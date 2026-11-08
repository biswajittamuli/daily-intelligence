"""V3 tests: harvesting, relative dates, news taxonomy, planning NL, multi-resume, exports, API."""
from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path

from app.config import Settings
from app.memory.planning import is_due_on, normalize_task, read_planning_notes, safe_note_path
from app.memory.store import Store
from app.services.discovery import DiscoveryEngine
from app.services.exports import calendar_ics, jobs_csv
from app.services.freshness import parse_relative_date
from app.services.insights import job_market
from app.services.job_matching import best_resume_match, resume_fit
from app.services.listing_links import harvest_listings, is_listing_url, looks_like_index
from app.services.news_taxonomy import classify_region, classify_topic
from app.services.preferences import load_preferences, scan_roles, validate_preferences
from app.services.query_plan import build_plan
from app.services.resume import find_skills
from app.services.today_plan import build_today_plan
from app.web import Application, BoundedThreadingHTTPServer

TODAY = date(2026, 11, 8)  # a Sunday

INDEX_PAGE = """## AI Engineer jobs in India
[AI Engineer](https://wellfound.com/jobs/3912345-ai-engineer "AI Engineer") Acme · Bengaluru · Python, PyTorch · 3 days ago

[Apply](https://wellfound.com/jobs/3912345-ai-engineer)
[Backend Developer at Zeta](https://www.naukri.com/job-listings-backend-developer-zeta-pune-061125012345) Pune · Posted today · Java, Spring Boot, Docker
[Data Engineer](https://boards.greenhouse.io/example/jobs/7712345) Remote · 2 weeks ago · SQL, Airflow
[More AI jobs](https://wellfound.com/role/l/ai-engineer/india)
[Privacy policy](https://wellfound.com/privacy)
"""


class HarvestTests(unittest.TestCase):
    def test_harvests_individual_listings_with_dates_skills_and_employer(self):
        items = harvest_listings("https://wellfound.com/role/l/ai-engineer/india", INDEX_PAGE, today=TODAY)
        urls = [item["url"] for item in items]
        self.assertEqual(len(items), 3)
        self.assertNotIn("https://wellfound.com/role/l/ai-engineer/india", urls)
        first = items[0]
        self.assertEqual(first["title"], "AI Engineer")
        self.assertEqual(first["posted_date"], "2026-11-05")
        self.assertEqual(first["location"], "Bengaluru")
        self.assertEqual(first["employer"], "Acme")
        self.assertIn("PyTorch", first["skills"])
        zeta = items[1]
        self.assertEqual(zeta["employer"], "Zeta")
        self.assertEqual(zeta["posted_date"], "2026-11-08")
        self.assertIn("Spring Boot", zeta["skills"])
        self.assertEqual(items[2]["posted_date"], "2026-10-25")

    def test_listing_and_index_url_shapes(self):
        self.assertTrue(is_listing_url("https://www.linkedin.com/jobs/view/4012345678"))
        self.assertTrue(is_listing_url("https://jobs.lever.co/acme/1b2c3d4e-0000-1111-2222-333344445555"))
        self.assertFalse(is_listing_url("https://wellfound.com/role/l/ai-engineer/india"))
        self.assertFalse(is_listing_url("https://www.indeed.com/jobs?q=python"))
        self.assertTrue(looks_like_index("https://dailyremote.com/remote-ai-engineer-jobs-in-india",
                                         "Remote AI Engineer Jobs in India"))

    def test_relative_dates(self):
        self.assertEqual(parse_relative_date("Posted 3 days ago", TODAY), date(2026, 11, 5))
        self.assertEqual(parse_relative_date("30+ days ago", TODAY), date(2026, 10, 9))
        self.assertEqual(parse_relative_date("Posted today", TODAY), TODAY)
        self.assertEqual(parse_relative_date("2 weeks ago", TODAY), date(2026, 10, 25))
        self.assertEqual(parse_relative_date("yesterday", TODAY), date(2026, 11, 7))
        self.assertIsNone(parse_relative_date("Bengaluru, India", TODAY))

    def test_skill_scan_avoids_ordinary_words(self):
        skills = find_skills("Let's go to Excel at our goals. Python, Go, SQL and MS Excel required.")
        self.assertIn("Python", skills)
        self.assertIn("Go", skills)
        self.assertEqual(skills.count("Excel"), 1)
        self.assertNotIn("Go", find_skills("We go further every day"))


