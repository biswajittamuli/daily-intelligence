"""v4 phase 7: followed-company monitoring, deadline reminders, alerts, scheduler intervals (fixtures only)."""
from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from app.config import Settings
from app.memory.store import Store
from app.services import ats_sources
from app.services.monitoring import check_followed, deadline_reminders, notable_jobs, notify
from app.services.preferences import validate_preferences
from app.web import Application

PREFS = validate_preferences({"jobs": {"locations": ["India"], "roles": ["Backend Engineer"]}})
RECENT = (date.today() - timedelta(days=1)).isoformat()


def board(urls):
    async def fetch(companies, **kwargs):
        jobs = [{"title": f"[TEST] Backend Engineer {i}", "employer": "Fixture", "location": "Bengaluru, India",
                 "url": url, "posted_date": RECENT, "description": "Python Django PostgreSQL. 0-1 years. B.Tech.",
                 "source_platform": "lever:fixture", "ats": "lever"} for i, url in enumerate(urls)]
        return jobs, [{"platform": "Fixture", "ats": "lever", "slug": "fixture", "status": "ok", "complete": True,
                       "results": len(jobs)}]
    return fetch


class FollowedTests(unittest.TestCase):
    def test_followed_board_new_and_removed_vacancies(self):
        ats_sources._CACHE.clear()
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            store.add_resume({"skills": ["Python", "Django", "PostgreSQL"], "experience_years": 0}, "be.pdf", "BE",
                             make_default=True)
            employer, _ = store.upsert_employer({"name": "Fixture", "ats_provider": "lever", "ats_slug": "fixture"})
            store.set_employer_followed(employer["id"], True)
            a, b = "https://jobs.lever.co/fixture/aaaaaaaa-1", "https://jobs.lever.co/fixture/bbbbbbbb-2"
            first = asyncio.run(check_followed(Settings(data_dir=Path(tmp)), store, PREFS, ats_fetcher=board([a, b])))
            self.assertEqual((first["new"], first["stored"]), (2, 2))
            again = asyncio.run(check_followed(Settings(data_dir=Path(tmp)), store, PREFS, ats_fetcher=board([a, b])))
            self.assertEqual(again["new"], 0)  # nothing becomes new by being read again
            asyncio.run(check_followed(Settings(data_dir=Path(tmp)), store, PREFS, ats_fetcher=board([a])))
            asyncio.run(check_followed(Settings(data_dir=Path(tmp)), store, PREFS, ats_fetcher=board([a])))
            status = {j["original_url"]: j["status"] for j in store.jobs()}
            self.assertEqual(status[b], "closed")
            self.assertEqual(status[a], "open")
            self.assertTrue(all(j["employer_id"] == employer["id"] for j in store.jobs()))


class ReminderAndAlertTests(unittest.TestCase):
    def test_deadline_reminders_only_for_tracked_and_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            today = date(2026, 11, 9)
            saved, other = store.upsert_jobs([
                {"url": "https://x.test/1", "title": "[TEST] Saved role", "employer": "A", "deadline": "2026-11-11"},
                {"url": "https://x.test/2", "title": "[TEST] Untracked role", "employer": "B", "deadline": "2026-11-11"}])
            store.set_item_state("job", saved["id"], "saved")
            self.assertEqual(deadline_reminders(store, today=today), 1)
            self.assertEqual(deadline_reminders(store, today=today), 0)
            self.assertTrue(any("Saved role" in t["text"] for t in store.tasks()))

    def test_alerts_threshold_and_dedup(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            rows = store.upsert_jobs([
                {"url": "https://x.test/s", "title": "[TEST] Strong", "match_score": 85,
                 "eligibility": {"tier": "strong", "level": "eligible", "composite": 85}},
                {"url": "https://x.test/u", "title": "[TEST] Uncertain high", "match_score": 90,
                 "eligibility": {"tier": "possible", "level": "uncertain", "composite": 70}},
                {"url": "https://x.test/l", "title": "[TEST] Low", "match_score": 40,
                 "eligibility": {"tier": "low", "level": "eligible", "composite": 40}}])
            notable = notable_jobs(store, [r["id"] for r in rows], PREFS)
            self.assertEqual([j["title"] for j in notable], ["[TEST] Strong"])
            sent = []
            first = notify(store, PREFS, notable, origin="test", sender=lambda title, body: sent.append((title, body)) or True)
            second = notify(store, PREFS, notable, origin="test", sender=lambda title, body: sent.append((title, body)) or True)
            self.assertEqual((first["alerts"], second["alerts"]), (1, 0))
            self.assertEqual(len(sent), 1)
            self.assertIn("[TEST] Strong", sent[0][1])
            quiet = validate_preferences({"automation": {"notify": False}})
            more = store.upsert_jobs([{"url": "https://x.test/s2", "title": "[TEST] Strong 2", "match_score": 88,
                                       "eligibility": {"tier": "strong", "level": "eligible"}}])
            result = notify(store, quiet, more, origin="test", sender=lambda *a: sent.append(a) or True)
            self.assertEqual((result["alerts"], result["desktop"], len(sent)), (1, False, 1))


class SchedulerTests(unittest.TestCase):
    def test_intervals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "notes").mkdir()
            app = Application(Settings(data_dir=root, notes_dir=root / "notes"))
            started = []
            app.start_job = lambda kind, request="", payload=None: (started.append(kind) or "id-" + kind, None)
            self.assertTrue(app.discovery_preferences["automation"]["daily_refresh"])
            morning = datetime(2026, 11, 9, 7, 0)
            self.assertIsNone(app.maybe_auto_refresh(morning))
            self.assertEqual(app.maybe_auto_refresh(datetime(2026, 11, 9, 9, 0)), "id-auto_refresh")
            self.assertIsNone(app.maybe_auto_refresh(datetime(2026, 11, 9, 18, 0)))  # once a day
            self.assertIsNone(app.maybe_followed_check())  # nothing followed
            employer, _ = app.store.upsert_employer({"name": "Fixture"})
            app.store.set_employer_followed(employer["id"], True)
            now = datetime(2026, 11, 9, 9, tzinfo=timezone.utc)
            self.assertEqual(app.maybe_followed_check(now), "id-followed_check")
            self.assertIsNone(app.maybe_followed_check(now + timedelta(hours=2)))
            self.assertEqual(app.maybe_followed_check(now + timedelta(hours=13)), "id-followed_check")
            app._executor.shutdown(wait=False, cancel_futures=True)


if __name__ == "__main__":
    unittest.main()
