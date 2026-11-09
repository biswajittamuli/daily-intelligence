"""v4 phase 1: unified acquisition — pagination, registry state/backoff, reconciliation, orchestrator.

All HTTP is mocked; records here are labelled test fixtures, never shown as real opportunities.
"""
from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

from app.config import Settings
from app.memory.store import Store
from app.services import ats_sources
from app.services.job_sources.base import AdapterResult, skip_map
from app.services.job_sources.registry import BY_ID, aggregate, backoff_until, run_state, source_id_for
from app.services.orchestrator import DiscoveryOrchestrator
from app.services.verification import reconcile_boards, select_due_for_verification


def lever_handler(total: int):
    def handler(request: httpx.Request) -> httpx.Response:
        skip = int(request.url.params.get("skip", 0))
        limit = int(request.url.params.get("limit", 100))
        items = [{"text": f"[TEST FIXTURE] Engineer {i}", "hostedUrl": f"https://jobs.lever.co/fixture/{i:08d}-aaaa",
                  "categories": {"location": "Bengaluru"}, "createdAt": 1793000000000}
                 for i in range(skip, min(skip + limit, total))]
        return httpx.Response(200, json=items)
    return handler


def smartrecruiters_handler(request: httpx.Request) -> httpx.Response:
    offset = int(request.url.params.get("offset", 0))
    total = 230
    content = [{"id": str(1000000 + i), "name": f"[TEST FIXTURE] Developer {i}", "location": {"city": "Pune", "country": "in"},
                "company": {"identifier": "fixture", "name": "Fixture"}, "releasedDate": "2026-11-01T00:00:00Z"}
               for i in range(offset, min(offset + 100, total))]
    return httpx.Response(200, json={"totalFound": total, "content": content})


class PaginationTests(unittest.TestCase):
    def setUp(self):
        ats_sources._CACHE.clear()

    def run_fetch(self, handler, company):
        async def go():
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                return await ats_sources.fetch_company_jobs([company], client=client)
        return asyncio.run(go())

    def test_lever_reads_every_page(self):
        jobs, coverage = self.run_fetch(lever_handler(250), {"name": "Fixture", "ats": "lever", "slug": "fixture"})
        self.assertEqual(len(jobs), 250)
        self.assertEqual(coverage[0]["pages"], 3)
        self.assertTrue(coverage[0]["complete"])
        self.assertEqual(len({j["url"] for j in jobs}), 250)

    def test_smartrecruiters_uses_offset_and_total(self):
        jobs, coverage = self.run_fetch(smartrecruiters_handler, {"name": "Fixture", "ats": "smartrecruiters", "slug": "fixture"})
        self.assertEqual(len(jobs), 230)
        self.assertEqual(coverage[0]["pages"], 3)

    def test_failure_after_first_page_is_partial_and_not_cached(self):
        def handler(request):
            if int(request.url.params.get("skip", 0)) >= 100:
                return httpx.Response(503)
            return lever_handler(250)(request)
        jobs, coverage = self.run_fetch(handler, {"name": "Fixture", "ats": "lever", "slug": "fixture"})
        self.assertEqual(len(jobs), 100)
        self.assertTrue(coverage[0]["status"].startswith("partial"))
        self.assertFalse(coverage[0].get("complete"))
        self.assertNotIn(("lever", "fixture"), ats_sources._CACHE)