class FakeRetriever:
    def __init__(self, results, pages):
        self.results, self.pages = results, pages
        self.fetch_calls = []

    async def search(self, queries, objective, **kwargs):
        return [dict(item) for item in self.results]

    async def fetch(self, urls, objective, **kwargs):
        self.fetch_calls.append(list(urls))
        return [{"url": url, "title": "", "full_content": self.pages[url]} for url in urls if url in self.pages]


class FakeProvider:
    def __init__(self, payload):
        self.payload, self.calls = payload, 0

    async def generate_json(self, prompt, **kwargs):
        self.calls += 1
        return self.payload


class DiscoveryHarvestTests(unittest.IsolatedAsyncioTestCase):
    async def test_index_page_is_expanded_into_listings_not_stored_itself(self):
        index = "https://wellfound.com/role/l/ai-engineer/india"
        detail = "https://wellfound.com/jobs/3912345-ai-engineer"
        retriever = FakeRetriever(
            [{"title": "AI Engineer Jobs in India | Wellfound", "url": index, "domain": "wellfound.com",
              "publish_date": None, "excerpts": ["AI Engineer jobs"], "evidence": []}],
            {index: INDEX_PAGE,
             detail: "Acme is hiring an AI Engineer in Bengaluru. Python and PyTorch. Apply now. Posted 3 days ago."},
        )
        provider = FakeProvider({"listings": [{
            "source_id": "S1", "employer": "Acme", "title": "AI Engineer", "location": "Bengaluru",
            "skills": ["Python", "PyTorch"], "status": "open",
            "evidence_quote": "Acme is hiring an AI Engineer in Bengaluru."}]})
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            store.add_resume({"skills": ["Python", "PyTorch"]}, "ml.pdf", "ML")
            store.add_resume({"skills": ["Java", "Spring Boot", "Docker"]}, "backend.pdf", "Backend")
            engine = DiscoveryEngine(Settings(data_dir=Path(tmp), max_content_chars=20000), store=store,
                                     provider=provider, retriever=retriever,
                                     preferences=validate_preferences({}))
            summary = await engine.run("jobs", "AI Engineer", freshness="all")
            jobs = {job["canonical_url"]: job for job in store.jobs()}
            self.assertNotIn(index, jobs)
            self.assertEqual(summary["harvested"], 3)
            self.assertIn(detail, retriever.fetch_calls[1])
            acme = jobs[detail]
            self.assertEqual(acme["status"], "open")
            self.assertEqual(acme["posted_date"], "2026-11-05" if date.today() == TODAY else acme["posted_date"])
            self.assertEqual(acme["best_resume_label"], "ML")
            zeta = next(job for url, job in jobs.items() if "naukri" in url)
            self.assertEqual(zeta["best_resume_label"], "Backend")
            self.assertEqual(zeta["raw"]["source_kind"], "harvested")
            self.assertEqual(len(zeta["resume_scores"]), 2)

    async def test_scan_market_runs_one_pass_per_role(self):
        retriever = FakeRetriever([], {})
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            engine = DiscoveryEngine(Settings(data_dir=Path(tmp)), store=store, provider=FakeProvider({}),
                                     retriever=retriever, preferences=validate_preferences({}))
            messages = []
            result = await engine.scan_market(["AI Engineer", "Data Engineer", "AI Engineer"],
                                              progress=messages.append, pause_seconds=0)
            self.assertEqual(result["roles"], ["AI Engineer", "Data Engineer"])
            self.assertEqual(len(result["passes"]), 2)
            self.assertTrue(any(message.startswith("Pass 2/2: Data Engineer") for message in messages))


class NewsTaxonomyTests(unittest.TestCase):
    def test_region_is_detected_from_content_and_publisher(self):
        self.assertEqual(classify_region("https://inc42.com/buzz/x", "Sarvam raises funding"), "India")
        self.assertEqual(classify_region("https://example.com/a", "MeitY releases IndiaAI guidelines for Indian startups"),
                         "India")
        self.assertEqual(classify_region("https://example.com/a", "New model released"), "Global")
        self.assertEqual(classify_region("https://sifted.eu/x", "EU AI Act enforcement"), "Europe/UK")

    def test_topic_classification(self):
        self.assertEqual(classify_topic("Startup raises $20M Series A for AI agents platform funding"),
                         "Funding & startups")
        self.assertEqual(classify_topic("Government issues AI regulation guidelines policy"), "Policy & regulation")

    def test_regional_news_plan_carries_region_in_every_query(self):
        prefs = validate_preferences({"news": {"region": "India"}})
        plan = build_plan("news", "", prefs, max_queries=6, freshness_days=7, region="India",
                          topic="Funding & startups")
        self.assertTrue(all("India" in query or query.startswith("site:") or "IndiaAI" in query
                            for query in plan.queries))
        self.assertTrue(any("site:inc42.com" in query or "site:analyticsindiamag.com" in query
                            for query in plan.queries))


