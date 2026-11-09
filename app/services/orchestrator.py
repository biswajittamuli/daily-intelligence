"""Discover Opportunities: one orchestrated acquisition run feeding one opportunity database.

    load resume + preferences + source state (disabled / backing-off sources are skipped and reported)
    → JobsAdapter        BroadJobSearch: search paths, ATS boards (paginated), career pages,
                         employer discovery/resolution, feeds, dedup, freshness, resume matching, store
    → GovernmentAdapter  government & PSU recruitment notices
    → ExamsAdapter       examination notifications
    → NewsAdapter        AI developments (at most once per day)
    → ReverifyAdapter    re-verification of active listings whose check is due
    → registry update, discovery report, notifications

Every section of the UI (jobs, startups, government, exams, news) is a filtered view of what this
run stored; no section needs its own search to be populated. A targeted request ("ML internships
in Pune") runs the same engine with that request and skips the non-job adapters unless the request
names them.
"""
from __future__ import annotations

import asyncio
import re
import time
from datetime import date, datetime, timezone
from typing import Any, Callable

from app.config import Settings
from app.memory.store import Store
from app.services.job_sources.base import AcquisitionContext, AdapterResult, skip_map
from app.services.job_sources.registry import BY_ID, RUN_STATE_LABEL, aggregate, run_state


class JobsAdapter:
    name = "Jobs"
    source_ids = tuple(sid for sid in BY_ID if sid.split(":")[0] in {"search", "ats", "career", "employers", "portal", "feed"})

    def applies(self, ctx: AcquisitionContext) -> bool:
        return True

    async def acquire(self, ctx: AcquisitionContext) -> AdapterResult:
        from app.services.broad_search import BroadJobSearch
        pool = int(ctx.preferences.get("jobs", {}).get("pool_size") or 100)
        # A full or scheduled run also discovers new employers once a day (startup hubs rotate daily).
        employers = None
        if ctx.mode != "targeted" and ctx.store.get_preference("last_employer_discovery") != date.today().isoformat():
            employers = True
            ctx.store.set_preference("last_employer_discovery", date.today().isoformat())
        summary = await BroadJobSearch(ctx.settings, ctx.store, ctx.preferences, skip=ctx.skip,
                                       discover_employers=employers).run(
            ctx.request, pool_size=pool, progress=ctx.progress, cancel_event=ctx.cancel_event)
        reports = (summary.get("acquisition") or {}).get("sources") or []
        return AdapterResult(self.name, "complete" if summary.get("status") in {"complete", "empty"} else "failed",
                             summary, reports)


class _EngineAdapter:
    category = ""
    source_id = ""
    name = ""
    daily = False

    def applies(self, ctx: AcquisitionContext) -> bool:
        sections = (ctx.preferences.get("discovery") or {}).get("sections") or ["jobs", "government", "exams", "news"]
        if self.category not in sections or self.source_id in ctx.skip:
            return False
        if ctx.mode == "targeted":
            from app.services.universal_search import classify_rules
            return self.category in classify_rules(ctx.request)
        if self.daily:
            last = ctx.store.get_preference(f"last_{self.category}_discovery")
            return last != date.today().isoformat()
        return True

    async def acquire(self, ctx: AcquisitionContext) -> AdapterResult:
        from app.services.discovery import DiscoveryEngine
        query = ctx.request if ctx.mode == "targeted" else ""
        summary = await DiscoveryEngine(ctx.settings, ctx.store, preferences=ctx.preferences).run(
            self.category, query, progress=ctx.progress, cancel_event=ctx.cancel_event)
        ctx.store.set_preference(f"last_{self.category}_discovery", date.today().isoformat())
        ok = summary.get("status") in {"complete", "partial", "empty"}
        state = "extraction_successful" if summary.get("records") else ("no_results" if ok else "temporarily_unavailable")
        report = {"source_id": self.source_id, "category": "government" if self.category in {"government", "exams"}
                  else "news", "name": self.name, "method": BY_ID[self.source_id].method, "state": state,
                  "search_results": int(summary.get("sources_found") or 0), "listings": int(summary.get("records") or 0),
                  "unique": int(summary.get("records") or 0),
                  "failure_reason": None if ok else (summary.get("error") or summary.get("reason"))}
        return AdapterResult(self.name, "complete" if ok else "failed", summary, [report])