class ReconciliationTests(unittest.TestCase):
    def test_two_fresh_complete_misses_close_a_listing(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            store.upsert_jobs([
                {"url": "https://jobs.lever.co/fixture/aaaaaaaa-1", "title": "[TEST] Kept", "employer": "Fixture",
                 "source_platform": "lever:fixture", "discovered_via": "company career board", "status": "open"},
                {"url": "https://jobs.lever.co/fixture/bbbbbbbb-2", "title": "[TEST] Removed", "employer": "Fixture",
                 "source_platform": "lever:fixture", "discovered_via": "company career board", "status": "open"}])
            board = [{"url": "https://jobs.lever.co/fixture/aaaaaaaa-1"}]
            fresh = [{"ats": "lever", "slug": "fixture", "status": "ok", "complete": True}]
            cached = [{"ats": "lever", "slug": "fixture", "status": "ok (cached)", "complete": True}]
            partial = [{"ats": "lever", "slug": "fixture", "status": "partial: HTTP 503 on page 2"}]
            first = reconcile_boards(store, board, fresh)
            self.assertEqual((first["still_listed"], first["missing_once"], first["closed"]), (1, 1, 0))
            self.assertEqual(reconcile_boards(store, board, cached)["checked"], 0)
            self.assertEqual(reconcile_boards(store, board, partial)["checked"], 0)
            second = reconcile_boards(store, board, fresh)
            self.assertEqual(second["closed"], 1)
            by_title = {j["title"]: j for j in store.jobs()}
            self.assertEqual(by_title["[TEST] Removed"]["status"], "closed")
            self.assertEqual(by_title["[TEST] Kept"]["status"], "open")
            self.assertIsNotNone(by_title["[TEST] Kept"]["last_verified"])

    def test_due_selection_skips_recent_and_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            store.upsert_jobs([
                {"url": "https://example.test/a", "title": "[TEST] Never checked", "status": "unverified", "match_score": 80},
                {"url": "https://example.test/b", "title": "[TEST] Closed", "status": "closed"},
                {"url": "https://example.test/c", "title": "[TEST] Fresh check", "status": "open",
                 "last_verified": datetime.now(timezone.utc).isoformat()}])
            titles = [j["title"] for j in select_due_for_verification(store)]
            self.assertEqual(titles, ["[TEST] Never checked"])


class RegistryTests(unittest.TestCase):
    def test_definitions_cover_portals_ats_and_search_paths(self):
        for sid in ("portal:linkedin-jobs", "portal:indeed", "portal:naukri", "ats:greenhouse", "ats:workday",
                    "search:ats", "career:discovery", "gov:notices"):
            self.assertIn(sid, BY_ID)
        self.assertEqual(BY_ID["portal:linkedin-jobs"].policy, "search_results_only")
        self.assertTrue(BY_ID["portal:linkedin-jobs"].alternative)
        self.assertEqual(BY_ID["ats:lever"].pagination, "offset")

    def test_report_mapping_and_run_states(self):
        reports = [
            {"category": "ats_board", "name": "Zeta", "method": "lever API", "state": "extraction_successful", "listings": 28},
            {"category": "ats_board", "name": "Ghost", "method": "lever API", "state": "not_found", "failure_reason": "404"},
            {"category": "job_portal", "name": "Indeed", "method": "index page fetch", "state": "skipped_by_access_policy",
             "failure_reason": "policy"},
            {"category": "search_engine", "name": "Public ATS boards", "method": "Parallel web_search",
             "state": "rate_limited", "failure_reason": "429"},
        ]
        self.assertEqual(source_id_for(reports[0]), "ats:lever")
        self.assertEqual(source_id_for(reports[2]), "portal:indeed")
        self.assertEqual(source_id_for(reports[3]), "search:ats")
        stats = aggregate(reports)
        self.assertEqual(run_state(stats["ats:lever"]), "partial")
        # v4.3: a portal limited by its terms is reported as such, not as a failure or restriction.
        self.assertEqual(run_state(stats["portal:indeed"]), "search_only")
        self.assertEqual(run_state(stats["search:ats"]), "access_restricted")
        empty = aggregate([{"category": "job_portal", "name": "LinkedIn", "method": "search index only (policy)",
                            "state": "no_results"},
                           {"category": "job_portal", "name": "Hasjob", "method": "public feed",
                            "state": "extraction_successful", "listings": 21}])
        self.assertEqual(run_state(empty["portal:linkedin-jobs"]), "search_only")
        self.assertEqual(run_state(empty["feed:hasjob"]), "successful")
        self.assertNotIn("portal:hasjob", empty)

    def test_backoff_and_skip_map(self):
        now = datetime(2026, 11, 9, tzinfo=timezone.utc)
        self.assertIsNone(backoff_until(2, now=now))
        self.assertEqual(datetime.fromisoformat(backoff_until(3, now=now)) - now, timedelta(hours=6))
        self.assertEqual(datetime.fromisoformat(backoff_until(20, now=now)) - now, timedelta(days=7))
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            for _ in range(3):
                store.record_source_runs({"ats:lever": {"state": "failed", "failure": "timeout"}})
            store.set_source_enabled("portal:naukri", False)
            skips = skip_map(store)
            self.assertIn("backing off", skips["ats:lever"])
            self.assertEqual(skips["portal:naukri"], "disabled")
            self.assertEqual(skips["extractor:firecrawl"], "disabled")  # off by default
            store.record_source_runs({"ats:lever": {"state": "successful", "listings": 5}})
            self.assertNotIn("ats:lever", skip_map(store))


class FakeAdapter:
    def __init__(self, name, *, fail=False, reports=None, applies=True):
        self.name, self.fail, self._reports, self._applies = name, fail, reports or [], applies
        self.source_ids = ()

    def applies(self, ctx):
        return self._applies

    async def acquire(self, ctx):
        if self.fail:
            raise RuntimeError("source down")
        ctx.progress("working")
        return AdapterResult(self.name, "complete", {"records": 1}, self._reports)


class OrchestratorTests(unittest.TestCase):
    def test_one_action_runs_every_adapter_and_isolates_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            reports = [{"category": "ats_board", "name": "Zeta", "method": "lever API", "state": "extraction_successful",
                        "listings": 3, "unique": 3}]
            adapters = [FakeAdapter("Jobs", reports=reports), FakeAdapter("Government & PSU", fail=True),
                        FakeAdapter("Exams", applies=False)]
            messages = []
            report = asyncio.run(DiscoveryOrchestrator(Settings(data_dir=Path(tmp)), store, {}, adapters=adapters)
                                 .discover(progress=messages.append))
            statuses = {a["name"]: a["status"] for a in report["adapters"]}
            self.assertEqual(statuses, {"Jobs": "complete", "Government & PSU": "failed", "Exams": "skipped"})
            self.assertTrue(any(m.startswith("Jobs: working") for m in messages))
            lever = next(s for s in report["sources"] if s["id"] == "ats:lever")
            self.assertEqual(lever["state"], "successful")
            linkedin = next(s for s in report["sources"] if s["id"] == "portal:linkedin-jobs")
            self.assertEqual(linkedin["state"], "not_attempted")  # listed, but never claimed as searched
            self.assertEqual(store.source_states()["ats:lever"]["successes"], 1)
            self.assertEqual(report["mode"], "full")
            self.assertEqual(store.search_sessions(1)[0]["category"], "discovery")


if __name__ == "__main__":
    unittest.main()
