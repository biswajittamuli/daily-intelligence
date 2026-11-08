"""V3.1 tests: broad discovery, active-resume ranking, ATS parsing, central search,
resume manager, themes, single instance/health/shutdown and pre-migration backup."""
from __future__ import annotations

import asyncio
import base64
import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from app.config import Settings
from app.memory.store import SCHEMA_VERSION, Store
from app.services.ats_sources import _parse, normalize_company
from app.services.broad_search import BroadJobSearch, _site_query, rescore_stored
from app.services.job_matching import infer_job_titles, location_fit, rank_listing
from app.services.preferences import validate_preferences
from app.services.universal_search import classify, classify_rules
from app.web import Application, BoundedThreadingHTTPServer

RECENT = (date.today() - timedelta(days=3)).isoformat()
PREFS = validate_preferences({"jobs": {"locations": ["India", "Bengaluru"], "experience": "fresher",
                                       "roles": ["AI Engineer"],
                                       "portals": {"Naukri": {"domain": "naukri.com", "enabled": False}}}})
AI_PROFILE = {"skills": ["Python", "PyTorch", "RAG", "FastAPI", "PostgreSQL", "Docker"], "experience_years": 0}
FE_PROFILE = {"skills": ["React", "TypeScript", "JavaScript", "Next.js", "HTML5", "CSS3"], "experience_years": 0}


class FakeRetriever:
    def __init__(self):
        self.searches, self.fetches = [], []

    async def search(self, queries, objective, **kwargs):
        self.searches.append(list(queries))
        if any("site:wellfound.com" in q for q in queries):
            return [{"title": "AI Engineer Jobs in India | Wellfound", "url": "https://wellfound.com/role/l/ai-engineer/india",
                     "domain": "wellfound.com", "publish_date": None, "excerpts": ["AI Engineer jobs"], "evidence": []}]
        return [
            {"title": "AI Engineer at Acme", "url": "https://jobs.acme.in/ai-engineer-1234",
             "domain": "jobs.acme.in", "publish_date": RECENT,
             "excerpts": ["Acme is hiring an AI Engineer in Bengaluru. Python, PyTorch, RAG. 0-1 years experience."],
             "evidence": []},
            {"title": "Why AI hiring is booming in 2026", "url": "https://news.example.com/ai-hiring-trends",
             "domain": "news.example.com", "publish_date": RECENT, "excerpts": ["Hiring trends."], "evidence": []},
        ]

    async def fetch(self, urls, objective, **kwargs):
        self.fetches.append(list(urls))
        page = ("[ML Engineer](https://wellfound.com/jobs/3912345-ml-engineer) Kappa · Bengaluru · Python, PyTorch · 2 days ago\n"
                "[Senior Staff Engineer](https://wellfound.com/jobs/3912346-senior-staff) Kappa · Bengaluru · 1 day ago\n")
        return [{"url": url, "full_content": page} for url in urls if "wellfound.com/role" in url]


async def fake_ats(companies, **kwargs):
    jobs = [
        {"title": "Software Engineer, Backend", "employer": "Zeta", "location": "Bengaluru, India",
         "url": "https://jobs.lever.co/zeta/aaaaaaaa-1111", "posted_date": RECENT,
         "description": "Python FastAPI PostgreSQL Docker. 0-2 years of experience.", "source_platform": "lever:zeta"},
        {"title": "Account Executive", "employer": "Zeta", "location": "Mumbai, India",
         "url": "https://jobs.lever.co/zeta/bbbbbbbb-2222", "posted_date": RECENT, "description": "Sales quota.",
         "source_platform": "lever:zeta"},
        {"title": "Software Engineer", "employer": "Stripe", "location": "San Francisco, United States",
         "url": "https://stripe.com/jobs/3333", "posted_date": RECENT, "description": "Ruby", "remote": "remote",
         "source_platform": "greenhouse:stripe"},
        {"title": "AI Engineer", "employer": "Acme", "location": "Bengaluru",
         "url": "https://boards.greenhouse.io/acme/jobs/4444", "posted_date": RECENT,
         "description": "Python PyTorch RAG", "source_platform": "greenhouse:acme"},
        {"title": "Frontend Engineer", "employer": "Swiggy", "location": "Bangalore, Karnataka",
         "url": "https://careers.swiggy.com/job/5555", "posted_date": RECENT,
         "description": "React TypeScript JavaScript Next.js", "source_platform": "greenhouse:swiggy"},
    ]
    coverage = [{"platform": "Zeta", "method": "lever API", "status": "ok", "results": 2},
                {"platform": "Stripe", "method": "greenhouse API", "status": "ok", "results": 1},
                {"platform": "Ghost", "method": "ashby API", "status": "board not found (404)", "results": 0}]
    return jobs, coverage


