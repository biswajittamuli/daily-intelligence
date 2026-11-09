"""v3.3 pipeline acceptance tests (offline): unknown employer resolution, portal honesty, dedup, lifecycle."""
from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import httpx

from app.config import Settings
from app.memory.store import Store
from app.services.broad_search import BroadJobSearch
from app.services.employer_discovery import cluster_signals
from app.services.job_sources.safe_http import SafeFetcher
from app.services.preferences import validate_preferences
from app.services.verification import lifecycle

RECENT = (date.today() - timedelta(days=2)).isoformat()
PREFS = validate_preferences({"jobs": {"locations": ["India"], "experience": "fresher", "roles": ["AI Engineer"],
                                       "companies": [{"name": "Acme", "ats": "greenhouse", "slug": "acme"}]}})
PROFILE = {"skills": ["Python", "PyTorch", "RAG", "FastAPI", "Docker"], "experience_years": 0}


class Retriever:
    """Search results from portals, the open web and an employer-resolution query."""

    def __init__(self):
        self.searches, self.fetched = [], []

    async def search(self, queries, objective, **kwargs):
        self.searches.append(list(queries))
        if any("Nimbus Robotics careers" in q for q in queries):
            return [{"title": "Careers | Nimbus Robotics", "url": "https://www.nimbusrobotics.in/careers",
                     "domain": "nimbusrobotics.in", "excerpts": ["Join Nimbus Robotics"]}]
        if any(q.startswith("site:") and "greenhouse" not in q and "lever" not in q and "ashby" not in q
               and "workable" not in q and "smartrecruiters" not in q and "workday" not in q for q in queries):
            return [
                {"title": "AI Engineer at Acme | LinkedIn", "url": "https://www.linkedin.com/jobs/view/ai-engineer-at-acme-4001",
                 "domain": "linkedin.com", "publish_date": RECENT,
                 "excerpts": ["Acme is hiring an AI Engineer in Bengaluru, India. Python, PyTorch. 0-1 years."]},
                {"title": "AI Engineer Jobs in Bengaluru | Indeed", "url": "https://in.indeed.com/q-ai-engineer-l-bengaluru-jobs.html",
                 "domain": "in.indeed.com", "excerpts": ["3,000+ AI Engineer jobs"]},
            ]
        return [
            {"title": "AI Engineer at Nimbus Robotics", "url": "https://startupjobs.example/jobs/nimbus-ai-engineer-55501",
             "domain": "startupjobs.example", "publish_date": RECENT,
             "excerpts": ["Nimbus Robotics is hiring an AI Engineer in Pune, India. Python, PyTorch, RAG. Freshers welcome."]},
        ]

    async def fetch(self, urls, objective, **kwargs):
        self.fetched.extend(urls)
        return []