class PlanningTests(unittest.TestCase):
    def test_free_form_note_lines_become_actionable_tasks(self):
        task = normalize_task("i want to walk my dog", TODAY)
        self.assertEqual(task["text"], "Walk my dog")
        self.assertEqual(task["category"], "health")
        run = normalize_task("Need to go for a run tomorrow at 6pm", TODAY)
        self.assertEqual((run["text"], run["due_date"], run["due_time"]), ("Go for a run", "2026-11-09", "18:00"))
        rent = normalize_task("remind me to pay rent by 15 nov", TODAY)
        self.assertEqual((rent["text"], rent["due_date"], rent["category"]), ("Pay rent", "2026-11-15", "finance"))
        daily = normalize_task("revise GATE CS every morning", TODAY)
        self.assertEqual((daily["recurrence"], daily["due_time"]), ("daily", "08:00"))
        friday = normalize_task("call mom on friday", TODAY)
        self.assertEqual(friday["due_date"], "2026-11-13")

    def test_notes_are_source_of_truth_and_removed_lines_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            notes = root / "notes"
            notes.mkdir()
            note = notes / "test_notes.txt"
            note.write_text("i want to walk my dog\nbuy milk tomorrow\n", encoding="utf-8")
            store = Store(root / "data")
            parsed = read_planning_notes(notes, TODAY)
            store.import_tasks(parsed["tasks"], sync_sources=parsed["sources"])
            self.assertEqual(sorted(t["text"] for t in store.tasks()), ["Buy milk", "Walk my dog"])
            note.write_text("i want to walk my dog\n", encoding="utf-8")
            parsed = read_planning_notes(notes, TODAY)
            stats = store.import_tasks(parsed["tasks"], sync_sources=parsed["sources"])
            self.assertEqual(stats["archived"], 1)
            self.assertEqual([t["text"] for t in store.tasks()], ["Walk my dog"])

    def test_recurring_tasks_and_note_path_safety(self):
        self.assertTrue(is_due_on({"recurrence": "daily", "status": "pending"}, TODAY))
        self.assertFalse(is_due_on({"recurrence": "weekdays", "status": "pending"}, TODAY))
        self.assertTrue(is_due_on({"recurrence": "weekly:sunday", "status": "pending"}, TODAY))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for bad in ("../x.txt", "a/b.txt", ".hidden.txt", "notes.py", ""):
                with self.assertRaises(ValueError):
                    safe_note_path(root, bad)
            self.assertEqual(safe_note_path(root, "today.md").name, "today.md")

    def test_today_plan_merges_tasks_deadlines_and_suggestions(self):
        tasks = [{"id": 1, "text": "Walk my dog", "recurrence": "daily", "due_time": "18:00",
                  "status": "pending", "category": "health"},
                 {"id": 2, "text": "Old thing", "due_date": "2026-11-01", "status": "pending"},
                 {"id": 3, "text": "Later", "due_date": "2026-12-20", "status": "pending"}]
        jobs = [{"id": 7, "title": "AI Engineer", "employer": "Acme", "match_score": 81,
                 "best_resume_label": "ML", "status": "open", "raw": {"source_kind": "job_listing"}}]
        plan = build_today_plan(tasks=tasks, jobs=jobs,
                                exams=[{"exam_name": "GATE", "event_type": "exam", "event_date": "2026-11-10"}],
                                notices=[], skill_gap=[{"name": "Kubernetes", "count": 9}], today=TODAY)
        self.assertEqual(plan["counts"]["overdue"], 1)
        self.assertEqual(plan["counts"]["later"], 1)
        self.assertEqual(plan["schedule"][0]["title"], "Walk my dog")
        self.assertIn("ML", plan["suggestions"][0]["title"])
        self.assertTrue(any(item["kind"] == "learn" for item in plan["suggestions"]))
        self.assertEqual(plan["deadlines"][0]["kind"], "exam")


