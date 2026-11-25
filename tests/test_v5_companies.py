"""v5: company registry — ATS board detection/reading, seeds, scan rotation and coverage.

No network: ATS payloads and career pages are fixtures, and ``scan_due`` receives an injected fetcher.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from app.memory.store import Store
from app.memory.store_parts.companies import SEGMENTS
from app.services import company_seeds
from app.services.ats_sources import DEFAULT_COMPANIES
from app.services.company_registry import scan_due
from app.services.job_sources.ats_readers import Board, WorkdayReader, detect_board
from app.services.job_sources.models import SourceState

TODAY = date(2026, 11, 16)

WORKDAY_PAYLOAD = {
    "total": 1,
    "jobPostings": [{
        "title": "Software Engineer",
        "externalPath": "/job/Bengaluru-India/Software-Engineer_JR-123",
        "locationsText": "Bengaluru, India",
        "postedOn": "Posted 2 Days Ago",
        "bulletFields": ["JR-123"],
    }],
    "facets": [],
}

JOB_LD = json.dumps({
    "@context": "https://schema.org", "@type": "JobPosting", "title": "AI Engineer",
    "url": "/careers/jobs/ai-engineer", "datePosted": "2026-11-01", "validThrough": "2026-12-31",
    "employmentType": "FULL_TIME",
    "hiringOrganization": {"@type": "Organization", "name": "Acme Labs"},
    "jobLocation": {"@type": "Place", "address": {"addressLocality": "Bengaluru", "addressCountry": "IN"}},
    "description": "<p>Build LLM agents with Python and PyTorch.</p>", "identifier": {"value": "AC-7"},
})

CAREERS_PAGE = (f"<html><head><title>Careers at Acme</title></head><body><h1>Open roles</h1>"
                f"<script type='application/ld+json'>{JOB_LD}</script></body></html>")


class WorkdayTests(unittest.TestCase):
    board = Board("workday", "acme.wd5.myworkdayjobs.com/acme", "Acme",
                  "https://acme.wd5.myworkdayjobs.com/en-US/acme")

    def test_endpoint_and_apply_urls_are_built_from_the_tenant(self):
        self.assertEqual(WorkdayReader.endpoint(self.board),
                         "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/acme/jobs")
        self.assertEqual(WorkdayReader.apply_url(WORKDAY_PAYLOAD["jobPostings"][0], self.board),
                         "https://acme.wd5.myworkdayjobs.com/acme/job/Bengaluru-India/Software-Engineer_JR-123")

    def test_payload_is_parsed_with_dates_locations_and_requisition(self):
        jobs = WorkdayReader.parse(WORKDAY_PAYLOAD, self.board, today=TODAY)
        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(job["title"], "Software Engineer")
        self.assertEqual(job["location"], "Bengaluru, India")
        self.assertEqual(job["posted_date"], "2026-11-14")
        self.assertEqual(job["requisition_id"], "JR-123")
        self.assertEqual(job["ats"], "workday")
        self.assertEqual(job["date_source"], "employer job board (relative date)")

    def test_multi_location_label_uses_the_path_city(self):
        payload = {"jobPostings": [{"title": "Data Engineer", "externalPath": "/job/Remote/Data-Engineer_JR-9",
                                    "locationsText": "2 Locations", "postedOn": "Posted Today"}]}
        job = WorkdayReader.parse(payload, self.board, today=TODAY)[0]
        self.assertEqual(job["location"], "Remote (+ other locations)")
        self.assertEqual(job["posted_date"], "2026-11-16")
        self.assertIsNone(job["requisition_id"])

    def test_an_empty_board_is_no_results_not_a_failure(self):
        class Http:
            async def post_json(self, url, body):
                return SimpleNamespace(ok=True, text=json.dumps({"total": 0, "jobPostings": [], "facets": []}),
                                       state=SourceState.FETCH_OK, error=None)

        result = asyncio.run(WorkdayReader().enumerate(Http(), self.board, india_only=False))
        self.assertEqual(result.state, SourceState.NO_RESULTS)
        self.assertTrue(result.ok)
        self.assertEqual(result.jobs, [])


class DetectBoardTests(unittest.TestCase):
    def test_known_ats_references(self):
        self.assertEqual(detect_board("https://acme.wd5.myworkdayjobs.com/en-US/acme/job/x").ats, "workday")
        self.assertEqual(detect_board("https://acme.wd5.myworkdayjobs.com/en-US/acme/job/x").tenant,
                         "acme.wd5.myworkdayjobs.com/acme")
        board = detect_board("<a href='https://boards.greenhouse.io/acme'>Careers</a>")
        self.assertEqual((board.ats, board.tenant), ("greenhouse", "acme"))
        embedded = detect_board("https://boards.greenhouse.io/embed/job_board?for=acme")
        self.assertEqual((embedded.ats, embedded.tenant), ("greenhouse", "acme"))

    def test_reserved_and_unlisted_pages_do_not_produce_a_guard_guess(self):
        self.assertIsNone(detect_board("https://boards.greenhouse.io/www"))
        self.assertIsNone(detect_board("<html>We are hiring. Apply by email.</html>"))
        self.assertIsNone(detect_board("", page_url="https://acme.test/careers"))

    def test_phenom_is_recognised_from_the_company_hosted_page(self):
        board = detect_board("phApp.ddo = {}", page_url="https://careers.acme.test/search")
        self.assertEqual((board.ats, board.tenant), ("phenom", "https://careers.acme.test"))

    def test_detected_tenant_is_never_guessed_from_a_bare_company_domain(self):
        self.assertIsNone(detect_board("Acme Corp careers", page_url="https://acme.test/careers"))


class SeedTests(unittest.TestCase):
    def test_catalogue_is_deduplicated_and_classified(self):
        rows = company_seeds.companies()
        domains = [row["domain"] for row in rows]
        self.assertEqual(len(domains), len(set(domains)))
        self.assertTrue(all(row["name"] and row["domain"] for row in rows))
        self.assertTrue(set(SEGMENTS) >= {row["segment"] for row in rows})

    def test_verified_boards_keep_the_tenant_that_was_verified(self):
        boards = {(row["ats"], row["tenant"]) for row in company_seeds.companies() if row.get("ats")}
        known = {(company["ats"], company["slug"]) for company in DEFAULT_COMPANIES}
        self.assertTrue(boards)
        self.assertTrue(boards <= known)

    def test_summary_reports_the_real_size(self):
        summary = company_seeds.summary()
        rows = company_seeds.companies()
        self.assertEqual(summary["companies"], len(rows))
        self.assertEqual(summary["with_ats"], sum(1 for row in rows if row.get("ats")))
        self.assertEqual(sum(summary["segments"].values()), len(rows))


class RotationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name))
        self.store.seed_companies([
            {"name": "Alpha", "domain": "alpha.test", "segment": "product", "ats": "workday",
             "tenant": "alpha.wd1.myworkdayjobs.com/alpha", "priority": 80},
            {"name": "Beta", "domain": "beta.test", "segment": "gcc", "priority": 90},
            {"name": "Gamma", "domain": "gamma.test", "segment": "startup", "priority": 10},
        ])
        self.ids = {row["name"]: row["id"] for row in self.store.companies()}

    def tearDown(self):
        self.tmp.cleanup()

    def test_due_order_prefers_followed_then_priority_then_unscanned(self):
        due = [row["name"] for row in self.store.companies_due(limit=10)]
        self.assertEqual(due, ["Beta", "Alpha", "Gamma"])
        self.store.update_company(self.ids["Gamma"], followed=1)
        self.assertEqual([row["name"] for row in self.store.companies_due(limit=10)],
                         ["Gamma", "Beta", "Alpha"])
        self.store.update_company(self.ids["Alpha"], enabled=0)
        self.assertNotIn("Alpha", [row["name"] for row in self.store.companies_due(limit=10)])

    def test_success_resets_failures_and_schedules_the_next_scan(self):
        now = datetime(2026, 11, 16, 9, tzinfo=timezone.utc)
        self.store.record_company_scan(self.ids["Alpha"], ok=True, state=SourceState.EXTRACT_OK, jobs=3,
                                       india_jobs=2, now=now)
        row = self.store.company(self.ids["Alpha"])
        self.assertEqual(row["consecutive_failures"], 0)
        self.assertEqual(row["jobs_count"], 3)
        self.assertEqual(row["india_jobs"], 2)
        self.assertEqual(row["last_success_at"], now.isoformat())
        self.assertEqual(row["next_due_at"], (now + timedelta(hours=24)).isoformat())

    def test_failures_back_off_exponentially(self):
        now = datetime(2026, 11, 16, 9, tzinfo=timezone.utc)
        for expected in (1, 2, 3):
            self.store.record_company_scan(self.ids["Beta"], ok=False, state=SourceState.TIMEOUT,
                                           error="timeout", now=now)
            self.assertEqual(self.store.company(self.ids["Beta"])["consecutive_failures"], expected)
        row = self.store.company(self.ids["Beta"])
        due = datetime.fromisoformat(row["next_due_at"])
        self.assertEqual(due, now + timedelta(hours=24 * 2 ** 3))

    def test_coverage_counts_scanned_successful_failing_and_due(self):
        now = datetime(2026, 11, 16, 9, tzinfo=timezone.utc)
        self.store.record_company_scan(self.ids["Alpha"], ok=True, state=SourceState.EXTRACT_OK, jobs=2,
                                       india_jobs=1, now=now)
        for _ in range(3):
            self.store.record_company_scan(self.ids["Beta"], ok=False, state=SourceState.TIMEOUT, now=now)
        coverage = self.store.company_coverage(now=now)
        totals = coverage["totals"]
        self.assertEqual(totals["companies"], 3)
        self.assertEqual(totals["enabled"], 3)
        self.assertEqual(totals["scanned"], 2)
        self.assertEqual(totals["successful"], 1)
        self.assertEqual(totals["failing"], 1)
        self.assertEqual(totals["jobs"], 2)
        self.assertEqual(totals["india_jobs"], 1)
        self.assertEqual(coverage["segments"]["startup"]["companies"], 1)


class ScanTests(unittest.TestCase):
    class Result:
        def __init__(self, url, text, *, ok=True, state=SourceState.FETCH_OK):
            self.url, self.final_url, self.text = url, url, text
            self.ok, self.state, self.error, self.status = ok, state, None, 200

    class Fetcher:
        def __init__(self, pages):
            self.pages, self.calls = pages, []

        async def get(self, url, **_kwargs):
            self.calls.append(url)
            return ScanTests.Result(url, self.pages.get(url, "<html><body>Nothing here</body></html>"))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name))
        self.store.seed_companies([
            {"name": "Acme", "domain": "acme.test", "segment": "product", "priority": 70,
             "careers_url": "https://acme.test/careers", "source": "built-in Indian startup list"},
        ])
        self.company_id = self.store.companies()[0]["id"]
        self.settings = SimpleNamespace(data_dir=Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_scan_stores_career_page_postings_and_records_success(self):
        fetcher = self.Fetcher({"https://acme.test/careers": CAREERS_PAGE})
        summary = asyncio.run(scan_due(self.settings, self.store, {}, only=[self.company_id], fetcher=fetcher))
        self.assertEqual(summary["companies"], 1)
        self.assertEqual(summary["failures"], 0)
        self.assertEqual(summary["stored"], 1)
        self.assertEqual(summary["india_jobs"], 1)
        self.assertEqual(len(summary["new_job_ids"]), 1)
        jobs = self.store.jobs()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["title"], "AI Engineer")
        self.assertEqual(jobs[0]["employer"], "Acme Labs")
        self.assertEqual(jobs[0]["discovered_via"], "company career page")
        row = self.store.company(self.company_id)
        self.assertEqual(row["consecutive_failures"], 0)
        self.assertEqual(row["jobs_count"], 1)
        self.assertIsNotNone(row["last_success_at"])

    def test_a_page_with_no_openings_is_a_successful_empty_scan(self):
        fetcher = self.Fetcher({"https://acme.test/careers": "<html><body><h1>No open roles</h1></body></html>"})
        summary = asyncio.run(scan_due(self.settings, self.store, {}, only=[self.company_id], fetcher=fetcher))
        self.assertEqual(summary["stored"], 0)
        self.assertEqual(summary["failures"], 0)
        row = self.store.company(self.company_id)
        self.assertEqual(row["consecutive_failures"], 0)
        self.assertIsNotNone(row["last_scan_at"])

    def test_a_foreign_role_on_a_career_page_is_not_stored_as_india(self):
        page = CAREERS_PAGE.replace("Bengaluru", "London").replace('"addressCountry": "IN"',
                                                                   '"addressCountry": "GB"')
        fetcher = self.Fetcher({"https://acme.test/careers": page})
        summary = asyncio.run(scan_due(self.settings, self.store, {}, only=[self.company_id], fetcher=fetcher))
        self.assertEqual(summary["stored"], 0)
        self.assertEqual(summary["india_jobs"], 0)
        self.assertEqual(self.store.jobs(), [])


if __name__ == "__main__":
    unittest.main()