class RankingTests(unittest.TestCase):
    def test_india_aware_location_and_remote_restrictions(self):
        self.assertEqual(location_fit("Bangalore, Karnataka", "", ["India", "Bengaluru"])[0], True)
        self.assertEqual(location_fit("Noida, Uttar Pradesh", "", ["India"])[0], True)
        self.assertFalse(location_fit("Remote - US", "", ["India"])[0])
        self.assertTrue(location_fit("Remote, Global", "", ["India"])[0])
        self.assertFalse(location_fit("London, UK", "", ["India"])[0])
        self.assertIsNone(location_fit("", "", ["India"])[0])

    def test_exclusions_are_explicit(self):
        cases = {
            ("Senior Staff Engineer", "Bengaluru", ""): "Seniority too high for your experience",
            ("Account Executive - AI", "Mumbai, India", ""): "Not a technical role for your profile",
            ("Software Engineer", "Bengaluru", "5+ years of experience in Java"): "Requires more experience than you have",
            ("1,200+ AI Engineer Jobs in India", "India", ""): "Job search page, not a single vacancy",
        }
        for (title, loc, text), reason in cases.items():
            result = rank_listing({"title": title, "location": loc, "raw_text": text}, AI_PROFILE, PREFS)
            self.assertEqual(result["tier"], "excluded", title)
            self.assertEqual(result["excluded_reason"], reason)

    def test_active_resume_changes_ranking(self):
        backend = {"title": "Python Backend Developer", "location": "Pune, India", "raw_text": "Python FastAPI PostgreSQL"}
        frontend = {"title": "Frontend Developer", "location": "Pune, India", "raw_text": "React TypeScript Next.js"}
        prefs = validate_preferences({"jobs": {"locations": ["India"], "experience": "fresher"}})
        ai_scores = [rank_listing(job, AI_PROFILE, prefs)["score"] for job in (backend, frontend)]
        fe_scores = [rank_listing(job, FE_PROFILE, prefs)["score"] for job in (backend, frontend)]
        self.assertGreater(ai_scores[0], ai_scores[1])
        self.assertGreater(fe_scores[1], fe_scores[0])
        self.assertIn("AI Engineer", infer_job_titles(AI_PROFILE))
        self.assertIn("Frontend Developer", infer_job_titles(FE_PROFILE))


