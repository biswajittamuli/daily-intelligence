"""V3.2 tests: the 17 realistic Indian job scenarios (deterministic, network mocked) plus regressions.

Live results are reported separately (IMPLEMENTATION_STATUS.md); nothing here touches the network.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import httpx

from app.config import Settings
from app.memory.store import Store
from app.services.assessment import candidate_from_profile
from app.services.briefing_v2 import build_briefing
from app.services.broad_search import parse_request
from app.services.employer_discovery import EmployerDiscovery, detect_links, extract_companies
from app.services.insights import _location, job_market
from app.services.job_matching import rank_listing
from app.services.preferences import validate_preferences
from app.services.requirements import extract_requirements
from app.services.skills_taxonomy import canonical, canonical_set
from app.services.verification import lifecycle, verify_jobs

TODAY = date.today()
RECENT = (TODAY - timedelta(days=2)).isoformat()
PREFS = validate_preferences({"jobs": {"locations": ["India"], "experience": "fresher", "roles": ["AI Engineer"]}})
FRESHER = {"skills": ["Python", "PyTorch", "RAG", "FastAPI", "PostgreSQL", "Docker", "Git"],
           "education": ["B.Tech in Computer Science and Engineering"], "experience_years": 0,
           "graduation_year": TODAY.year}

AI_BENGALURU = """About the role
We are hiring an AI Engineer for our Bengaluru office.
Requirements:
* B.Tech or BE in Computer Science or related field
* 0-1 years of experience
* Strong Python and PyTorch
* Experience with RAG and LLMs
Nice to have:
* Docker
"""


def rank(text, title="AI Engineer", location="Bengaluru, India", profile=FRESHER, posted=RECENT, **extra):
    listing = {"title": title, "location": location, "raw_text": text, "posted_date": posted,
               "employer": "Acme", **extra}
    return rank_listing(listing, profile, PREFS)


class FakeRetriever:
    """Search results for publications/directories + website lookups; fetch is never needed (direct HTTP works)."""

    def __init__(self):
        self.searches = []

    async def search(self, queries, objective, **kwargs):
        self.searches.append(list(queries))
        if any("official website" in q for q in queries):
            return [{"title": "Kovai Labs — AI for retail", "url": "https://www.kovailabs.in/", "excerpts": []}]
        return [
            {"title": "Kovai Labs raises $5 Mn to build AI agents for Indian retail | Inc42",
             "url": "https://inc42.com/buzz/kovai-labs-raises-5-mn/", "publish_date": RECENT,
             "excerpts": ["Bengaluru-based Kovai Labs raised $5 Mn in a Series A round."]},
            {"title": "Why Indian AI funding is rising in 2026", "url": "https://yourstory.com/ai-funding-trend",
             "excerpts": ["An overview of the market."]},
        ]

    async def fetch(self, urls, objective, **kwargs):
        return []


def http_handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if url.startswith("https://kovailabs.in") or url.startswith("https://www.kovailabs.in"):
        return httpx.Response(200, headers={"content-type": "text/html"}, text=(
            "<html><body><h1>Kovai Labs</h1><p>Built in Bengaluru, India.</p>"
            "<a href='/careers'>Careers</a><a href='https://boards.greenhouse.io/kovailabs'>Open roles</a></body></html>"))
    if "boards-api.greenhouse.io/v1/boards/kovailabs/jobs" in url:
        return httpx.Response(200, json={"jobs": [
            {"title": "AI Engineer", "absolute_url": "https://boards.greenhouse.io/kovailabs/jobs/101",
             "location": {"name": "Bengaluru, India"}, "first_published": f"{RECENT}T09:00:00Z",
             "content": "Kovai Labs is hiring. Python, PyTorch, RAG. 0-1 years."}]})
    return httpx.Response(404, text="not found")


def discover(store):
    client = httpx.AsyncClient(transport=httpx.MockTransport(http_handler))
    engine = EmployerDiscovery(Settings(data_dir=store.data_dir), store, retriever=FakeRetriever(), http=client)
    return asyncio.run(engine.run("Find AI Engineer jobs at Indian startups", topic="AI", search_calls=2, use_llm=False))


class IndianJobScenarioTests(unittest.TestCase):
    # 1
    def test_01_entry_level_ai_engineer_bengaluru(self):
        intent = parse_request("Find entry-level AI Engineer jobs in Bengaluru")
        self.assertEqual(intent["city"], "Bengaluru")
        self.assertTrue(intent["fresher"])
        result = rank(AI_BENGALURU)
        a = result["assessment"]
        self.assertEqual(a["eligibility"], "eligible")
        self.assertIn(result["tier"], {"strong", "possible"})
        self.assertFalse(a["missing_mandatory"])

    # 2
    def test_02_fresher_python_backend_india(self):
        intent = parse_request("Find fresher Python Backend Developer jobs in India")
        self.assertTrue(intent["fresher"])
        self.assertIn("python backend developer", intent["role"].casefold())
        text = "Requirements:\n* Python and FastAPI\n* PostgreSQL\n* Freshers welcome, 0-1 years of experience"
        a = rank(text, title="Python Backend Developer", location="Pune, India")["assessment"]
        self.assertEqual(a["eligibility"], "eligible")
        self.assertEqual(a["missing_mandatory"], [])

    # 3 + 8
    def test_03_08_discover_new_indian_startup_and_career_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            self.assertIsNone(store.find_employer("Kovai Labs"))
            summary = discover(store)
            company = next(c for c in summary["companies"] if c["name"] == "Kovai Labs")
            self.assertEqual(company["website"], "https://kovailabs.in")
            self.assertTrue(company["career_url"])  # a real link found on the homepage, not a guessed URL
            self.assertEqual(company["country"], "India")
            self.assertEqual(company["classification"], "startup")
            self.assertGreaterEqual(summary["new_employers"], 1)
            self.assertIsNotNone(store.find_employer("Kovai Labs"))
            self.assertTrue(all(c["status"] for c in summary["coverage"]))

    # 4 + 7
    def test_04_07_public_greenhouse_board_detected_and_verified(self):
        links = detect_links("https://acme.in", "<a href='https://jobs.lever.co/acme'>Jobs</a>"
                                                "<script src='https://boards.greenhouse.io/embed/job_board/js?for=acme'></script>")
        self.assertEqual({a["provider"] for a in links["ats"]}, {"lever", "greenhouse"})
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            company = next(c for c in discover(store)["companies"] if c["name"] == "Kovai Labs")
            self.assertEqual((company["ats_provider"], company["ats_slug"], company["ats_jobs"]), ("greenhouse", "kovailabs", 1))

    # 5
    def test_05_funding_is_a_signal_not_a_vacancy(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            discover(store)
            signals = store.signals()
            self.assertEqual([s["signal_type"] for s in signals], ["funding"])
            self.assertEqual(signals[0]["company_name"], "Kovai Labs")
            self.assertEqual(store.jobs(), [])  # discovery never turns a signal into a listing
        # A trend article names no company and creates nothing.
        self.assertEqual(extract_companies([{"title": "Why Indian AI funding is rising", "url": "https://x.com/a"}]), [])

    # 6
    def test_06_remote_ai_internship_india(self):
        intent = parse_request("Find remote AI internships in India")
        self.assertEqual(intent["remote"], "Remote India")
        self.assertTrue(intent["intern"])
        a = rank("Requirements:\n* Python\n* Currently pursuing B.Tech", title="AI Intern", location="Remote, India")["assessment"]
        self.assertNotEqual(a["eligibility"], "not_eligible")

    # 9
    def test_09_psu_cse_explicit_eligibility(self):
        from app.mcp.filter import classify_cse_eligibility
        self.assertEqual(classify_cse_eligibility("b.e./b.tech in computer science engineering"), "explicit_cse_or_it_mention")
        self.assertEqual(classify_cse_eligibility("b.e. in mechanical engineering"), "needs_eligibility_verification")

    # 10 + 11 + 12
    def test_10_11_12_reverify_expire_and_inaccessible(self):
        async def ats(companies, **kwargs):
            jobs = [{"url": "https://boards.greenhouse.io/acme/jobs/1", "description": "Python", "posted_date": RECENT}]
            coverage = [{"platform": "acme", "ats": "greenhouse", "slug": "acme", "status": "ok", "results": 1}]
            return jobs, coverage

        class Blocked:
            async def fetch(self, urls, objective, **kwargs):
                return []  # login wall / blocked: nothing retrievable

        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            store.upsert_jobs([
                {"url": "https://boards.greenhouse.io/acme/jobs/1", "title": "AI Engineer", "employer": "Acme",
                 "source_platform": "greenhouse:acme", "discovered_via": "company career board", "status": "open"},
                {"url": "https://www.naukri.com/job-listings-ai-engineer-2", "title": "ML Engineer", "employer": "Beta",
                 "source_platform": "naukri.com", "status": "unverified"},
                {"url": "https://example.in/jobs/3", "title": "Data Engineer", "employer": "Gamma",
                 "deadline": (TODAY - timedelta(days=3)).isoformat(), "status": "unverified"},
            ])
            targets = store.jobs()
            result = asyncio.run(verify_jobs(store, Settings(data_dir=Path(tmp)), targets, ats_fetcher=ats,
                                             retriever=Blocked()))
            outcomes = {d["title"]: d["outcome"] for d in result["details"]}
            self.assertEqual(outcomes["AI Engineer"], "verified_open")
            self.assertEqual(outcomes["Data Engineer"], "expired")
            self.assertEqual(outcomes["ML Engineer"], "unreachable")
            by_title = {j["title"]: j for j in store.jobs()}
            self.assertEqual(lifecycle(by_title["AI Engineer"])["state"], "open_verified")
            self.assertEqual(lifecycle(by_title["Data Engineer"])["state"], "expired")
            self.assertNotEqual(by_title["ML Engineer"]["status"], "closed")  # unreachable is not closed

    def test_10b_board_miss_closes_only_after_two_checks(self):
        async def empty_board(companies, **kwargs):
            return [], [{"platform": "acme", "ats": "greenhouse", "slug": "acme", "status": "ok", "results": 0}]
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            store.upsert_jobs([{"url": "https://boards.greenhouse.io/acme/jobs/9", "title": "SDE", "employer": "Acme",
                                "source_platform": "greenhouse:acme", "status": "open"}])
            settings = Settings(data_dir=Path(tmp))
            first = asyncio.run(verify_jobs(store, settings, store.jobs(), ats_fetcher=empty_board))
            self.assertEqual(first["details"][0]["outcome"], "missing_once")
            self.assertEqual(store.jobs()[0]["status"], "open")
            second = asyncio.run(verify_jobs(store, settings, store.jobs(), ats_fetcher=empty_board))
            self.assertEqual(second["details"][0]["outcome"], "closed")

    # 13
    def test_13_more_experience_than_candidate(self):
        text = "Requirements:\n* 3+ years of experience building backend services\n* Python, FastAPI"
        result = rank(text, title="Backend Engineer", profile={**FRESHER, "experience_years": 1})
        a = result["assessment"]
        self.assertEqual(result["tier"], "ineligible")
        self.assertTrue(any(g.startswith("Experience") for g in a["gates"]))
        self.assertEqual(a["experience"]["difference"], -2)

    # 14
    def test_14_matching_skills_but_missing_mandatory_degree(self):
        text = "Requirements:\n* Master's degree in Computer Science required\n* Python, PyTorch, RAG\n* 0-2 years of experience"
        result = rank(text)
        self.assertEqual(result["tier"], "ineligible")
        self.assertTrue(any(g.startswith("Education") for g in result["assessment"]["gates"]))
        self.assertGreaterEqual(result["assessment"]["match"], 50)  # skills still visible as matching

    # 15
    def test_15_skill_normalisation(self):
        self.assertEqual(canonical_set(["LLM", "Large Language Models", "large language model"]), {"llms"})
        self.assertEqual(canonical("GenAI"), "Generative AI")
        self.assertEqual(canonical("CI/CD Pipelines"), "CI/CD")
        self.assertNotEqual(canonical("Java"), canonical("JavaScript"))

    # 16 + 17
    def test_16_17_cross_portal_dedup_keeps_both_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            base = {"title": "AI Engineer", "employer": "Acme Technologies Pvt Ltd", "location": "Bengaluru, India"}
            store.upsert_jobs([{**base, "url": "https://www.naukri.com/job-listings-acme-ai-1",
                                "sources": [{"platform": "naukri.com", "url": "https://www.naukri.com/job-listings-acme-ai-1"}]}])
            store.upsert_jobs([{**base, "employer": "Acme", "location": "Bangalore",
                                "url": "https://www.linkedin.com/jobs/view/42",
                                "sources": [{"platform": "linkedin.com", "url": "https://www.linkedin.com/jobs/view/42"}]}])
            jobs = store.jobs()
            self.assertEqual(len(jobs), 1)
            self.assertEqual({s["platform"] for s in jobs[0]["sources"]}, {"naukri.com", "linkedin.com"})
            # Same title, different requisition IDs: two different openings, never merged.
            store.upsert_jobs([{**base, "url": "https://acme.in/jobs/7", "requisition_id": "REQ-7"},
                               {**base, "url": "https://acme.in/jobs/8", "requisition_id": "REQ-8"}])
            self.assertGreaterEqual(len(store.jobs()), 2)


class V32RegressionTests(unittest.TestCase):
    def test_degree_alternatives_take_the_lowest(self):
        def degree(text):
            return [(e["degree"]) for e in extract_requirements(text, title="Engineer")["education"]]
        self.assertEqual(degree("Requirements:\n* B.Tech, BE, or M.Tech in Computer Science"), ["Bachelor's"])
        self.assertEqual(degree("Requirements:\n* Master's degree in Computer Science required"), ["Master's"])
        self.assertEqual(degree("Education: BE/B.Tech or MCA"), ["Bachelor's"])

    def test_specific_skills_imply_general_ones_but_not_reverse(self):
        c = candidate_from_profile({"skills": ["PostgreSQL", "Deep Learning (CNNs, Transformers)", "PyTorch"]}, {})
        self.assertIn("sql", c["implied"])
        self.assertIn("machine learning", c["implied"])
        self.assertIn("deep learning", c["explicit"])  # compound entry read
        python_only = candidate_from_profile({"skills": ["Python"]}, {})
        self.assertNotIn("fastapi", python_only["explicit"] | set(python_only["implied"]))
        self.assertNotIn("pytorch", python_only["explicit"] | set(python_only["implied"]))

    def test_programming_languages_in_keywords_count(self):
        c = candidate_from_profile({"skills": ["Docker"], "languages": ["English", "Hindi"],
                                    "keywords": ["Python", "Java", "Inventory management system"]}, {})
        self.assertTrue({"python", "java"} <= c["explicit"])
        self.assertNotIn("inventory management system", c["explicit"])

    def test_page_check_is_weaker_than_board_verification(self):
        now = TODAY.isoformat()
        page = lifecycle({"status": "open", "last_verified": now, "status_evidence": "Listing page reachable with apply option"})
        board = lifecycle({"status": "open", "last_verified": now, "status_evidence": "Listed on Greenhouse board 'x'"})
        self.assertEqual((page["state"], board["state"]), ("open_page_checked", "open_verified"))

    def test_city_variants_merge_in_skills_market(self):
        self.assertEqual({_location(v) for v in ("Bangalore", "bengaluru", "Onsite in Bangalore",
                                                 "Bengaluru, Karnataka, India")}, {"Bengaluru"})
        self.assertEqual(_location("Remote - India"), "Remote")

    def test_market_matrices_are_lists(self):
        jobs = [{"id": i, "title": "AI Engineer", "employer": f"E{i % 3}", "location": "Bangalore",
                 "skills": ["Python", "PyTorch"], "posted_date": RECENT, "source_platform": "wellfound.com",
                 "first_seen": RECENT, "original_url": f"https://x.in/{i}"} for i in range(6)]
        market = job_market(jobs, resumes=[{"profile": {"skills": ["PostgreSQL"]}, "status": "processed"}])
        for key in ("skills_by_portal", "skills_by_role", "skills_by_location", "skills_by_employer"):
            self.assertIsInstance(market[key]["matrix"], list, key)
        self.assertNotIn("Python", [g["name"] for g in market["skill_gap"]]) if market["resume_complete"] else None

    def test_employer_inferred_only_from_evidence(self):
        from app.services.listing_links import infer_employer
        cases = {
            ("https://www.naukri.com/job-listings-ai-engineer-hitachi-energy-bengaluru-2-to-4-years-0505", "AI Engineer"):
                "Hitachi Energy",
            ("https://www.naukri.com/job-listings-agentic-ai-engineer-claude-code-cursor-nordavo-bengaluru-1", "Agentic AI Engineer (Claude Code, Cursor)"):
                "Nordavo",
            ("https://simbian.zohorecruit.in/jobs/careers/1/x", "Applied AI Engineer"): "Simbian",
            ("https://jobs.ametek.com/job/x", "AI Engineer/ Developer Job Details | Ametek, Inc."): "Ametek",
        }
        for (url, title), name in cases.items():
            self.assertEqual(infer_employer(url, title)[0], name, url)
        self.assertEqual(infer_employer("https://in.indeed.com/viewjob?jk=1", "AI Engineer",
                                        "https://in.indeed.com/cmp/Prodigal/salaries")[0], "Prodigal")
        # No evidence -> no guess; aggregator names are not employers.
        self.assertEqual(infer_employer("https://in.indeed.com/viewjob?jk=2", "AI / ML Engineer"), (None, None))
        self.assertIsNone(infer_employer("https://aimlroles.com/x", "ML Engineer Jobs | aimlroles")[0])

    def test_suggestions_skip_ineligible_and_follow_up_applications(self):
        from app.services.today_plan import build_today_plan
        jobs = [{"id": 1, "title": "Senior AI Engineer", "match_score": 92, "status": "open",
                 "eligibility": {"tier": "ineligible", "status": "not_eligible", "composite": 40}},
                {"id": 2, "title": "AI Engineer", "match_score": 75, "status": "open",
                 "eligibility": {"tier": "possible", "status": "eligible", "composite": 70}}]
        old = (TODAY - timedelta(days=9)).isoformat()
        plan = build_today_plan(tasks=[], jobs=jobs, exams=[], notices=[], item_states={},
                                tracker=[{"id": 5, "role": "SDE", "company": "Acme", "status": "applied", "applied_at": old}])
        titles = [s["title"] for s in plan["suggestions"]]
        self.assertTrue(any("AI Engineer" in t and "Senior" not in t for t in titles), titles)
        self.assertFalse(any("Senior" in t for t in titles), titles)
        self.assertIn("Follow up: SDE at Acme", titles)

    def test_briefing_never_recommends_closed_jobs(self):
        job = {"title": "AI Engineer", "employer": "Acme", "original_url": "https://x/1", "status": "closed",
               "first_seen": "2099-01-01", "eligibility": {"tier": "strong", "composite": 90}}
        brief = build_briefing(jobs=[job], notices=[], exams=[], news=[], papers=[], employers=[], signals=[],
                               applications=[], today_plan={}, previous_at="2000-01-01")
        jobs_section = next(s for s in brief["sections"] if s["key"] == "jobs")
        self.assertEqual(jobs_section["items"], [])

    def test_application_status_history_and_reminders(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            item = store.save_application({"role": "SDE", "company": "Acme", "status": "applied",
                                           "follow_up_date": (TODAY + timedelta(days=3)).isoformat(),
                                           "interview_dates": [{"at": f"{TODAY + timedelta(days=5)}T10:30", "note": "R1"}]})
            item = store.save_application({"status": "interview"}, item["id"])
            self.assertEqual([h["status"] for h in item["history"]], ["applied", "interview"])
            self.assertEqual(item["applied_at"], TODAY.isoformat())
            with self.assertRaises(ValueError):
                store.save_application({"status": "submitted-automatically"}, item["id"])


if __name__ == "__main__":
    unittest.main()