class GovernmentAdapter(_EngineAdapter):
    category, source_id, name = "government", "gov:notices", "Government & PSU"


class ExamsAdapter(_EngineAdapter):
    category, source_id, name = "exams", "gov:exams", "Exams"


class NewsAdapter(_EngineAdapter):
    category, source_id, name, daily = "news", "news:ai", "AI developments", True


class ReverifyAdapter:
    name = "Re-verification"
    source_ids = ()

    def applies(self, ctx: AcquisitionContext) -> bool:
        return ctx.mode != "targeted"

    async def acquire(self, ctx: AcquisitionContext) -> AdapterResult:
        from app.services.verification import select_due_for_verification, verify_jobs
        limit = int((ctx.preferences.get("automation") or {}).get("reverify_batch") or 30)
        due = select_due_for_verification(ctx.store, limit=limit)
        if not due:
            return AdapterResult(self.name, "skipped", {"checked": 0, "reason": "nothing due"})
        ctx.progress(f"Re-verifying {len(due)} active listings whose check is due")
        result = await verify_jobs(ctx.store, ctx.settings, due, progress=ctx.progress,
                                   cancel=lambda: (_ for _ in ()).throw(asyncio.CancelledError) if ctx.cancelled() else None)
        ctx.store.set_preference("last_reverify", datetime.now(timezone.utc).isoformat())
        return AdapterResult(self.name, "complete", result)


ADAPTERS = [JobsAdapter, GovernmentAdapter, ExamsAdapter, NewsAdapter, ReverifyAdapter]


