"""Daily Intelligence V2 tests: storage, planning, discovery, resume, API, briefing."""
from __future__ import annotations

import io
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

from app.agent.briefing import BriefingService
from app.config import Settings
from app.memory.planning import read_planning_notes
from app.memory.store import Store
from app.services.discovery import DiscoveryEngine
from app.services.freshness import classify_event_date, classify_freshness, parse_date
from app.services.insights import job_market
from app.services.job_matching import score_job
from app.services.preferences import (
    DEFAULT_PORTALS,
    load_preferences,
    portal_domains,
    save_preferences,
    validate_preferences,
)
from app.services.query_plan import build_plan, classify_source
from app.services.resume import (
    extract_profile_deterministic,
    extract_text,
    profile_search_terms,
)
from app.web import Application, BoundedThreadingHTTPServer


def source(title, url, excerpts=None, published=None, domain=None):
    return {
        "title": title,
        "url": url,
        "original_url": url,
        "canonical_url": url,
        "domain": domain or url.split("/")[2],
        "publish_date": published,
        "excerpts": excerpts or [],
        "evidence": [],
    }


class FakeRetriever:
    def __init__(self, results, pages=None, *, search_error=None, fetch_error=None):
        self.results = results
        self.pages = pages or {}
        self.search_error = search_error
        self.fetch_error = fetch_error
        self.search_calls = []
        self.fetch_calls = []

    async def search(self, queries, objective, **kwargs):
        self.search_calls.append({"queries": queries, "objective": objective, **kwargs})
        if self.search_error:
            raise self.search_error
        return [dict(item) for item in self.results]

    async def fetch(self, urls, objective, **kwargs):
        self.fetch_calls.append(list(urls))
        if self.fetch_error:
            raise self.fetch_error
        return [{"url": url, "title": self.pages.get(url, {}).get("title", ""),
                 "full_content": self.pages.get(url, {}).get("content", "")}
                for url in urls if url in self.pages]


class FakeProvider:
    def __init__(self, payload):
        self.payload = payload
        self.prompts = []

    async def generate_json(self, prompt, **kwargs):
        self.prompts.append(prompt)
        return self.payload


