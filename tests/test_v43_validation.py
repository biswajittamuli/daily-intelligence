"""v4.3 regression tests: vacancy validation gate, publication freshness, geography, verification, dedup,
job-API parsers and source health. Fixtures are realistic records taken from the shapes real sources return."""
from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from app.config import Settings
from app.memory.store import Store
from app.services.broad_search import BroadJobSearch
from app.services.feed import build_feed
from app.services.freshness import freshness_bucket
from app.services.job_sources.models import SourceState
from app.services.job_sources.safe_http import FetchResult
from app.services.vacancy_validation import (classify_document, classify_geography, clean_text, clean_title,
                                             employer_owned_url, publication_freshness, validate)

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
TODAY = NOW.date()
PREFS = {"jobs": {"locations": ["India", "Bengaluru"], "roles": ["AI Engineer"]}}


def job(**fields):
    base = {"id": 1, "title": "AI Engineer", "employer": "Acme Labs", "location": "Bengaluru, India",
            "original_url": "https://jobs.acmelabs.com/job/ai-engineer/123", "status": "open",
            "first_seen": NOW.isoformat(), "eligibility": {"tier": "strong"}}
    base.update(fields)
    return base


class FakeHttp:
    """Answers get/get_many from a URL -> FetchResult map; records calls."""

    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    async def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        for prefix, result in self.pages.items():
            if url.startswith(prefix):
                return result
        return FetchResult(url=url, status=404, state=SourceState.NOT_FOUND)

    async def get_many(self, urls, **kwargs):
        return [await self.get(url, **kwargs) for url in urls]


def ok(text, url="https://x.test"):
    return FetchResult(url=url, final_url=url, status=200, state=SourceState.FETCH_OK, text=text,
                       content_type="text/html")