class DiscoveryOrchestrator:
    def __init__(self, settings: Settings, store: Store, preferences: dict[str, Any], *,
                 adapters: list[Any] | None = None) -> None:
        self.settings = settings
        self.store = store
        self.preferences = preferences
        self.adapters = adapters if adapters is not None else [cls() for cls in ADAPTERS]

    async def discover(self, request: str = "", *, mode: str | None = None,
                       progress: Callable[[str], None] | None = None, cancel_event: Any | None = None) -> dict[str, Any]:
        progress = progress or (lambda _m: None)
        started = time.perf_counter()
        mode = mode or ("targeted" if request.strip() else "full")
        before = self._snapshot()
        ctx = AcquisitionContext(self.settings, self.store, self.preferences, request=request.strip(), mode=mode,
                                 progress=progress, cancel_event=cancel_event, skip=skip_map(self.store))
        session_id = self.store.start_search_session("discovery", request or f"Discover opportunities ({mode})")
        results: list[AdapterResult] = []
        for adapter in self.adapters:
            if ctx.cancelled():
                raise asyncio.CancelledError
            if not adapter.applies(ctx):
                results.append(AdapterResult(adapter.name, "skipped"))
                continue
            progress(f"{adapter.name}: starting")
            t0 = time.perf_counter()
            label = adapter.name
            ctx.progress = lambda message, label=label: progress(f"{label}: {message}")
            try:
                result = await adapter.acquire(ctx)
            except asyncio.CancelledError:
                self.store.update_search_session(session_id, status="cancelled", error="Cancelled by user")
                raise
            except Exception as exc:  # one failing adapter never stops the others
                result = AdapterResult(adapter.name, "failed", error=f"{type(exc).__name__}: {str(exc)[:200]}")
            finally:
                ctx.progress = progress
            result.seconds = round(time.perf_counter() - t0, 1)
            results.append(result)
            progress(f"{adapter.name}: {result.status}")
        report = self._report(results, ctx, before, mode, request)
        report["duration_seconds"] = round(time.perf_counter() - started, 1)
        report["session_id"] = session_id
        self.store.update_search_session(session_id, status="complete", summary=report)
        self.store.set_preference("last_discovery", {"at": datetime.now(timezone.utc).isoformat(), "mode": mode,
                                                     "session_id": session_id})
        return report

    # ------------------------------------------------------------ report
    def _snapshot(self) -> dict[str, Any]:
        with self.store.connect() as db:
            ids = {row["id"] for row in db.execute("SELECT id FROM job_listings")}
        return {"job_ids": ids}

    def _report(self, results: list[AdapterResult], ctx: AcquisitionContext, before: dict[str, Any], mode: str,
                request: str) -> dict[str, Any]:
        reports = [r for result in results for r in result.reports]
        stats = aggregate(reports)
        runs: dict[str, dict[str, Any]] = {}
        for sid, entry in stats.items():
            state = run_state(entry)
            runs[sid] = {"state": state, "results": entry.results, "listings": entry.listings, "unique": entry.unique,
                         "extraction_ok": entry.extraction_ok, "extraction_total": entry.extraction_total,
                         "failure": "; ".join(dict.fromkeys(entry.failures))[:300] or None}
        self.store.record_source_runs(runs)
        sources = []
        for sid, definition in BY_ID.items():
            run = runs.get(sid)
            state = run["state"] if run else ("disabled" if ctx.skip.get(sid) == "disabled" else
                                              "backing_off" if sid in ctx.skip else
                                              "not_configured" if definition.category == "renderer" else "not_attempted")
            sources.append({"id": sid, "name": definition.name, "category": definition.category,
                            "method": definition.method, "state": state, "state_label": RUN_STATE_LABEL[state],
                            "results": (run or {}).get("results", 0), "listings": (run or {}).get("listings", 0),
                            "unique": (run or {}).get("unique", 0), "reason": (run or {}).get("failure") or ctx.skip.get(sid),
                            "alternative": definition.alternative if state in {"access_restricted", "failed"} or
                            definition.policy == "search_results_only" else "", "access": definition.access})
        jobs = next((r.summary for r in results if r.name == "Jobs"), {}) or {}
        funnel = {row["stage"]: row["count"] for row in (jobs.get("acquisition") or {}).get("funnel_stages") or []}
        with self.store.connect() as db:
            new_ids = [row["id"] for row in db.execute("SELECT id FROM job_listings") if row["id"] not in before["job_ids"]]
        stored = self.store.jobs(limit=5000)
        from app.services.verification import lifecycle
        session_jobs = [j for j in stored if j["id"] in set(new_ids)]
        life = [lifecycle(j)["state"] for j in session_jobs]
        counts = lambda states: sum(1 for item in life if item in states)
        acquisition = jobs.get("acquisition") or {}
        career_pages = sum(1 for r in acquisition.get("sources") or [] if r.get("category") == "career_page"
                           and r.get("state") in {"extraction_successful", "partially_successful"})
        boards = sum(1 for r in acquisition.get("sources") or [] if r.get("category") == "ats_board"
                     and r.get("state") in {"extraction_successful", "partially_successful", "no_results"})
        metrics = {
            "sources_configured": len([s for s in sources if s["state"] not in {"disabled"}]),
            "sources_attempted": sum(1 for s in sources if s["state"] not in {"not_attempted", "disabled", "backing_off",
                                                                              "not_configured"}),
            "sources_successful": sum(1 for s in sources if s["state"] == "successful"),
            "sources_partial": sum(1 for s in sources if s["state"] == "partial"),
            "sources_restricted": sum(1 for s in sources if s["state"] in {"access_restricted", "failed"}),
            "search_results": funnel.get("search_results", 0),
            "career_pages_discovered": career_pages,
            "ats_boards_read": boards,
            "raw_vacancy_records": funnel.get("listings_extracted", 0),
            "unique_vacancies": jobs.get("unique_candidates", 0),
            "relevant_vacancies": funnel.get("relevant_jobs", 0),
            "stored_vacancies": jobs.get("stored", 0),
            "new_vacancies": len(new_ids),
            "new_verified_open": counts({"open_verified"}),
            "new_awaiting_verification": counts({"pending_verification", "unverified", "open_page_checked"}),
            "new_closed_or_expired": counts({"closed", "expired"}),
            "board_removals_detected": (jobs.get("reconciliation") or {}).get("closed", 0),
        }
        reverify = next((r.summary for r in results if r.name == "Re-verification"), {}) or {}
        return {
            "kind": "discovery", "mode": mode, "request": request, "status": "complete",
            "adapters": [{"name": r.name, "status": r.status, "seconds": r.seconds, "error": r.error,
                          "records": (r.summary or {}).get("records") or (r.summary or {}).get("stored")} for r in results],
            "metrics": metrics, "sources": sources, "reverify": {k: reverify.get(k) for k in
                                                              ("checked", "verified_open", "closed", "expired",
                                                               "unreachable", "not_checked")} if reverify else None,
            "jobs_session_id": jobs.get("session_id"), "new_job_ids": new_ids[:500],
        }


def is_government_request(request: str) -> bool:
    return bool(re.search(r"\b(government|govt|psu|sarkari|public sector)\b", request or "", re.I))