def nimbus_site(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    host = request.url.host
    if path == "/robots.txt":
        return httpx.Response(404)
    if host == "nimbusrobotics.in" and path in {"", "/"}:
        return httpx.Response(200, headers={"content-type": "text/html"}, text=(
            "<html><head><title>Nimbus Robotics — warehouse robots, Pune India</title></head><body>"
            "<nav><a href='/about'>About</a></nav><footer><a href='https://jobs.lever.co/nimbus'>Careers</a></footer>"
            "</body></html>"))
    return httpx.Response(404, text="not found")


async def ats(companies, **kwargs):
    jobs, coverage = [], []
    for company in companies:
        if company["slug"] == "acme":
            jobs.append({"title": "AI Engineer", "employer": "Acme", "location": "Bengaluru, India",
                         "url": "https://job-boards.greenhouse.io/acme/jobs/9001", "posted_date": RECENT,
                         "description": "Python PyTorch RAG. 0-1 years.", "source_platform": "greenhouse:acme",
                         "ats": "greenhouse"})
            coverage.append({"platform": company["name"], "method": "greenhouse API", "status": "ok", "results": 1})
        elif company["slug"] == "nimbus":
            jobs.append({"title": "AI Engineer", "employer": "Nimbus Robotics", "location": "Pune, India",
                         "url": "https://jobs.lever.co/nimbus/0f0f0f0f-aaaa-bbbb-cccc-111122223333", "posted_date": RECENT,
                         "description": "Python PyTorch RAG. Freshers welcome.", "source_platform": "lever:nimbus",
                         "ats": "lever"})
            coverage.append({"platform": company["name"], "method": "lever API", "status": "ok", "results": 1})
        else:
            coverage.append({"platform": company["name"], "method": f"{company['ats']} API",
                             "status": "board not found (404)", "results": 0})
    return jobs, coverage


def run_search(store, retriever, prefs=PREFS):
    async def go():
        async with SafeFetcher(transport=httpx.MockTransport(nimbus_site), allow_private_hosts={"nimbusrobotics.in",
                                                                                               "www.nimbusrobotics.in"},
                               per_host_interval=0, retries=0) as http:
            engine = BroadJobSearch(Settings(data_dir=store.data_dir), store, prefs, retriever=retriever,
                                    ats_fetcher=ats, http=http, browser=None, direct_fetch=True)
            return await engine.run("entry-level AI Engineer jobs in India", pool_size=50, use_llm=False)
    return asyncio.run(go())


class PipelineAcceptanceTests(unittest.TestCase):
    def test_b_unknown_startup_is_resolved_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            store.add_resume(PROFILE, "ai.pdf", "AI", make_default=True)
            self.assertIsNone(store.find_employer("Nimbus Robotics"))
            summary = run_search(store, Retriever())
            employer = store.find_employer("Nimbus Robotics")
            self.assertIsNotNone(employer, summary["steps"])
            self.assertEqual(employer["website"], "https://nimbusrobotics.in")
            self.assertEqual(employer["career_outcome"], "ats_identified")
            self.assertEqual((employer["ats_provider"], employer["ats_slug"]), ("lever", "nimbus"))
            methods = [m["stage"] for m in employer["career_discovery"]["methods"]]
            self.assertEqual(methods[0], "A")
            self.assertIsNotNone(employer["next_discovery_at"])
            jobs = [j for j in store.jobs() if j.get("employer") == "Nimbus Robotics"]
            self.assertTrue(jobs)
            official = [j for j in jobs if "jobs.lever.co/nimbus" in j["original_url"]]
            self.assertTrue(official, [j["original_url"] for j in jobs])
            self.assertEqual(official[0]["discovered_via"], "company career board")
            self.assertEqual(official[0]["extraction_method"], "lever public job-board API")
            # The search-result page that led us here is preserved as a source reference.
            urls = {s["url"] for j in jobs for s in j.get("sources") or []} | {j["original_url"] for j in jobs}
            self.assertIn("https://startupjobs.example/jobs/nimbus-ai-engineer-55501", urls)
            self.assertGreaterEqual(summary["boards_discovered"], 1)

    def test_d_linkedin_and_indeed_are_reported_honestly(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            store.add_resume(PROFILE, "ai.pdf", "AI", make_default=True)
            prefs = validate_preferences({"jobs": {**PREFS["jobs"], "portals": {
                "LinkedIn": {"domain": "linkedin.com", "enabled": True}, "Indeed": {"domain": "in.indeed.com", "enabled": True}}}})
            retriever = Retriever()
            summary = run_search(store, retriever, prefs)
            self.assertFalse([u for u in retriever.fetched if "linkedin.com" in u or "indeed.com" in u])
            sources = summary["acquisition"]["sources"]
            indeed = [r for r in sources if r["name"] == "Indeed"]
            self.assertTrue(indeed)
            self.assertFalse(any(r["state"] == "extraction_successful" for r in indeed))
            self.assertTrue(any(r["state"] == "skipped_by_access_policy" for r in indeed))
            linkedin = [r for r in sources if r["name"] == "LinkedIn"]
            self.assertTrue(all(r["state"] in {"search_successful", "no_results"} for r in linkedin))
            self.assertTrue(any("search results only" in (r.get("method") or "") or "only" in (r.get("method") or "")
                                for r in linkedin))
            exclusions = store.exclusions(summary["session_id"], reason="Search or listing-index page, not a job detail")
            self.assertTrue(any("indeed.com" in e["url"] and "search results only" in (e["detail"] or "")
                                for e in exclusions["items"]))

    def test_e_same_vacancy_from_board_portal_and_web_is_one_listing(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            store.add_resume(PROFILE, "ai.pdf", "AI", make_default=True)
            prefs = validate_preferences({"jobs": {**PREFS["jobs"], "portals": {
                "LinkedIn": {"domain": "linkedin.com", "enabled": True}}}})
            run_search(store, Retriever(), prefs)
            acme = [j for j in store.jobs() if (j.get("employer") or "").casefold() == "acme"]
            self.assertEqual(len(acme), 1, [(j["title"], j["original_url"]) for j in acme])
            job = acme[0]
            self.assertEqual(job["original_url"], "https://job-boards.greenhouse.io/acme/jobs/9001")
            source_urls = {s["url"] for s in job["sources"]}
            self.assertIn("https://www.linkedin.com/jobs/view/ai-engineer-at-acme-4001", source_urls)
            self.assertEqual(lifecycle(job)["state"], "open_verified")

    def test_store_merge_prefers_employer_page_and_keeps_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            store.upsert_jobs([{"url": "https://www.naukri.com/job-listings-ai-engineer-zeta-bengaluru-1", "title": "AI Engineer",
                                "employer": "Zeta", "location": "Bengaluru", "posted_date": "2026-11-01",
                                "discovered_via": "web search", "status": "unverified"}])
            store.upsert_jobs([{"url": "https://jobs.lever.co/zeta/abcdef12-0000", "title": "AI Engineer", "employer": "Zeta",
                                "location": "Bengaluru", "posted_date": "2026-11-03", "discovered_via": "company career board",
                                "status": "open", "extraction_method": "lever public job-board API"}])
            jobs = store.jobs()
            self.assertEqual(len(jobs), 1)
            job = jobs[0]
            self.assertEqual(job["application_url"], "https://jobs.lever.co/zeta/abcdef12-0000")
            self.assertEqual(job["status"], "open")
            self.assertEqual(job["discovered_via"], "company career board")
            self.assertEqual(job["conflicts"][0]["field"], "posted_date")
            self.assertEqual(len(job["sources"]), 2)

    def test_f_lifecycle_states(self):
        today = date.today()
        cases = {
            "open_verified": {"status": "open", "last_verified": today.isoformat(), "discovered_via": "company career board"},
            "open_page_checked": {"status": "open", "last_verified": today.isoformat(), "verification_source": "third-party listing page"},
            "closed": {"status": "closed"},
            "expired": {"status": "unverified", "deadline": (today - timedelta(days=1)).isoformat()},
            "inaccessible": {"status": "unverified", "verify_history": [{"outcome": "unreachable"}, {"outcome": "unreachable"}]},
            "pending_verification": {"status": "unverified"},
            "unverified": {"status": "unverified", "verify_history": [{"outcome": "unchanged"}]},
        }
        for state, job in cases.items():
            self.assertEqual(lifecycle(job)["state"], state, job)
        employer_page = {"status": "open", "last_verified": today.isoformat(), "verification_source": "employer page"}
        self.assertEqual(lifecycle(employer_page)["label"], "Open · verified on employer page")
        self.assertIn("conflicting", lifecycle({"status": "unverified", "conflicts": [{"field": "posted_date"}],
                                                "verify_history": [{"outcome": "unchanged"}]})["label"])

    def test_funding_articles_cluster_into_one_event(self):
        signals = [
            {"company_name": "Kovai Labs", "signal_type": "funding", "amount": "$5 Mn", "signal_date": "2026-11-01",
             "source_url": "https://inc42.com/a", "publisher": "inc42.com"},
            {"company_name": "Kovai Labs AI", "signal_type": "funding", "amount": "USD 5 million", "signal_date": "2026-11-02",
             "source_url": "https://yourstory.com/b", "publisher": "yourstory.com"},
            {"company_name": "Kovai Labs", "signal_type": "funding", "amount": "$20 Mn", "signal_date": "2026-11-03",
             "source_url": "https://entrackr.com/c", "publisher": "entrackr.com"},
            {"company_name": "Kovai Labs", "signal_type": "hiring", "signal_date": "2026-11-02",
             "source_url": "https://et.com/d", "publisher": "et.com"},
        ]
        events = cluster_signals(signals)
        funding = [e for e in events if e["signal_type"] == "funding"]
        self.assertEqual(len(funding), 2)
        five = next(e for e in funding if e["source_count"] == 2)
        self.assertEqual({s["publisher"] for s in five["sources"]}, {"inc42.com", "yourstory.com"})
        self.assertEqual(len([e for e in events if e["signal_type"] == "hiring"]), 1)


if __name__ == "__main__":
    unittest.main()