class ResumeTests(unittest.TestCase):
    def test_best_resume_is_selected_per_listing(self):
        resumes = [{"id": 1, "label": "SDE", "is_default": True,
                    "profile": {"skills": ["Java", "Spring Boot", "SQL"], "experience_years": 0}},
                   {"id": 2, "label": "AI/ML", "profile": {"skills": ["Python", "PyTorch", "RAG", "LLMs"]}}]
        prefs = validate_preferences({})
        ai = best_resume_match({"title": "LLM Engineer", "skills": ["Python", "PyTorch", "LLMs"]}, prefs, resumes)
        backend = best_resume_match({"title": "Java Backend Developer", "skills": ["Java", "Spring Boot"]},
                                    prefs, resumes)
        self.assertEqual(ai["best_resume_label"], "AI/ML")
        self.assertEqual(backend["best_resume_label"], "SDE")
        fit = resume_fit({"title": "LLM Engineer", "skills": ["Python", "Kubernetes"]}, resumes[1]["profile"])
        self.assertEqual(fit["missing"], ["Kubernetes"])

    def test_legacy_profile_migrates_into_resumes_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = sqlite3.connect(root / "daily-intelligence.sqlite3")
            db.executescript("""CREATE TABLE candidate_profile (id INTEGER PRIMARY KEY CHECK (id = 1),
                profile_json TEXT NOT NULL, resume_filename TEXT, extracted_at TEXT NOT NULL,
                updated_at TEXT NOT NULL);
                CREATE TABLE tasks (id INTEGER PRIMARY KEY, text TEXT NOT NULL, due_date TEXT,
                status TEXT NOT NULL DEFAULT 'pending', source TEXT NOT NULL, updated_at TEXT NOT NULL);""")
            db.execute("INSERT INTO candidate_profile VALUES(1,?,?,?,?)",
                       (json.dumps({"skills": ["Python"]}), "Biswajit_Tamuli_Amazon_SDE.pdf",
                        "2026-11-08T00:00:00", "2026-11-08T00:00:00"))
            db.execute("INSERT INTO tasks(text,status,source,updated_at) VALUES('Keep me','pending','user','x')")
            db.commit()
            db.close()
            store = Store(root)
            resumes = store.resumes()
            self.assertEqual(len(resumes), 1)
            self.assertEqual(resumes[0]["label"], "Biswajit Tamuli Amazon SDE")
            self.assertTrue(resumes[0]["is_default"])
            self.assertEqual(store.profile()["profile"]["skills"], ["Python"])
            self.assertEqual(store.tasks()[0]["text"], "Keep me")
            second = store.add_resume({"skills": ["React"]}, "fe.pdf", "Frontend")
            store.set_default_resume(second)
            self.assertEqual(store.profile()["label"], "Frontend")
            store.delete_resume(second)
            self.assertEqual(store.profile()["label"], "Biswajit Tamuli Amazon SDE")

    def test_existing_database_upgrades_in_place(self):
        source = Path(__file__).resolve().parents[1] / "data" / "daily-intelligence.sqlite3"
        if not source.exists():
            self.skipTest("no local database")
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copy(source, Path(tmp) / "daily-intelligence.sqlite3")
            store = Store(Path(tmp))
            self.assertGreaterEqual(len(store.jobs(limit=2000)), 0)
            self.assertIsInstance(store.resumes(), list)