class BroadSearchTests(unittest.TestCase):
    def test_plan_respects_pool_size_and_bare_domains(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = BroadJobSearch(Settings(data_dir=Path(tmp)), Store(Path(tmp)), PREFS)
            plans = {n: engine.plan("", n) for n in (50, 100, 200)}
            self.assertEqual([plans[n]["search_calls"] for n in (50, 100, 200)], [3, 6, 10])
            groups = [batch.get("group") for batch in plans[50]["batches"]]
            self.assertEqual(groups, ["portal", "career", "web"])
            queries = [q for b in plans[200]["batches"] for q in b["queries"]]
            self.assertFalse(any("site:" in q and "/" in q.split()[0] for q in queries))
            self.assertFalse(any("naukri" in q for q in queries))  # disabled portal is not searched
        self.assertEqual(_site_query("linkedin.com/jobs", "AI Engineer", "India"), "site:linkedin.com AI Engineer jobs India")

    def test_two_stage_pipeline_ranks_dedupes_and_reports_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            store.add_resume(AI_PROFILE, "ai.pdf", "AI", make_default=True)
            retriever = FakeRetriever()
            engine = BroadJobSearch(Settings(data_dir=Path(tmp)), store, PREFS, retriever=retriever,
                                    ats_fetcher=fake_ats)
            summary = asyncio.run(engine.run("", pool_size=50, use_llm=False))
            self.assertEqual(summary["status"], "complete")
            self.assertEqual(summary["search_calls"], 3)
            self.assertEqual(summary["harvested"], 2)
            self.assertEqual(summary["ats_openings"], 5)
            excluded = summary["excluded"]
            self.assertEqual(excluded["Articles / hiring news (not vacancies)"], 1)
            self.assertGreaterEqual(excluded.get("Not a technical role for your profile", 0), 1)
            self.assertGreaterEqual(excluded.get("Seniority too high for your experience", 0), 1)
            self.assertGreaterEqual(excluded.get("Remote role restricted to another country or region", 0), 1)
            jobs = {job["title"]: job for job in store.jobs()}
            self.assertNotIn("Account Executive", jobs)
            self.assertIn("ML Engineer", jobs)
            self.assertIn("Software Engineer, Backend", jobs)
            platforms = {entry["platform"]: entry for entry in summary["coverage"]}
            self.assertEqual(platforms["Ghost"]["status"], "board not found (404)")
            self.assertIn("Wellfound", platforms)
            # Acme's AI Engineer appears on web search and its ATS board: merged, both sources kept.
            acme = [job for job in store.jobs() if job["title"] == "AI Engineer at Acme" or
                    (job["title"] == "AI Engineer" and job["employer"] == "Acme")]
            self.assertTrue(acme)
            self.assertTrue(all((job.get("eligibility") or {}).get("tier") != "excluded" for job in store.jobs()))

    def test_switching_active_resume_reorders_stored_listings(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            ai_id = store.add_resume(AI_PROFILE, "ai.pdf", "AI", make_default=True)
            fe_id = store.add_resume(FE_PROFILE, "fe.docx", "Frontend")
            engine = BroadJobSearch(Settings(data_dir=Path(tmp)), store, PREFS, retriever=FakeRetriever(),
                                    ats_fetcher=fake_ats)
            asyncio.run(engine.run("", pool_size=50, use_llm=False))

            def order():
                jobs = [job for job in store.jobs() if job.get("match_score") is not None]
                return [job["title"] for job in sorted(jobs, key=lambda job: -job["match_score"])]
            ai_order = order()
            store.set_default_resume(fe_id)
            rescore_stored(store, PREFS)
            fe_order = order()
            self.assertNotEqual(ai_order, fe_order)
            self.assertEqual(fe_order[0], "Frontend Engineer")
            self.assertNotEqual(ai_order[0], "Frontend Engineer")
            self.assertTrue(ai_id)


class AtsAndCentralSearchTests(unittest.TestCase):
    def test_ats_payload_parsing(self):
        gh = _parse({"name": "G", "ats": "greenhouse", "slug": "g"}, {"jobs": [
            {"title": "SDE", "absolute_url": "https://boards.greenhouse.io/g/jobs/1", "location": {"name": "Bengaluru, India"},
             "first_published": "2026-11-01T10:00:00-04:00", "content": "&lt;p&gt;Python&lt;/p&gt;"}]})
        self.assertEqual((gh[0]["posted_date"], gh[0]["location"], gh[0]["description"]), ("2026-11-01", "Bengaluru, India", "Python"))
        lever = _parse({"name": "L", "ats": "lever", "slug": "l"}, [
            {"text": "Backend Engineer", "hostedUrl": "https://jobs.lever.co/l/x", "createdAt": 1788866461675,
             "categories": {"location": "Hyderabad", "commitment": "Full-time"}, "descriptionPlain": "Java"}])
        self.assertEqual((lever[0]["title"], lever[0]["employment_type"]), ("Backend Engineer", "Full-time"))
        ashby = _parse({"name": "A", "ats": "ashby", "slug": "a"}, {"jobs": [
            {"title": "ML Engineer", "jobUrl": "https://jobs.ashbyhq.com/a/1", "location": "Delhi", "isRemote": False,
             "publishedAt": "2026-10-01T00:00:00+00:00", "address": {"postalAddress": {"addressCountry": "India"}}},
            {"title": "Hidden", "jobUrl": "https://jobs.ashbyhq.com/a/2", "isListed": False}]})
        self.assertEqual(len(ashby), 1)
        self.assertEqual(ashby[0]["location"], "Delhi, India")
        self.assertIsNone(normalize_company({"ats": "workday", "slug": "x"}))

    def test_intent_rules_and_offline_classification(self):
        self.assertEqual(classify_rules("backend developer jobs in Pune"), ["jobs"])
        self.assertEqual(classify_rules("GATE 2027 exam dates"), ["exams"])
        self.assertIn("news", classify_rules("latest AI startup funding news India"))
        self.assertIn("papers", classify_rules("papers on RAG evaluation benchmark"))
        self.assertIn("government", classify_rules("ISRO government recruitment for CSE"))
        result = asyncio.run(classify("what is the capital of Assam", Settings(), use_model=False))
        self.assertEqual(result["categories"], ["research"])


class StoreUpgradeTests(unittest.TestCase):
    def test_database_is_backed_up_before_schema_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = sqlite3.connect(root / "daily-intelligence.sqlite3")
            db.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY, text TEXT NOT NULL, due_date TEXT, "
                       "status TEXT NOT NULL DEFAULT 'pending', source TEXT NOT NULL, updated_at TEXT NOT NULL)")
            db.execute("INSERT INTO tasks(text,status,source,updated_at) VALUES('Keep me','pending','user','x')")
            db.commit()
            db.close()
            store = Store(root)
            self.assertIsNotNone(store.backup_path)
            backup = sqlite3.connect(store.backup_path)
            self.assertEqual(backup.execute("SELECT text FROM tasks").fetchone()[0], "Keep me")
            backup.close()
            self.assertIsNone(Store(root).backup_path)  # already current: no second backup
            with sqlite3.connect(root / "daily-intelligence.sqlite3") as conn:
                self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)


