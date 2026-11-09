"""v4 phase 3: posting-date provenance, freshness buckets, no re-fetch 'newness', vacancy fields (fixtures only)."""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.memory.store import Store
from app.services.ats_sources import _parse
from app.services.freshness import date_confidence, freshness_bucket, stronger_date, vacancy_view

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


class FreshnessTests(unittest.TestCase):
    def test_confidence_by_source(self):
        self.assertEqual(date_confidence("employer ATS", "2026-11-01"), "high")
        self.assertEqual(date_confidence("search engine page date", "2026-11-01"), "low")
        self.assertEqual(date_confidence("employer ATS", None), "unknown")
        self.assertTrue(stronger_date("2026-11-02", "high", "2026-10-01", "low"))
        self.assertFalse(stronger_date("2026-11-02", "low", "2026-10-01", "high"))
        self.assertFalse(stronger_date(None, "high", "2026-10-01", "low"))

    def test_buckets_use_trusted_posting_dates_only(self):
        def bucket(**job):
            return freshness_bucket(job, now=NOW, lifecycle_state=job.pop("_state", "unverified"))["key"]
        self.assertEqual(bucket(posted_date="2026-11-09", posted_date_source="employer ATS"), "new_today")
        self.assertEqual(bucket(posted_date="2026-11-08", posted_date_source="employer ATS"), "new_24h")
        self.assertEqual(bucket(posted_date="2026-11-07", posted_date_source="feed entry date"), "new_3d")
        self.assertEqual(bucket(posted_date="2026-11-03", posted_date_source="employer ATS"), "new_7d")
        self.assertEqual(bucket(posted_date="2026-10-01", posted_date_source="employer ATS", _state="open_verified"), "older_open")
        self.assertEqual(bucket(posted_date="2026-10-01", posted_date_source="employer ATS"), "verification_required")
        # A low-confidence search-engine date is not used; first-seen decides, and says so.
        low = freshness_bucket({"posted_date": "2026-11-09", "posted_date_source": "search engine page date",
                                "first_seen": (NOW - timedelta(days=10)).isoformat()}, now=NOW)
        self.assertEqual(low["key"], "date_unknown")
        # v4.3: first-seen is never a publication date; an undated listing is "date unknown", discovered today.
        seen = freshness_bucket({"first_seen": NOW.isoformat()}, now=NOW)
        self.assertEqual(seen["key"], "date_unknown")
        self.assertEqual(seen["label"], "Publication date not disclosed · First discovered today")
        self.assertTrue(seen["newly_discovered"])
        self.assertFalse(seen["newly_published"])
        self.assertEqual(bucket(status="closed"), "closed")
        self.assertEqual(bucket(_state="expired"), "expired")
        self.assertEqual(freshness_bucket({}, now=NOW)["key"], "date_unknown")

    def test_vacancy_view_fields(self):
        view = vacancy_view({"first_seen": "a", "last_seen": "b", "posted_date": "2026-11-01", "posted_date_source": "employer ATS",
                             "original_url": "https://x.test/1", "application_url": "https://x.test/apply"}, "open_verified")
        for key in ("first_seen_at", "last_seen_at", "published_at", "updated_at", "verified_at", "application_deadline",
                    "posting_date_confidence", "verification_status", "vacancy_status", "source_url", "application_url"):
            self.assertIn(key, view)
        self.assertEqual((view["vacancy_status"], view["verification_status"]), ("open", "verified_employer"))
        self.assertEqual(view["posting_date_confidence"], "high")

    def test_greenhouse_updated_at_is_not_a_posting_date(self):
        jobs = _parse({"name": "F", "ats": "greenhouse", "slug": "f"}, {"jobs": [
            {"title": "[TEST] Engineer", "absolute_url": "https://job-boards.greenhouse.io/f/jobs/1",
             "updated_at": "2026-11-08T00:00:00Z", "location": {"name": "Pune"}}]})
        self.assertIsNone(jobs[0]["posted_date"])
        self.assertEqual(jobs[0]["updated_date"], "2026-11-08")


class PersistenceTests(unittest.TestCase):
    def test_refetch_keeps_first_seen_and_never_downgrades_dates(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            record = {"url": "https://jobs.lever.co/fixture/aaaaaaaa-1", "title": "[TEST] Engineer", "employer": "Fixture",
                      "posted_date": "2026-11-01", "posted_date_source": "employer ATS", "status": "open"}
            first = store.upsert_jobs([record])[0]
            again = store.upsert_jobs([{**record, "posted_date": "2026-11-09", "posted_date_source": "search engine page date"}])[0]
            self.assertEqual(again["first_seen"], first["first_seen"])
            self.assertEqual(again["posted_date"], "2026-11-01")
            self.assertEqual(again["posting_date_confidence"], "high")
            weak = store.upsert_jobs([{"url": "https://example.test/j/2", "title": "[TEST] Analyst", "employer": "Other",
                                       "posted_date": "2026-11-05", "posted_date_source": "search engine page date"}])[0]
            self.assertEqual(weak["posting_date_confidence"], "low")
            better = store.upsert_jobs([{"url": "https://example.test/j/2", "title": "[TEST] Analyst", "employer": "Other",
                                         "posted_date": "2026-11-02", "posted_date_source": "JobPosting datePosted"}])[0]
            self.assertEqual((better["posted_date"], better["posting_date_confidence"]), ("2026-11-02", "high"))


if __name__ == "__main__":
    unittest.main()
