"""Discover Opportunities: one orchestrated acquisition run feeding one opportunity database.

    load resume + preferences + source state (disabled / backing-off sources are skipped and reported)
    → JobsAdapter        BroadJobSearch: search paths, ATS boards (paginated), career pages,
                         employer discovery/resolution, feeds, dedup, freshness, resume matching, store
    → GovSourceAdapter   official government / PSU / examination sources, polled incrementally (v5):
                         listing pages → new notifications (HTML/PDF) → structured fields → eligibility
    → GovernmentAdapter  search fallback, targeted requests only ("NTPC recruitment")
    → ExamsAdapter       search fallback, targeted requests only
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
import os
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

    # Government and exams are source-first (GovSourceAdapter); the search engine is only their fallback.
    targeted_only = False

    def applies(self, ctx: AcquisitionContext) -> bool:
        sections = (ctx.preferences.get("discovery") or {}).get("sections") or ["jobs", "government", "exams", "news"]
        if self.category not in sections or self.source_id in ctx.skip:
            return False
        if ctx.mode == "targeted":
            from app.services.universal_search import classify_rules
            return self.category in classify_rules(ctx.request)
        if self.targeted_only:
            return False
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
    category, source_id, name, targeted_only = "government", "gov:notices", "Government & PSU (search)", True


class ExamsAdapter(_EngineAdapter):
    category, source_id, name, targeted_only = "exams", "gov:exams", "Exams (search)", True


class GovSourceAdapter:
    """Official government / PSU / examination sources, polled incrementally (app.services.gov_crawler).

    A Discover run reads more due sources than the background scheduler does, and is the only place the
    headless browser and the search provider are used (JavaScript sites, broken TLS chains, blocked sites)."""
    name = "Government & exams"
    source_ids = ()

    def applies(self, ctx: AcquisitionContext) -> bool:
        sections = (ctx.preferences.get("discovery") or {}).get("sections") or ["jobs", "government", "exams", "news"]
        return ctx.mode != "targeted" and bool({"government", "exams"} & set(sections))

    async def acquire(self, ctx: AcquisitionContext) -> AdapterResult:
        from app.services.gov_crawler import GovCrawler
        from app.services.job_sources.browser import BrowserRenderer
        from app.services.job_sources.models import SourceState
        from app.services.job_sources.safe_http import SafeFetcher
        prefs = ctx.preferences.get("government") or {}
        limit = max(1, min(40, int(prefs.get("sources_per_run") or 14)))
        browser = BrowserRenderer(max_pages=1, enabled=bool((ctx.preferences.get("jobs") or {}).get("browser_rendering", True))) \
            if prefs.get("render_sources", True) else None
        retriever = None
        if prefs.get("provider_sources", True):
            try:
                from app.mcp.retrieval import ParallelWebRetriever
                retriever = ParallelWebRetriever(settings=ctx.settings)
                await retriever.__aenter__()
            except Exception:  # the provider is optional: blocked sources are then reported, not fetched
                retriever = None
        llm = None
        if prefs.get("llm_assist", False):
            from app.llm import OllamaProvider
            llm = OllamaProvider(host=ctx.settings.ollama_host, preferred_model=ctx.settings.ollama_model,
                                 timeout=ctx.settings.ollama_timeout)

        def cancel() -> None:
            if ctx.cancelled():
                raise asyncio.CancelledError
        try:
            async with SafeFetcher(cache_path=ctx.settings.data_dir / "http-cache.sqlite3", cache_ttl=0, timeout=25,
                                   max_bytes=2_500_000, concurrency=4) as http:
                crawler = GovCrawler(ctx.store, http, browser=browser, retriever=retriever, llm=llm,
                                     time_budget=float(prefs.get("time_budget_seconds") or 420))
                summary = await crawler.crawl_due(limit=limit, progress=ctx.progress, cancel=cancel, record_registry=False)
        finally:
            if browser is not None:
                await browser.close()
            if retriever is not None:
                try:
                    await retriever.__aexit__(None, None, None)
                except Exception:
                    pass
        reports = []
        for item in summary["sources"]:
            usable = int(item.get("notices_new") or 0) + int(item.get("notices_updated") or 0) + \
                int(item.get("exam_events") or 0) + int(item.get("signals") or 0)
            state = (SourceState.EXTRACT_OK if usable else SourceState.FETCH_OK) if item["ok"] else (
                SourceState.ACCESS_DENIED if item["outcome"] == "blocked" else SourceState.UNAVAILABLE)
            reports.append({"source_id": item["source_id"], "category": "government", "name": item["name"],
                            "method": item["method"], "state": state, "search_results": int(item.get("links") or 0),
                            "listings": usable, "unique": usable, "failure_reason": item.get("error"),
                            "outcome_label": item.get("outcome_label")})
        return AdapterResult(self.name, "complete" if summary["status"] in {"complete", "partial"} else "failed",
                             summary, reports)


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


ADAPTERS = [JobsAdapter, GovSourceAdapter, GovernmentAdapter, ExamsAdapter, NewsAdapter, ReverifyAdapter]


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
                         "rejected": entry.rejected, "stored": entry.stored, "verified": entry.verified,
                         "extraction_ok": entry.extraction_ok, "extraction_total": entry.extraction_total,
                         "failure": "; ".join(dict.fromkeys(entry.failures))[:300] or None}
        self.store.record_source_runs(runs)
        outcome_labels = {r["source_id"]: r["outcome_label"] for r in reports if r.get("outcome_label") and r.get("source_id")}
        from app.services.job_sources import job_apis, portals as portal_policy
        from app.services.preferences import portal_domains
        persisted = self.store.source_states()
        sources = []
        for sid, definition in BY_ID.items():
            run = runs.get(sid)
            api = job_apis.BY_ID.get(sid)
            keyless = api is not None and not api.configured()
            if sid == "extractor:firecrawl":
                keyless = not os.environ.get("FIRECRAWL_API_KEY", "").strip()
                renderer_state = "not_configured" if keyless else "standby"
            else:
                renderer_state = "standby"
            state = run["state"] if run else ("not_configured" if keyless else
                                              "disabled" if ctx.skip.get(sid) == "disabled" else
                                              "backing_off" if sid in ctx.skip else
                                              renderer_state if definition.category == "renderer"
                                              else "not_attempted")
            reason = (run or {}).get("failure") or ctx.skip.get(sid)
            if state == "not_configured" and keyless:
                reason = "Add the key in Settings → API keys"
            elif state == "not_attempted" and definition.category == "job_portal":
                enabled = {d.split("/")[0].removeprefix("www.") for d in portal_domains(self.preferences)}
                portal = next((p for p in portal_policy.PORTALS if p.name == definition.name), None)
                on = portal is not None and any(d in enabled for d in portal.domains)
                reason = ("Queued for a later run (portal searches rotate across runs)" if on
                          else "Disabled in your portal preferences")
            label = RUN_STATE_LABEL[state]
            if sid in outcome_labels and state in {"successful", "no_usable_results", "no_results"}:
                label = "Checked · " + outcome_labels[sid]  # an unchanged listing page is a normal incremental outcome
            sources.append({"id": sid, "name": definition.name, "category": definition.category,
                            "method": definition.method, "state": state, "state_label": label,
                            "results": (run or {}).get("results", 0), "listings": (run or {}).get("listings", 0),
                            "unique": (run or {}).get("unique", 0), "stored": (run or {}).get("stored", 0),
                            "verified": (run or {}).get("verified", 0), "rejected": (run or {}).get("rejected", 0),
                            "last_success_at": (persisted.get(sid) or {}).get("last_success_at"),
                            "reason": reason,
                            "alternative": definition.alternative if state in {"access_restricted", "failed", "search_only",
                                                                               "not_configured"} or
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
            "sources_no_results": sum(1 for s in sources if s["state"] == "no_results"),
            "sources_no_usable_results": sum(1 for s in sources if s["state"] == "no_usable_results"),
            "sources_search_only": sum(1 for s in sources if s["state"] == "search_only"),
            "sources_not_configured": sum(1 for s in sources if s["state"] == "not_configured"),
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
        gov = next((r.summary for r in results if r.name == "Government & exams"), {}) or {}
        metrics.update({"gov_sources_checked": len(gov.get("sources") or []), "gov_notices_new": gov.get("notices_new", 0),
                        "gov_notices_updated": gov.get("notices_updated", 0), "gov_documents_read": gov.get("documents", 0),
                        "gov_signals": gov.get("signals", 0), "gov_exam_events": gov.get("exam_events", 0)})
        return {
            "kind": "discovery", "mode": mode, "request": request, "status": "complete",
            "adapters": [{"name": r.name, "status": r.status, "seconds": r.seconds, "error": r.error,
                          "records": (r.summary or {}).get("records") or (r.summary or {}).get("stored")} for r in results],
            "metrics": metrics, "sources": sources, "reverify": {k: reverify.get(k) for k in
                                                              ("checked", "verified_open", "closed", "expired",
                                                               "unreachable", "not_checked")} if reverify else None,
            "jobs_session_id": jobs.get("session_id"), "new_job_ids": new_ids[:500],
            "new_notice_ids": (gov.get("new_notice_ids") or [])[:200],
        }


def is_government_request(request: str) -> bool:
    return bool(re.search(r"\b(government|govt|psu|sarkari|public sector)\b", request or "", re.I))