class ApiV31Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.app = Application(Settings(data_dir=root, notes_dir=root / "notes", ollama_host="http://127.0.0.1:9"))
        self.server = BoundedThreadingHTTPServer(("127.0.0.1", 0), self.app.handler())
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.app._executor.shutdown(wait=False, cancel_futures=True)
        self.tmp.cleanup()

    def call(self, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            body = exc.read()
            exc.close()
            return exc.code, json.loads(body or b"{}")

    def upload(self, name, content, label, default=False):
        return self.call("/api/resume", {"filename": name, "label": label, "make_default": default,
                                         "content_base64": base64.b64encode(content).decode()})

    def test_health_theme_and_shutdown(self):
        status, health = self.call("/api/health")
        self.assertEqual((status, health["app"]), (200, "daily-intelligence"))
        for theme in ("soft-neutral", "minimal-dark", "minimal-light"):
            self.assertEqual(self.call("/api/theme", {"theme": theme})[1]["theme"], theme)
            reloaded = Application(Settings(data_dir=Path(self.tmp.name), notes_dir=Path(self.tmp.name) / "notes"))
            self.assertEqual(reloaded.public_settings()["theme"], theme)
        self.assertEqual(self.call("/api/theme", {"theme": "neon"})[0], 400)
        status, _ = self.call("/api/shutdown", {})
        self.assertEqual(status, 202)
        self.assertTrue(self.app.shutdown_requested.is_set())

    def test_resume_manager_stores_files_shows_errors_and_switches_active(self):
        status, first = self.upload("ai.txt", b"B.Tech 2026. Skills: Python, PyTorch, RAG, FastAPI, PostgreSQL", "AI", True)
        self.assertEqual((status, first["status"]), (200, "processed"))
        status, second = self.upload("fe.txt", b"B.Tech 2025. Skills: React, TypeScript, JavaScript, Next.js, CSS", "Frontend")
        status, broken = self.upload("scan.txt", b"   \n  ", "Scanned")
        self.assertEqual(broken["status"], "error")
        self.assertIn("No readable text", broken["error"])
        resumes = {r["label"]: r for r in self.call("/api/resumes")[1]["resumes"]}
        self.assertTrue(resumes["AI"]["is_active"])
        self.assertTrue(Path(resumes["Frontend"]["stored_path"]).is_file())
        self.assertEqual(resumes["Scanned"]["status"], "error")
        self.assertEqual(self.call(f"/api/resumes/{resumes['Scanned']['id']}/activate", {})[0], 400)
        self.assertEqual(self.call(f"/api/resumes/{second['resume_id']}/activate", {})[0], 200)
        reloaded = Application(Settings(data_dir=Path(self.tmp.name), notes_dir=Path(self.tmp.name) / "notes"))
        self.assertEqual(reloaded.store.profile()["label"], "Frontend")
        status, data = self.call(f"/api/resumes/{second['resume_id']}/reprocess", {})
        self.assertEqual(status, 200)
        self.assertIn("Frontend Developer", next(r for r in data["resumes"] if r["label"] == "Frontend")["profile"]["job_titles"])
        self.call(f"/api/resumes/{resumes['Scanned']['id']}/delete", {})
        self.assertFalse(Path(resumes["Scanned"]["stored_path"]).exists())

    def test_universal_search_validation(self):
        self.assertEqual(self.call("/api/search/universal", {"request": ""})[0], 400)


if __name__ == "__main__":
    unittest.main()
