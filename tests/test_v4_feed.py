"""v4 phase 5: unified feed — priorities, sections, user actions preserved across scans (fixtures only)."""
from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from app.config import Settings
from app.memory.store import Store
from app.services.feed import build_feed
from app.web import Application, BoundedThreadingHTTPServer

TODAY = date(2026, 11, 9)
NOW = datetime(2026, 11, 9, 9, tzinfo=timezone.utc).isoformat()
OLD = datetime(2026, 10, 1, tzinfo=timezone.utc).isoformat()


def job(id, title, tier="possible", composite=55, bucket="date_unknown", **extra):
    return {"id": id, "title": f"[TEST] {title}", "employer": extra.pop("employer", "Fixture"), "source_kind": "job_listing",
            "eligibility": {"tier": tier, "composite": composite, "level": "eligible", "level_label": "Eligible"},
            "freshness_bucket": {"key": bucket}, "lifecycle": {"state": extra.pop("life", "unverified")},
            "first_seen": extra.pop("first_seen", OLD), "flags": extra.pop("flags", {}), "arrangement": {}, **extra}


class BuildFeedTests(unittest.TestCase):
    def test_priorities_sections_and_exclusions(self):
        jobs = [job(1, "Old good match", composite=60),
                job(2, "New strong match", tier="strong", composite=82, bucket="new_today", first_seen=NOW),
                job(3, "Deadline soon", deadline=(TODAY + timedelta(days=2)).isoformat()),
                job(4, "Followed company role", employer_id=7),
                job(5, "Closed role", life="closed"),
                job(6, "Hidden role"), job(7, "Reported role"),
                job(8, "ML Intern", flags={"intern": True, "fresher": True}),
                job(9, "Stretch role", tier="ineligible", composite=70),
                job(10, "Search page", source_kind="search_page")]
        employers = [{"id": 7, "name": "Followed Co", "followed": 1, "classification": "startup", "country": "India"}]
        notices = [{"id": 1, "post_name": "[TEST] Scientist B", "organization": "Test PSU",
                    "closing_date": (TODAY + timedelta(days=5)).isoformat(), "first_seen": OLD}]
        exams = [{"id": 1, "exam_name": "[TEST] GATE", "event_type": "registration_closes",
                  "event_date": (TODAY + timedelta(days=10)).isoformat()},
                 {"id": 2, "exam_name": "[TEST] Past exam", "event_date": "2026-01-01"}]
        feed = build_feed(jobs=jobs, notices=notices, exams=exams, employers=employers, states={6: "dismissed"},
                          reported={7}, last_visit=datetime(2026, 11, 8, tzinfo=timezone.utc).isoformat(), today=TODAY)
        titles = [i["title"] for i in feed["items"]]
        self.assertEqual(titles[0], "[TEST] New strong match")
        self.assertLess(titles.index("[TEST] Deadline soon"), titles.index("[TEST] Old good match"))
        self.assertLess(titles.index("[TEST] Followed company role"), titles.index("[TEST] Old good match"))
        for missing in ("[TEST] Closed role", "[TEST] Hidden role", "[TEST] Reported role", "[TEST] Search page", "[TEST] Past exam"):
            self.assertNotIn(missing, titles)
        self.assertEqual(titles[-1], "[TEST] Stretch role")
        by_title = {i["title"]: i for i in feed["items"]}
        self.assertIn("internship", by_title["[TEST] ML Intern"]["sections"])
        self.assertIn("followed", by_title["[TEST] Followed company role"]["sections"])
        self.assertIn("startup", by_title["[TEST] Followed company role"]["sections"])
        self.assertIn("government", by_title["[TEST] Scientist B"]["sections"])
        s = feed["summary"]
        self.assertEqual((s["strong_matches"], s["new_since_last_visit"], s["hidden"], s["exam_updates"]), (1, 1, 2, 1))
        self.assertEqual(s["deadlines_14d"], 3)
        everything = build_feed(jobs=jobs, notices=[], exams=[], employers=employers, states={6: "dismissed"},
                                reported={7}, today=TODAY, include_hidden=True)
        self.assertIn("[TEST] Reported role", [i["title"] for i in everything["items"]])

    def test_verified_and_dated_listings_outrank_unverified_undated_ones(self):
        jobs = [job(1, "Unverified undated", composite=62, life="unverified", bucket="date_unknown"),
                job(2, "Verified dated", composite=55, life="open_verified", bucket="last_week")]
        feed = build_feed(jobs=jobs, notices=[], exams=[], employers=[], states={}, reported=set(), today=TODAY)
        self.assertEqual([i["title"] for i in feed["items"]], ["[TEST] Verified dated", "[TEST] Unverified undated"])
        # A much better match still wins: trust adjusts the order, it does not override fit.
        jobs[0]["eligibility"]["composite"] = 95
        feed = build_feed(jobs=jobs, notices=[], exams=[], employers=[], states={}, reported=set(), today=TODAY)
        self.assertEqual(feed["items"][0]["title"], "[TEST] Unverified undated")


class FeedApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "notes").mkdir()
        self.app = Application(Settings(data_dir=root, notes_dir=root / "notes"))
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
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            body = exc.read()
            exc.close()
            return exc.code, json.loads(body or b"{}")

    def test_feed_actions_survive_a_rescan(self):
        store: Store = self.app.store
        record = {"url": "https://jobs.lever.co/fixture/aaaaaaaa-1", "title": "[TEST] Backend Engineer", "employer": "Fixture",
                  "location": "Bengaluru, India", "status": "open", "discovered_via": "company career board",
                  "eligibility": {"tier": "possible", "composite": 60}}
        saved = store.upsert_jobs([record])[0]
        employer, _ = store.upsert_employer({"name": "Fixture"})
        self.assertEqual(self.call("/api/items/state", {"kind": "job", "id": saved["id"], "state": "saved"})[0], 200)
        self.assertEqual(self.call(f"/api/employers/{employer['id']}/follow", {"followed": True})[0], 200)
        status, body = self.call("/api/feed")
        self.assertEqual(status, 200)
        item = next(i for i in body["items"] if i["id"] == saved["id"])
        self.assertEqual(item["state"], "saved")
        for key in ("summary", "deadlines", "news", "today_plan"):
            self.assertIn(key, body)
        # A routine rescan upserts the same listing again: the saved state and follow stay.
        store.upsert_jobs([record])
        store.link_jobs_to_employers()
        body = self.call("/api/feed")[1]
        item = next(i for i in body["items"] if i["id"] == saved["id"])
        self.assertEqual(item["state"], "saved")
        self.assertIn("followed", item["sections"])
        # Reporting hides it from the default feed without deleting it or its saved state.
        self.assertEqual(self.call(f"/api/listings/{saved['id']}/report", {"reason": "closed"})[0], 200)
        self.assertEqual(self.call(f"/api/listings/{saved['id']}/report", {"reason": "bogus"})[0], 400)
        body = self.call("/api/feed")[1]
        self.assertNotIn(saved["id"], [i["id"] for i in body["items"]])
        self.assertEqual(store.item_states()["job"][saved["id"]], "saved")
        self.assertIn(saved["id"], [i["id"] for i in self.call("/api/feed?hidden=1")[1]["items"]])


if __name__ == "__main__":
    unittest.main()