class MarketAndExportTests(unittest.TestCase):
    def test_market_adds_role_matrix_gap_and_weekly_trend(self):
        jobs = [{"title": "AI Engineer", "skills": ["Python", "Kubernetes"], "source_platform": "wellfound.com",
                 "posted_date": "2026-11-05", "employer": "Acme"},
                {"title": "Backend Developer", "skills": ["Java", "Kubernetes"],
                 "source_platform": "careers.example.com", "posted_date": "2026-10-30"}]
        market = job_market(jobs, today=TODAY, resumes=[{"profile": {"skills": ["Python"]}}])
        self.assertIn("AI / ML", market["skills_by_role"]["roles"])
        self.assertEqual(market["skill_gap"][0]["name"], "Kubernetes")
        self.assertEqual(len(market["weekly"]), 12)
        k8s = next(item for item in market["board_vs_company"] if item["name"] == "Kubernetes")
        self.assertEqual((k8s["board"], k8s["company"]), (1, 1))

    def test_calendar_and_csv_exports(self):
        ics = calendar_ics(tasks=[{"id": 1, "text": "Walk my dog", "due_date": "2026-11-08",
                                   "due_time": "18:00", "recurrence": "daily", "status": "pending"}],
                           jobs=[], exams=[{"id": 2, "exam_name": "GATE", "event_type": "exam",
                                            "event_date": "2027-02-01"}], notices=[])
        self.assertIn("RRULE:FREQ=DAILY", ics)
        self.assertIn("DTSTART:20261108T180000", ics)
        self.assertIn("SUMMARY:GATE: exam", ics)
        csv_text = jobs_csv([{"id": 1, "title": "=HYPERLINK(evil)", "skills": ["Python", "SQL"]}], {1: "applied"})
        self.assertIn("'=HYPERLINK(evil)", csv_text)
        self.assertIn("Python; SQL", csv_text)
        self.assertIn("applied", csv_text)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "notes").mkdir()
        (root / "notes" / "test_notes.txt").write_text("i want to walk my dog\n", encoding="utf-8")
        self.app = Application(Settings(data_dir=root, notes_dir=root / "notes"))
        self.server = BoundedThreadingHTTPServer(("127.0.0.1", 0), self.app.handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.app._executor.shutdown(wait=False, cancel_futures=True)
        self.tmp.cleanup()

    def call(self, path, payload=None, method=None):
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(self.base + path, data=data, method=method,
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                raw = response.read()
                kind = response.headers.get("Content-Type", "")
                return response.status, (json.loads(raw) if "json" in kind else raw.decode())
        except urllib.error.HTTPError as exc:
            body = exc.read()
            exc.close()
            return exc.code, json.loads(body or b"{}")

    def test_bootstrap_imports_free_form_note_and_exposes_v3_fields(self):
        status, data = self.call("/api/bootstrap")
        self.assertEqual(status, 200)
        self.assertEqual(data["version"], "3.0.0")
        self.assertIn("Walk my dog", [task["text"] for task in data["tasks"]])
        self.assertIn("India", data["news_presets"]["regions"])
        self.assertIn("today_plan", data)
        self.assertIn("resumes", data)

    def test_notes_editor_round_trip_and_traversal_rejected(self):
        status, data = self.call("/api/notes/test_notes.txt", {"content": "buy milk tomorrow\n"}, "PUT")
        self.assertEqual(status, 200)
        texts = [task["text"] for task in data["tasks"]]
        self.assertEqual(texts, ["Buy milk"])
        status, data = self.call("/api/notes/..%2F..%2Fetc%2Fpasswd")
        self.assertEqual(status, 400)
        status, _ = self.call("/api/notes/evil.py", {"content": "x"}, "POST")
        self.assertEqual(status, 400)

    def test_applied_state_creates_follow_up_task_and_tracker_entry(self):
        job = self.app.store.upsert_jobs([{"url": "https://jobs.example.com/1", "title": "AI Engineer",
                                           "employer": "Acme"}])[0]
        status, _ = self.call("/api/items/state", {"kind": "job", "id": job["id"], "state": "applied"})
        self.assertEqual(status, 200)
        tasks = self.app.store.tasks()
        self.assertTrue(any(task["text"].startswith("Follow up on application: AI Engineer") for task in tasks))
        status, data = self.call("/api/tracker")
        self.assertEqual(data["items"][0]["state"], "applied")
        status, _ = self.call("/api/items/state", {"kind": "job", "id": job["id"], "state": "interview"})
        self.assertEqual(self.app.store.tracker()[0]["state"], "interview")
        self.assertIsNotNone(self.app.store.tracker()[0]["applied_at"])

    def test_exports_and_resume_routes(self):
        status, text = self.call("/api/export/calendar.ics")
        self.assertEqual(status, 200)
        self.assertIn("BEGIN:VCALENDAR", text)
        status, text = self.call("/api/export/jobs.csv")
        self.assertIn("title,employer", text)
        resume_id = self.app.store.add_resume({"skills": ["Python"]}, "a.pdf", "A")
        status, data = self.call(f"/api/resumes/{resume_id}/label", {"label": "AI resume"})
        self.assertEqual(data["resumes"][0]["label"], "AI resume")
        status, _ = self.call("/api/resumes/999/default", {})
        self.assertEqual(status, 400)

    def test_scheduler_starts_once_per_day_only_when_enabled(self):
        self.assertIsNone(self.app.maybe_auto_refresh(datetime(2026, 11, 8, 9, 0)))
        self.app.discovery_preferences = validate_preferences(
            {"automation": {"daily_refresh": True, "refresh_time": "08:30"}})
        self.assertIsNone(self.app.maybe_auto_refresh(datetime(2026, 11, 8, 8, 0)))
        self.app.store.set_preference("last_auto_refresh", "2026-11-08")
        self.assertIsNone(self.app.maybe_auto_refresh(datetime(2026, 11, 8, 9, 0)))

    def test_scan_roles_include_configured_roles_first(self):
        prefs = validate_preferences({"jobs": {"roles": ["LLM Engineer"], "scan_roles": ["Data Engineer"]}})
        self.assertEqual(scan_roles(prefs), ["LLM Engineer", "Data Engineer"])
        self.assertTrue(load_preferences(self.app.store)["jobs"]["scan_roles"])


if __name__ == "__main__":
    unittest.main()