class RequiredCases(unittest.TestCase):
    # Test 1: old job rediscovered today
    def test_old_job_rediscovered_today_is_not_new(self):
        old = job(posted_date=(TODAY - timedelta(days=35)).isoformat(), posted_date_source="JobPosting datePosted",
                  posting_date_confidence="high", last_verified=NOW.isoformat(),
                  status_evidence="Employer page has JobPosting data", verification_source="employer page")
        bucket = freshness_bucket(old, now=NOW, lifecycle_state="open_verified")
        self.assertEqual(bucket["key"], "older_open")
        self.assertFalse(bucket["newly_published"])
        self.assertEqual(bucket["window"], "older")
        self.assertTrue(bucket["newly_discovered"])  # discovered today, but not published today
        verdict = validate(old, lifecycle_state="open_verified", now=NOW)
        self.assertEqual(verdict["vacancy_status"], "open_employer_verified")
        self.assertEqual(verdict["group"], "verified_strong")  # still visible in the older active-jobs view
        feed = build_feed(jobs=[{**old, "validation": verdict, "freshness_bucket": bucket,
                                 "lifecycle": {"state": "open_verified"}}],
                          notices=[], exams=[], employers=[], states={}, reported=set(), today=TODAY)
        item = feed["items"][0]
        self.assertNotIn("new", item["sections"])
        self.assertEqual(feed["summary"]["new_opportunities"], 0)

    # Test 2: job published today
    def test_job_published_today_is_new(self):
        fresh = job(posted_date=TODAY.isoformat(), posted_date_source="employer ATS",
                    application_url="https://jobs.acmelabs.com/apply/123", last_verified=NOW.isoformat(),
                    discovered_via="company career board")
        bucket = freshness_bucket(fresh, now=NOW, lifecycle_state="open_verified")
        self.assertEqual(bucket["key"], "new_today")
        self.assertEqual(bucket["label"], "Published today")
        self.assertTrue(bucket["newly_published"])
        verdict = validate(fresh, lifecycle_state="open_verified", now=NOW)
        feed = build_feed(jobs=[{**fresh, "validation": verdict, "freshness_bucket": bucket,
                                 "lifecycle": {"state": "open_verified"}}],
                          notices=[], exams=[], employers=[], states={}, reported=set(), today=TODAY)
        self.assertIn("new", feed["items"][0]["sections"])
        self.assertEqual(feed["summary"]["new_opportunities"], 1)

    # Test 3: talent network
    def test_talent_network_is_not_a_vacancy(self):
        record = job(title="Remote Professionals &amp; Specialists – AI Matching Network (All Industries & Skill Levels)",
                     employer=None, location="Remote", original_url="https://hasjob.co/sunlightmedia.org/74qjg",
                     raw={"raw_text": "Join our AI matching network. Register your profile and get matched to roles."},
                     eligibility={"tier": "strong"})
        document = classify_document(record)
        self.assertEqual(document["type"], "talent_network")
        self.assertFalse(document["is_vacancy"])
        verdict = validate(record, lifecycle_state="pending_verification", now=NOW)
        self.assertEqual(verdict["group"], "not_vacancy")
        feed = build_feed(jobs=[{**record, "validation": verdict, "lifecycle": {"state": "pending_verification"}}],
                          notices=[], exams=[], employers=[], states={}, reported=set(), today=TODAY)
        self.assertEqual(feed["items"], [])
        self.assertEqual(len(feed["other_opportunities"]), 1)
        self.assertEqual(feed["summary"]["strong_matches"], 0)

    # Test 4: US-only remote job
    def test_us_only_remote_job_is_outside_geography(self):
        geo = classify_geography(location="Remote", title="Machine Learning Engineer",
                                 text="This is a fully remote role. Applicants must reside in the United States.")
        self.assertEqual(geo["kind"], "remote_not_india")
        self.assertTrue(geo["excluded"])
        record = job(location="Remote", raw={"raw_text": "Applicants must reside in the United States."})
        self.assertEqual(validate(record, lifecycle_state="open_verified", now=NOW)["group"], "outside_geography")
        from app.services.job_matching import relevance_gate
        gate = relevance_gate({**record, "raw_text": record["raw"]["raw_text"]}, {}, PREFS, targets=["AI Engineer"])
        self.assertTrue(gate["excluded"])

    # Test 5: India-compatible remote job
    def test_remote_job_open_to_india(self):
        geo = classify_geography(location="Remote", title="Backend Engineer",
                                 text="Work remotely from anywhere in India. We welcome applicants based in India.")
        self.assertEqual(geo["kind"], "remote_india")
        self.assertTrue(geo["eligible"])
        self.assertEqual(classify_geography(location="Remote", restrictions=["India"])["kind"], "remote_india")
        # "Remote" alone is not evidence: it is labelled unknown, never India-eligible.
        self.assertEqual(classify_geography(location="Remote", title="Backend Engineer")["kind"], "remote_unknown")

    # Test 6: duplicate vacancy across LinkedIn, Indeed and the employer ATS
    def test_duplicate_across_portals_merges_with_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            engine = BroadJobSearch(Settings(data_dir=Path(tmp)), store, PREFS)
            ats = [{"title": "AI Engineer", "url": "https://boards.greenhouse.io/acmelabs/jobs/4410", "employer": "Acme Labs",
                    "location": "Bengaluru, India", "posted_date": "2026-11-08", "source_platform": "greenhouse:acmelabs",
                    "ats": "greenhouse", "application_url": "https://boards.greenhouse.io/acmelabs/jobs/4410#app",
                    "description": "Build RAG pipelines in Python."}]
            listings = [
                {"title": "AI Engineer at Acme Labs", "url": "https://in.linkedin.com/jobs/view/ai-engineer-at-acme-labs-4031",
                 "domain": "in.linkedin.com", "excerpts": ["Acme Labs · Bengaluru, Karnataka, India · 1 day ago"]},
                {"title": "AI Engineer - Acme Labs - Bengaluru", "url": "https://in.indeed.com/viewjob?jk=ab12",
                 "domain": "in.indeed.com", "excerpts": ["Acme Labs is hiring an AI Engineer in Bengaluru."]},
            ]
            for item in listings:
                item["title"] = "AI Engineer at Acme Labs"
            candidates, duplicates = engine._candidates(listings, [], ats)
            self.assertEqual(len(candidates), 1)
            self.assertEqual(duplicates, 2)
            canonical = candidates[0]
            self.assertEqual(len(canonical["sources"]), 3)
            self.assertEqual(canonical["url"], "https://boards.greenhouse.io/acmelabs/jobs/4410")
            self.assertEqual(canonical["application_url"], "https://boards.greenhouse.io/acmelabs/jobs/4410#app")

    def test_same_title_in_different_cities_is_not_merged(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = BroadJobSearch(Settings(data_dir=Path(tmp)), Store(Path(tmp)), PREFS)
            ats = [{"title": "Software Engineer", "url": f"https://jobs.lever.co/acme/{n}", "employer": "Acme",
                    "location": city, "source_platform": "lever:acme", "ats": "lever"}
                   for n, city in ((1, "Bengaluru"), (2, "Pune"))]
            candidates, duplicates = engine._candidates([], [], ats)
            self.assertEqual(len(candidates), 2)
            self.assertEqual(duplicates, 0)

    # Test 7: temporary source failure
    def test_timeout_never_closes_a_job(self):
        from app.services.verification import lifecycle, verify_jobs
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            saved = store.upsert_jobs([{"url": "https://jobs.acmelabs.com/job/1", "title": "AI Engineer",
                                        "employer": "Acme Labs", "status": "open", "last_verified": NOW.isoformat(),
                                        "application_url": "https://jobs.acmelabs.com/job/1",
                                        "status_evidence": "Employer page shows an apply option",
                                        "verification_source": "employer page"}])[0]
            http = FakeHttp({"https://jobs.acmelabs.com": FetchResult(url="x", state=SourceState.TIMEOUT,
                                                                      error="timed out")})
            summary = asyncio.run(verify_jobs(store, Settings(data_dir=Path(tmp)), [saved], http=http))
            self.assertEqual(summary["unreachable"], 1)
            stored = store.jobs()[0]
            self.assertEqual(stored["status"], "open")
            state = lifecycle(stored)["state"]
            self.assertEqual(state, "recheck_pending")
            self.assertEqual(validate(stored, lifecycle_state=state)["vacancy_status"], "possibly_open")

    # Test 8: search results page
    def test_search_results_page_is_an_index(self):
        record = {"title": "100 Python Developer jobs in Bengaluru", "employer": None,
                  "original_url": "https://www.foundit.in/srp/results?query=python-developer&locations=bengaluru",
                  "discovered_via": "web search"}
        document = classify_document(record)
        self.assertEqual(document["type"], "search_results")
        self.assertFalse(document["is_vacancy"])
        from app.services.listing_links import harvest_listings
        page = "".join(f'<a href="https://www.foundit.in/job/python-developer-acme-bengaluru-{n}">Python Developer</a>'
                       for n in range(1, 4))
        expanded = harvest_listings(record["original_url"], page)
        self.assertEqual(len(expanded), 3)  # expanded into individual vacancy links before publication

    # Test 9: missing publication date
    def test_missing_publication_date_is_not_invented(self):
        record = job(posted_date=None, first_seen=(NOW - timedelta(days=2)).isoformat())
        fresh = publication_freshness(record, now=NOW)
        self.assertIsNone(fresh["published_at"])
        self.assertEqual(fresh["window"], "unknown")
        self.assertFalse(fresh["newly_published"])
        self.assertEqual(fresh["label"], "Publication date not disclosed · First discovered 2 days ago")
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            first = store.upsert_jobs([{"url": "https://x.test/j/1", "title": "AI Engineer"}])[0]
            again = store.upsert_jobs([{"url": "https://x.test/j/1", "title": "AI Engineer"}])[0]
            self.assertIsNone(again["posted_date"])
            self.assertEqual(first["first_seen"], again["first_seen"])  # first_seen never resets
            self.assertIsNotNone(again["last_fetched_at"])

    # Test 10: invalid or stale application link
    def test_stale_link_is_pending_not_employer_verified(self):
        from app.services.verification import lifecycle, verify_jobs
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            saved = store.upsert_jobs([{"url": "https://careers.acmelabs.com/jobs/77", "title": "AI Engineer",
                                        "employer": "Acme Labs", "status": "open", "last_verified": NOW.isoformat(),
                                        "application_url": "https://careers.acmelabs.com/jobs/77",
                                        "verification_source": "employer page"}])[0]
            http = FakeHttp({})  # every URL -> 404
            asyncio.run(verify_jobs(store, Settings(data_dir=Path(tmp)), [saved], http=http))
            stored = store.jobs()[0]
            state = lifecycle(stored)["state"]
            self.assertNotEqual(state, "open_verified")
            verdict = validate(stored, lifecycle_state=state)
            self.assertEqual(verdict["vacancy_status"], "possibly_open")
            self.assertNotEqual(verdict["verification_level"], "employer")
            # a second consecutive miss closes it, with history of the transition
            asyncio.run(verify_jobs(store, Settings(data_dir=Path(tmp)), [store.jobs()[0]], http=http))
            self.assertEqual(store.jobs()[0]["status"], "closed")
            self.assertEqual(store.status_history(saved["id"])[-1]["to_status"], "closed")


class ExtractionAndDates(unittest.TestCase):
    def test_html_entities_decoded_without_touching_urls(self):
        self.assertEqual(clean_text("Software Engineer – Backend &amp; Platform"), "Software Engineer – Backend & Platform")
        self.assertEqual(clean_text("R&amp;amp;D"), "R&D")
        self.assertEqual(clean_title("Technical Support Engineer Operations USA (Remote) View &amp; Apply"),
                         "Technical Support Engineer Operations USA (Remote)")
        self.assertEqual(clean_title("AI Platform Engineer San Francisco San Francisco Apply"),
                         "AI Platform Engineer San Francisco")
        self.assertEqual(clean_text("AT&T"), "AT&T")

    def test_labelled_date_found_during_employer_verification(self):
        """The Ametek case: an undated search hit whose employer page says 'Date: Oct 19, 2026'."""
        from app.services.verification import verify_jobs
        page = ok("<html><body><h1>AI Engineer/ Developer</h1><p>Date: Oct 19, 2026</p>"
                  "<p>Job Description: build AI agents.</p><a>Apply now</a></body></html>")
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            saved = store.upsert_jobs([{"url": "https://jobs.ametek.com/job/Bangalore-AI-Engineer-Developer/1441296700",
                                        "title": "AI Engineer/ Developer", "employer": "Ametek", "location": "Bangalore",
                                        "discovered_via": "web search"}])[0]
            asyncio.run(verify_jobs(store, Settings(data_dir=Path(tmp)), [saved],
                                    http=FakeHttp({"https://jobs.ametek.com": page})))
            stored = store.jobs()[0]
            self.assertEqual(stored["posted_date"], "2026-10-19")
            self.assertEqual(stored["posted_date_source"], "employer page label")
            self.assertEqual(stored["verification_source"], "employer page")
            bucket = freshness_bucket(stored, now=NOW, lifecycle_state="open_verified")
            self.assertFalse(bucket["newly_published"])
            self.assertEqual(bucket["label"], "Published 21 days ago · still open")

    def test_employer_owned_url(self):
        self.assertTrue(employer_owned_url("https://jobs.ametek.com/job/x/1", "Ametek"))
        self.assertFalse(employer_owned_url("https://in.linkedin.com/jobs/view/1", "Ametek"))
        self.assertFalse(employer_owned_url("https://himalayas.app/companies/a/jobs/b", "A"))


class Geography(unittest.TestCase):
    def test_categories(self):
        cases = {
            ("Bengaluru, India", None, ""): "india",
            ("IN-Bengaluru", None, ""): "india",
            ("Remote India", "remote", ""): "remote_india",
            ("Remote, Global", "remote", ""): "remote_india",
            ("Remote - Luxembourg", "remote", ""): "remote_not_india",
            ("Malaysia, Malaysia", "remote", ""): "remote_not_india",
            ("Remote, APAC", None, ""): "remote_unknown",
            ("San Francisco, CA", None, ""): "outside",
            ("Berlin", None, "Relocation package provided for international hires."): "relocation",
            (None, None, ""): "unknown",
        }
        for (location, remote, text), expected in cases.items():
            with self.subTest(location=location):
                self.assertEqual(classify_geography(location=location, remote=remote, text=text)["kind"], expected)

    def test_relocation_is_outside_unless_accepted(self):
        text = "We sponsor visas for this on-site role."
        default = classify_geography(location="San Francisco, United States", text=text)
        self.assertEqual(default["kind"], "relocation")
        self.assertTrue(default["excluded"])
        accepted = classify_geography(location="San Francisco, United States", text=text, accept_relocation=True)
        self.assertFalse(accepted["excluded"])
        self.assertTrue(accepted["uncertain"])

    def test_medical_ai_gig_is_not_technical_for_a_cse_profile(self):
        from app.services.job_matching import relevance_gate
        gate = relevance_gate({"title": "Licensed Physician (MD/DO) - Freelance AI Trainer", "location": "India"},
                              {}, PREFS, targets=["AI Engineer"])
        self.assertEqual(gate["excluded"], "Not a technical role for your profile")

    def test_place_in_title_when_location_missing(self):
        geo = classify_geography(location=None, title="AI Platform Engineer San Francisco San Francisco Apply")
        self.assertEqual(geo["kind"], "outside")

    def test_target_country_is_configurable(self):
        geo = classify_geography(location="Berlin, Germany", target="Germany")
        self.assertEqual(geo["kind"], "india")  # "in the target country" (kind keeps its India-default name)
        self.assertTrue(geo["eligible"])
        self.assertEqual(classify_geography(location="Pune, India", target="Germany")["kind"], "outside")


class JobApis(unittest.TestCase):
    def test_himalayas_parser_keeps_restrictions_and_dates(self):
        from app.services.job_sources.job_apis import parse_himalayas
        payload = {"jobs": [{"title": "AI/ML Engineer - Production AI &amp; LLM Systems (India)", "companyName": "Volga Partners",
                             "locationRestrictions": ["India"], "pubDate": 1794207960, "expiryDate": 1799391959,
                             "guid": "https://himalayas.app/companies/volga-partners/jobs/ai-ml-engineer",
                             "applicationLink": "https://himalayas.app/companies/volga-partners/jobs/ai-ml-engineer?utm_source=api",
                             "employmentType": "Full Time", "description": "<p>Build LLM systems</p>"}]}
        item = parse_himalayas(payload)[0]
        self.assertEqual(item["title"], "AI/ML Engineer - Production AI & LLM Systems (India)")
        self.assertEqual(item["location_restrictions"], ["India"])
        self.assertEqual(item["posted_date"], datetime.fromtimestamp(1794207960, tz=timezone.utc).date().isoformat())
        self.assertNotIn("utm_source", item["url"])
        self.assertEqual(classify_geography(location=item["location"], remote="remote",
                                            restrictions=item["location_restrictions"])["kind"], "remote_india")

    def test_google_jobs_prefers_employer_link_and_keeps_portals(self):
        from app.services.job_sources.job_apis import parse_google_jobs
        payload = {"jobs_results": [{
            "title": "Generative AI Engineer", "company_name": "Acme Labs", "location": "Bengaluru, Karnataka, India",
            "via": "LinkedIn", "description": "Python, RAG", "detected_extensions": {"posted_at": "3 days ago"},
            "apply_options": [{"title": "LinkedIn", "link": "https://in.linkedin.com/jobs/view/123"},
                              {"title": "Naukri", "link": "https://www.naukri.com/job-listings-123"},
                              {"title": "Acme Labs", "link": "https://careers.acmelabs.com/jobs/77"}]}]}
        item = parse_google_jobs(payload, today=TODAY)[0]
        self.assertEqual(item["url"], "https://careers.acmelabs.com/jobs/77")
        self.assertEqual(item["application_url"], "https://careers.acmelabs.com/jobs/77")
        self.assertEqual(len(item["extra_sources"]), 3)
        self.assertEqual(item["posted_date"], (TODAY - timedelta(days=3)).isoformat())

    def test_unconfigured_api_reports_not_configured_and_sends_nothing(self):
        import os
        from app.services.job_sources.job_apis import ADZUNA, read_job_apis
        saved = {k: os.environ.pop(k, None) for k in ADZUNA.env}
        try:
            http = FakeHttp({})
            items, reports = asyncio.run(read_job_apis(http, ["AI Engineer"], apis=[ADZUNA]))
            self.assertEqual(items, [])
            self.assertEqual(reports[0]["state"], "not_configured")
            self.assertEqual(http.calls, [])
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v

    def test_robots_bypass_is_limited_to_keyed_api_hosts(self):
        from app.services.job_sources.safe_http import SafeFetcher
        captured = {}

        async def fake_request(url, *, use_cache, check_robots, accept_any_type):
            captured[url] = check_robots
            return FetchResult(url=url)

        fetcher = SafeFetcher()
        fetcher._request = fake_request
        asyncio.run(fetcher.get("https://api.adzuna.com/v1/api/jobs/in/search/1", robots=False))
        asyncio.run(fetcher.get("https://www.naukri.com/job-listings-1", robots=False))
        self.assertFalse(captured["https://api.adzuna.com/v1/api/jobs/in/search/1"])
        self.assertTrue(captured["https://www.naukri.com/job-listings-1"])


class SourceHealth(unittest.TestCase):
    def test_answered_without_usable_vacancies_is_not_success(self):
        from app.services.job_sources.registry import aggregate, run_state
        stats = aggregate([{"category": "search_engine", "name": "Remote search", "method": "Parallel web_search",
                            "state": "search_successful", "search_results": 10, "unique": 0}])
        self.assertEqual(run_state(stats["search:remote"]), "no_usable_results")
        stats = aggregate([{"category": "search_engine", "name": "Open web", "method": "Parallel web_search",
                            "state": "search_successful", "search_results": 10, "unique": 4}])
        self.assertEqual(run_state(stats["search:web"]), "successful")

    def test_registry_lists_job_apis_and_no_duplicate_hasjob(self):
        from app.services.job_sources.registry import BY_ID
        for sid in ("api:himalayas", "api:adzuna", "api:google-jobs", "feed:hasjob"):
            self.assertIn(sid, BY_ID)
        self.assertNotIn("portal:hasjob", BY_ID)

    def test_schema_v11_migration_preserves_user_activity(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            saved = store.upsert_jobs([{"url": "https://x.test/j/9", "title": "AI Engineer"}])[0]
            store.set_item_state("job", saved["id"], "applied")
            db = sqlite3.connect(store.path)
            try:
                db.execute("PRAGMA user_version = 10")
                db.commit()
            finally:
                db.close()
            again = Store(Path(tmp))
            self.assertIsNotNone(again.backup_path)
            self.assertEqual(again.item_states()["job"][saved["id"]], "applied")
            self.assertEqual(again.jobs()[0]["first_seen"], saved["first_seen"])


if __name__ == "__main__":
    unittest.main()