class StoreMigrationTests(unittest.TestCase):
    def test_additive_schema_preserves_existing_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            task_id = store.add_task("Keep me", "2026-11-09")
            history_id = store.start_history("briefing", "existing")
            store.finish_history(history_id, {"answer": "kept"})
            store.save_briefing({"date": "2026-11-08"})

            reopened = Store(Path(tmp))
            self.assertEqual(reopened.tasks()[0]["id"], task_id)
            self.assertEqual(reopened.history()[0]["result"]["answer"], "kept")
            self.assertEqual(reopened.briefings()[0]["content"]["date"], "2026-11-08")
            self.assertEqual(reopened.counts(), {"jobs": 0, "notices": 0, "exams": 0,
                                                 "news": 0, "papers": 0})

    def test_preferences_watchlists_profile_and_item_states_persist(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            store.set_preference("discovery_preferences", {"jobs": {"roles": ["AI Engineer"]}})
            self.assertEqual(store.preferences()["discovery_preferences"]["jobs"]["roles"],
                             ["AI Engineer"])
            store.add_watchlist("exam", "GATE")
            store.add_watchlist("organization", "Example PSU")
            self.assertEqual(store.watchlist("exam"), ["GATE"])
            self.assertEqual(store.watchlist("organization"), ["Example PSU"])
            store.remove_watchlist("exam", "GATE")
            self.assertEqual(store.watchlist("exam"), [])
            store.save_profile({"skills": ["Python"]}, "resume.pdf")
            self.assertEqual(store.profile()["profile"]["skills"], ["Python"])
            store.set_item_state("job", 1, "saved")
            self.assertEqual(store.item_states()["job"][1], "saved")

    def test_clear_intel_keeps_tasks_history_and_preferences(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            store.add_task("Keep task")
            store.set_preference("discovery_preferences", {"jobs": {"roles": ["AI"]}})
            store.upsert_jobs([{"url": "https://jobs.example.com/1", "title": "AI Engineer"}])
            removed = store.clear_intel()
            self.assertEqual(removed["job_listings"], 1)
            self.assertEqual(store.counts()["jobs"], 0)
            self.assertEqual(len(store.tasks()), 1)
            self.assertTrue(store.preferences()["discovery_preferences"])


class PreferenceTests(unittest.TestCase):
    def test_defaults_are_editable_and_portals_are_configurable(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            prefs = load_preferences(store)
            self.assertEqual(prefs["jobs"]["roles"], [])
            self.assertIn("Wellfound", prefs["jobs"]["portals"])
            self.assertEqual(portal_domains(prefs)[:1], ["wellfound.com"])

            prefs["jobs"]["portals"]["Wellfound"]["enabled"] = False
            prefs["jobs"]["custom_sites"] = ["careers.example.com"]
            saved = save_preferences(store, prefs)
            self.assertFalse(saved["jobs"]["portals"]["Wellfound"]["enabled"])
            self.assertEqual(saved["jobs"]["custom_sites"], ["careers.example.com"])
            domains = portal_domains(saved)
            self.assertNotIn("wellfound.com", domains)
            self.assertIn("careers.example.com", domains)

    def test_validation_bounds_values_and_keeps_defaults(self):
        clean = validate_preferences({
            "jobs": {"roles": ["AI Engineer", "AI Engineer"], "salary_min": "500000",
                     "salary_max": "not-a-number", "experience": "fresher"},
        })
        self.assertEqual(clean["jobs"]["roles"], ["AI Engineer"])
        self.assertEqual(clean["jobs"]["salary_min"], 500000.0)
        self.assertIsNone(clean["jobs"]["salary_max"])
        self.assertEqual(clean["jobs"]["experience"], "fresher")
        self.assertIn("Wellfound", clean["jobs"]["portals"])


class QueryPlanTests(unittest.TestCase):
    def test_jobs_plan_uses_configured_portals_and_stays_dynamic(self):
        prefs = validate_preferences({"jobs": {
            "roles": ["LLM Engineer"], "locations": ["India"],
            "portals": {**DEFAULT_PORTALS, "Wellfound": {"domain": "wellfound.com", "enabled": True},
                        "Naukri": {"domain": "naukri.com", "enabled": False}},
            "custom_sites": ["careers.example.com"],
        }})
        plan = build_plan("jobs", "", prefs, max_queries=8, freshness_days=30)
        joined = " | ".join(plan.queries)
        self.assertIn("site:wellfound.com", joined)
        self.assertIn("site:careers.example.com", joined)
        self.assertNotIn("site:naukri.com", joined)
        self.assertNotIn("IOCL", joined)
        self.assertNotIn("GATE", joined)
        self.assertEqual(plan.category, "jobs")

    def test_government_and_exam_plans_use_watchlists_not_fixed_results(self):
        prefs = validate_preferences({})
        gov = build_plan("government", "", prefs, organizations=["Example PSU"])
        exams = build_plan("exams", "", prefs, exams=["GATE", "UPSC"])
        self.assertTrue(any("Example PSU" in q for q in gov.queries))
        self.assertTrue(any("GATE" in q for q in exams.queries))
        self.assertTrue(any("UPSC" in q for q in exams.queries))
        self.assertFalse(any("IOCL" in q for q in gov.queries))

    def test_source_classification_separates_listings_from_news(self):
        self.assertEqual(classify_source("jobs", {"url": "https://wellfound.com/jobs/1",
                                                  "title": "AI Engineer"}), "job_listing")
        self.assertEqual(classify_source("jobs", {"url": "https://news.example.com/ai-hiring",
                                                  "title": "Why AI hiring is booming"}), "job_news")
        self.assertEqual(classify_source("government", {"url": "https://example.gov.in/notice.pdf",
                                                        "title": "Notice"}), "official_notice")
        self.assertEqual(classify_source("papers", {"url": "https://arxiv.org/abs/1",
                                                    "title": "Paper"}), "paper")

    def test_job_plan_covers_multiple_configured_roles_and_recent_listings(self):
        prefs = validate_preferences({"jobs": {
            "roles": ["AI Engineer", "LLM Engineer", "Data Engineer"],
            "locations": ["India"], "freshness": "30d",
        }})
        plan = build_plan("jobs", "", prefs, max_queries=8, freshness_days=30)
        joined = " | ".join(plan.queries)
        for role in ("AI Engineer", "LLM Engineer", "Data Engineer"):
            self.assertIn(role, joined)
        self.assertIn("past month", joined)
        self.assertIn("career page", joined)

    def test_news_plan_adds_region_queries(self):
        prefs = validate_preferences({"news": {"region": "India", "interests": ["AI policy"]}})
        plan = build_plan("news", "", prefs, max_queries=6, freshness_days=7)
        joined = " | ".join(plan.queries)
        self.assertIn("India", joined)
        self.assertIn("AI policy", joined)


class FreshnessTests(unittest.TestCase):
    def test_labels_do_not_silently_merge_dates(self):
        today = date(2026, 11, 8)
        recent = classify_freshness(published="2026-11-06", category="news", window="7d", today=today)
        old = classify_freshness(published="2026-01-01", category="news", window="7d", today=today)
        conflict = classify_freshness(published="2026-01-01", updated="2026-11-06",
                                      category="news", window="7d", today=today)
        missing = classify_freshness(category="news", window="7d", today=today)
        self.assertEqual(recent["label"], "recent")
        self.assertEqual(old["label"], "old")
        self.assertEqual(conflict["label"], "date_conflict")
        self.assertEqual(missing["label"], "date_unavailable")

    def test_deadline_status_and_event_date_status(self):
        today = date(2026, 11, 8)
        self.assertEqual(classify_freshness(deadline="2026-12-01", today=today)["deadline_status"], "open")
        self.assertEqual(classify_freshness(deadline="2026-10-01", today=today)["deadline_status"], "closed")
        self.assertEqual(classify_event_date("2027-02-07", "Exam date is tentative",
                                             today=today)["status"], "tentative")
        self.assertEqual(classify_event_date("2027-02-07", "Exam date announced",
                                             today=today)["status"], "announced")
        self.assertIsNone(parse_date("not a date"))


class JobScoringTests(unittest.TestCase):
    def test_score_is_explainable_and_uses_evidence(self):
        prefs = validate_preferences({"jobs": {
            "roles": ["AI Engineer"], "skills": ["Python", "FastAPI"],
            "experience": "fresher", "locations": ["Bengaluru"], "remote": "any",
            "employment_types": ["Full-time"],
        }})
        result = score_job({
            "title": "AI Engineer", "location": "Bengaluru", "remote": "on-site",
            "employment_type": "Full-time", "experience": "0-1 years",
            "skills": ["Python", "FastAPI"], "posted_date": "2026-11-06",
            "raw_text": "AI Engineer Python FastAPI 0-1 years",
        }, prefs, today=date(2026, 11, 8))
        self.assertIsNotNone(result["score"])
        self.assertGreaterEqual(result["score"], 70)
        self.assertIn("Role match", result["reasons_text"])
        self.assertIn("Skill overlap", result["reasons_text"])
        self.assertIn("Location preference matches", result["reasons_text"])

    def test_insufficient_evidence_returns_no_fabricated_percentage(self):
        prefs = validate_preferences({})
        result = score_job({}, prefs, today=date(2026, 11, 8))
        self.assertIsNone(result["score"])
        self.assertEqual(result["confidence"], "insufficient_evidence")


class DiscoveryEngineTests(unittest.IsolatedAsyncioTestCase):
    def engine(self, tmp, retriever, provider, prefs=None):
        store = Store(Path(tmp))
        return DiscoveryEngine(
            Settings(data_dir=Path(tmp), max_content_chars=8000),
            store=store,
            provider=provider,
            retriever=retriever,
            preferences=prefs or load_preferences(store),
        )

    async def test_jobs_run_extracts_listing_and_rejects_news(self):
        listing_url = "https://jobs.example.com/ai-engineer"
        news_url = "https://news.example.com/ai-hiring"
        body = ("Example Labs is hiring an AI Engineer in Bengaluru. Skills: Python and PyTorch. "
                "This is a full-time role. Apply by 2099-12-15. Applications are open.")
        retriever = FakeRetriever(
            [source("AI Engineer at Example Labs", listing_url, ["Example Labs is hiring an AI Engineer."],
                    published="2026-11-01"),
             source("Why AI hiring is booming", news_url, ["Hiring trends in AI."],
                    published="2026-11-05")],
            {listing_url: {"title": "AI Engineer at Example Labs", "content": body}},
        )
        provider = FakeProvider({"listings": [
            {"source_id": "S1", "employer": "Example Labs", "title": "AI Engineer",
             "location": "Bengaluru", "remote": "on-site", "employment_type": "full-time",
             "experience": "0-1 years", "skills": ["Python", "PyTorch"], "salary": "",
             "posted_date": "2026-11-01", "deadline": "2099-12-15", "status": "open",
             "application_url": listing_url,
             "evidence_quote": "Example Labs is hiring an AI Engineer in Bengaluru."},
            {"source_id": "S1", "employer": "Invented Corp", "title": "AI Engineer",
             "evidence_quote": "This quote does not appear anywhere in the page."},
        ]})
        prefs = validate_preferences({"jobs": {"roles": ["AI Engineer"],
                                               "skills": ["Python", "PyTorch"]}})
        with tempfile.TemporaryDirectory() as tmp:
            engine = self.engine(tmp, retriever, provider, prefs)
            summary = await engine.run("jobs", "entry-level AI jobs in India", freshness="all")
            self.assertEqual(summary["status"], "complete")
            self.assertEqual(summary["records"], 1)
            self.assertEqual(summary["filtered"]["off_topic"], 1)
            self.assertEqual(retriever.fetch_calls[0], [listing_url])
            jobs = engine.store.jobs()
            self.assertEqual(len(jobs), 1)
            job = jobs[0]
            self.assertEqual(job["title"], "AI Engineer")
            self.assertEqual(job["employer"], "Example Labs")
            self.assertEqual(job["location"], "Bengaluru")
            self.assertEqual(job["status"], "open")
            self.assertIn("Python", job["skills"])
            self.assertIsNotNone(job["match_score"])
            self.assertIn("Role match", job["match_reason"])
            self.assertEqual(job["original_url"], listing_url)
            self.assertEqual(summary["sources_found"], 2)
            self.assertEqual(summary["pages_fetched"], 1)

    async def test_government_run_extracts_notice_and_cse_eligibility(self):
        url = "https://recruitment.example.gov.in/notice"
        body = ("Example PSU invites applications for Assistant Engineer. "
                "B.Tech Computer Science graduates may apply. Total 42 vacancies. "
                "Closing date 2099-12-01. Advertisement number PSU/2026/01.")
        retriever = FakeRetriever(
            [source("Example PSU recruitment 2026", url, ["Example PSU invites applications."])],
            {url: {"title": "Example PSU recruitment 2026", "content": body}},
        )
        provider = FakeProvider({"notices": [{
            "source_id": "S1", "organization": "Example PSU",
            "advertisement_number": "PSU/2026/01", "post_name": "Assistant Engineer",
            "discipline": "Computer Science", "vacancies": "42",
            "qualifications": "B.Tech Computer Science", "cse_eligibility": "explicitly_eligible",
            "closing_date": "2099-12-01", "document_type": "advertisement",
            "application_url": url,
            "evidence_quote": "B.Tech Computer Science graduates may apply.",
        }]})
        with tempfile.TemporaryDirectory() as tmp:
            engine = self.engine(tmp, retriever, provider)
            summary = await engine.run("government", "PSU vacancies for CSE graduates", freshness="all")
            self.assertEqual(summary["records"], 1)
            notice = engine.store.notices()[0]
            self.assertEqual(notice["organization"], "Example PSU")
            self.assertEqual(notice["cse_eligibility"], "explicitly_eligible")
            self.assertEqual(notice["vacancies"], "42")
            self.assertEqual(notice["status"], "open")
            self.assertEqual(notice["notification_url"], url)

    async def test_extraction_reattributes_misattributed_quote(self):
        pdf_url = "https://gate.example.ac.in/brochure.pdf"
        pdf = ("GATE 2027 dates. Application Portal opening Friday, August 14, 2026. "
               "Results Friday, March 19, 2027. GATE 2027 IIT Madras.")
        provider = FakeProvider({"events": [{
            "source_id": "S1", "exam_name": "GATE 2027",
            "event_type": "application_open", "event_date": "2026-08-14",
            "date_status": "announced", "evidence_quote": "Friday, August 14, 2026",
        }]})
        with tempfile.TemporaryDirectory() as tmp:
            engine = self.engine(tmp, FakeRetriever([]), provider)
            sources = [
                {"url": "https://gate.example.ac.in/", "title": "GATE 2027 official",
                 "source_kind": "exam_notice", "excerpts": ["GATE 2027 important dates"]},
                {"url": pdf_url, "title": "GATE 2027 brochure",
                 "source_kind": "exam_notice", "content": pdf},
            ]
            events = await engine._extract("exams", "GATE 2027 dates", sources)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["_source_url"], pdf_url)
            self.assertEqual(events[0]["event_date"], "2026-08-14")

    async def test_exam_run_keeps_per_event_date_status(self):
        url = "https://gate.example.ac.in/dates"
        body = ("GATE 2027 application closes 2026-09-25. "
                "The examination date is 2027-02-07 (tentative).")
        retriever = FakeRetriever(
            [source("GATE 2027 important dates", url, ["GATE 2027 application closes 2026-09-25."])],
            {url: {"title": "GATE 2027 important dates", "content": body}},
        )
        provider = FakeProvider({"events": [
            {"source_id": "S1", "exam_name": "GATE 2027", "organization": "IIT",
             "event_type": "application_close", "event_date": "2026-09-25",
             "date_status": "announced", "evidence_quote": "GATE 2027 application closes 2026-09-25."},
            {"source_id": "S1", "exam_name": "GATE 2027", "organization": "IIT",
             "event_type": "exam", "event_date": "2027-02-07", "date_status": "tentative",
             "evidence_quote": "The examination date is 2027-02-07 (tentative)."},
        ]})
        with tempfile.TemporaryDirectory() as tmp:
            engine = self.engine(tmp, retriever, provider)
            summary = await engine.run("exams", "GATE 2027 dates", freshness="all")
            self.assertEqual(summary["records"], 2)
            events = {event["event_type"]: event for event in engine.store.exams()}
            self.assertEqual(events["application_close"]["date_status"], "announced")
            self.assertEqual(events["exam"]["date_status"], "tentative")

    async def test_news_and_papers_persist_with_freshness(self):
        news_url = "https://blog.example.com/new-model"
        news_retriever = FakeRetriever(
            [source("New open model released", news_url, ["A new open model was released."],
                    published="2026-11-06")],
            {news_url: {"title": "New open model released",
                        "content": "A new open model was released on 2026-11-06 with faster inference."}},
        )
        news_provider = FakeProvider({"items": [{
            "source_id": "S1", "title": "New open model released",
            "summary": "A new open model was released with faster inference.",
            "why_it_matters": "Faster local inference.", "published_date": "2026-11-06",
            "evidence_quote": "A new open model was released on 2026-11-06 with faster inference.",
        }]})
        with tempfile.TemporaryDirectory() as tmp:
            engine = self.engine(tmp, news_retriever, news_provider)
            summary = await engine.run("news", "AI model release", freshness="all")
            self.assertEqual(summary["records"], 1)
            news = engine.store.intel(category="news")[0]
            self.assertEqual(news["title"], "New open model released")
            self.assertIn(news["freshness"], {"recent", "unverified"})

        paper_url = "https://arxiv.org/abs/2601.00001"
        paper_retriever = FakeRetriever(
            [source("Agent memory benchmark", paper_url, ["We introduce a benchmark."],
                    published="2026-11-04")],
            {paper_url: {"title": "Agent memory benchmark",
                         "content": "We introduce a benchmark for agent memory. "
                                    "Code: https://github.com/example/memory"}},
        )
        paper_provider = FakeProvider({"items": [{
            "source_id": "S1", "title": "Agent memory benchmark", "authors": "A. Researcher",
            "summary": "We introduce a benchmark for agent memory.",
            "why_it_matters": "Comparable agent memory evaluation.",
            "code_url": "https://github.com/example/memory", "peer_reviewed": "not_verified",
            "evidence_quote": "We introduce a benchmark for agent memory.",
        }]})
        with tempfile.TemporaryDirectory() as tmp:
            engine = self.engine(tmp, paper_retriever, paper_provider)
            summary = await engine.run("papers", "agent memory", freshness="all")
            self.assertEqual(summary["records"], 1)
            paper = engine.store.intel(category="papers")[0]
            self.assertEqual(paper["code_url"], "https://github.com/example/memory")
            self.assertEqual(paper["peer_reviewed"], "not_verified")

    async def test_empty_and_failed_searches_are_reported_honestly(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = self.engine(tmp, FakeRetriever([]), FakeProvider({}))
            summary = await empty.run("jobs", "nothing", freshness="all")
            self.assertEqual(summary["status"], "empty")
            self.assertIn("No search results", summary["reason"])
        with tempfile.TemporaryDirectory() as tmp:
            from app.mcp.retrieval import RetrievalError
            failing = self.engine(tmp, FakeRetriever([], search_error=RetrievalError("search down")),
                                  FakeProvider({}))
            with self.assertRaises(RetrievalError):
                await failing.run("jobs", "nothing", freshness="all")
            session = failing.store.search_sessions()[0]
            self.assertEqual(session["status"], "failed")
            self.assertIn("search down", session["error"])

    async def test_fetch_failure_keeps_search_excerpts_and_marks_fallback(self):
        from app.mcp.retrieval import RetrievalError
        url = "https://wellfound.com/jobs/123"
        retriever = FakeRetriever(
            [source("AI Engineer", url, ["AI Engineer role at Example Labs."])],
            fetch_error=RetrievalError("fetch down"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            engine = self.engine(tmp, retriever, FakeProvider({}))
            summary = await engine.run("jobs", "AI jobs", freshness="all")
            self.assertEqual(summary["status"], "complete")
            self.assertEqual(summary["fallback_records"], 1)
            self.assertTrue(summary["errors"])
            job = engine.store.jobs()[0]
            self.assertEqual(job["status"], "unverified")
            self.assertIn("verify", job["match_reason"].lower())


class ResumeTests(unittest.TestCase):
    RESUME = """
    Jane Doe
    B.Tech in Computer Science, 2026
    Skills: Python, PyTorch, FastAPI, Docker, Linux
    Experience: 1 year of experience building LLM applications.
    Projects
    - Built a RAG assistant with FastAPI and PyTorch
    Certifications
    - Deep Learning Specialization
    """

    def test_deterministic_profile_extraction(self):
        profile = extract_profile_deterministic(self.RESUME)
        self.assertEqual(profile["graduation_year"], 2026)
        self.assertEqual(profile["experience_years"], 1)
        self.assertIn("Python", profile["skills"])
        self.assertIn("PyTorch", profile["skills"])
        self.assertIn("B.Tech", " ".join(profile["education"]))
        self.assertTrue(profile["projects"])
        self.assertIn("Python", profile_search_terms(profile))

    def test_docx_text_is_extracted_locally(self):
        from docx import Document
        document = Document()
        document.add_paragraph("B.Tech Computer Science 2026")
        document.add_paragraph("Skills: Python, PyTorch")
        buffer = io.BytesIO()
        document.save(buffer)
        text = extract_text("resume.docx", buffer.getvalue())
        self.assertIn("B.Tech Computer Science", text)
        profile = extract_profile_deterministic(text)
        self.assertIn("Python", profile["skills"])

    def test_unsupported_resume_format_is_rejected(self):
        with self.assertRaises(ValueError):
            extract_text("resume.exe", b"not a resume")


class BriefingAssemblyTests(unittest.IsolatedAsyncioTestCase):
    async def test_briefing_uses_stored_intel_without_live_search(self):
        class ForbiddenAgent:
            async def research(self, *args, **kwargs):
                raise AssertionError("Live research must not run when stored intel exists")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root)
            store.upsert_jobs([{"url": "https://jobs.example.com/1", "title": "AI Engineer",
                                "employer": "Example Labs", "match_score": 82,
                                "match_reason": "Role match", "status": "open"}])
            store.upsert_notices([{"url": "https://psu.example.gov.in/1",
                                   "organization": "Example PSU", "post_name": "Assistant Engineer",
                                   "closing_date": "2099-12-01", "status": "open"}])
            store.upsert_exams([{"url": "https://gate.example.ac.in/1", "exam_name": "GATE 2027",
                                 "event_type": "exam", "event_date": "2099-02-07",
                                 "date_status": "announced"}])
            store.upsert_intel([{"url": "https://blog.example.com/1", "category": "news",
                                 "title": "Model release", "summary": "A release."}])
            service = BriefingService(Settings(data_dir=root, notes_dir=root / "notes"),
                                      store=store, agent=ForbiddenAgent())
            content = await service.generate()
            titles = [section["title"] for section in content["sections"]]
            self.assertIn("New matching jobs", titles)
            self.assertIn("Government and PSU opportunities", titles)
            self.assertIn("Upcoming examination events", titles)
            self.assertEqual(content["execution"]["search_queries"], 0)
            self.assertEqual(content["jobs"][0]["title"], "AI Engineer")
            self.assertTrue(content["deadlines"])
            self.assertTrue(store.briefings())


class ApiWiringTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.app = Application(Settings(data_dir=root, notes_dir=root / "notes"))
        self.server = BoundedThreadingHTTPServer(("127.0.0.1", 0), self.app.handler())
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": 0.05}, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.app._executor.shutdown(wait=False)
        self.tmp.cleanup()

    def request(self, path, payload=None):
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        method = "POST" if data is not None else "GET"
        req = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.status, json.loads(response.read())

    def test_bootstrap_exposes_v2_collections(self):
        status, data = self.request("/api/bootstrap")
        self.assertEqual(status, 200)
        for key in ("counts", "jobs", "notices", "exams", "news", "papers",
                    "item_states", "preferences", "watchlists", "profile",
                    "search_sessions", "settings"):
            self.assertIn(key, data)
        self.assertEqual(data["counts"]["jobs"], 0)

    def test_preferences_watchlists_and_item_state_round_trip(self):
        status, data = self.request("/api/preferences", {"preferences": {
            "jobs": {"roles": ["AI Engineer"], "skills": ["Python"]}}})
        self.assertEqual(status, 200)
        self.assertEqual(data["preferences"]["jobs"]["roles"], ["AI Engineer"])

        _, data = self.request("/api/exams/watchlist", {"name": "GATE"})
        self.assertEqual(data["items"], ["GATE"])
        _, data = self.request("/api/organizations/watchlist", {"name": "Example PSU"})
        self.assertEqual(data["items"], ["Example PSU"])
        _, data = self.request("/api/exams/watchlist", {"name": "GATE", "remove": True})
        self.assertEqual(data["items"], [])

        _, data = self.request("/api/items/state", {"kind": "job", "id": 7, "state": "saved"})
        self.assertTrue(data["ok"])
        _, saved = self.request("/api/saved")
        self.assertEqual(saved["states"]["job"]["7"], "saved")

    def test_intel_profile_export_and_clear_endpoints(self):
        self.app.store.upsert_jobs([{"url": "https://jobs.example.com/1", "title": "AI Engineer"}])
        _, data = self.request("/api/intel?category=jobs")
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["counts"]["jobs"], 1)

        _, data = self.request("/api/resume/profile", {"profile": {
            "skills": ["Python"], "education": ["B.Tech"], "graduation_year": 2026}})
        self.assertEqual(data["profile"]["skills"], ["Python"])
        _, data = self.request("/api/resume")
        self.assertEqual(data["profile"]["profile"]["graduation_year"], 2026)

        _, exported = self.request("/api/export")
        self.assertIn("job_listings", exported)
        _, cleared = self.request("/api/data/clear-intel", {})
        self.assertEqual(cleared["removed"]["job_listings"], 1)
        _, data = self.request("/api/intel?category=jobs")
        self.assertEqual(data["items"], [])

    def test_invalid_category_and_item_state_are_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.request("/api/intel/search", {"category": "unknown", "query": "x"})
        self.assertEqual(context.exception.code, 400)
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.request("/api/items/state", {"kind": "unknown", "id": 1, "state": "saved"})
        self.assertEqual(context.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
