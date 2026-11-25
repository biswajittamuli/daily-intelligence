"""Company registry scanner (v5): read due company career boards through the public ATS readers.

The registry row decides *where* to look, never *what* is there:

    companies_due()  → one small batch of companies whose next_due_at has passed
      ├─ known ATS + tenant  → READERS[ats].enumerate()   (public, unauthenticated board)
      └─ no ATS yet          → fetch the careers page, detect the board from its own markup,
                               save the detected tenant, then read it; otherwise read the page
                               as an ordinary career page (schema.org JobPosting / job links)

Every request goes through ``SafeFetcher`` (robots.txt, per-host pacing, private-network blocking). A tenant is
never guessed: it is only stored when the company's own careers page names it. A scan that produced no usable
records is not recorded as a success.

The scan stores listings through the same normaliser as BroadJobSearch (``BroadJobSearch._record`` →
``Store.upsert_jobs``), so company jobs participate in cross-source dedup, freshness and resume ranking exactly
like every other listing. One ``rescore_stored`` pass runs after the batch, not once per company.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlparse

from app.services.job_sources.ats_readers import READERS, Board, detect_board, is_india
from app.services.job_sources.models import SourceState
from app.services.job_sources.safe_http import SafeFetcher
from app.services.job_sources.structured import job_postings, page_links

CADENCE_HOURS = 24.0
COMPANY_CONCURRENCY = 3
MAX_CAREER_JOBS = 80


def _record(item: dict[str, Any]) -> dict[str, Any]:
    from app.services.broad_search import BroadJobSearch
    return BroadJobSearch._record(item)


def _career_listing(company: dict[str, Any], job: dict[str, Any], page_url: str) -> dict[str, Any] | None:
    """Normalise one schema.org / page-link job from a company's own careers page."""
    url = str(job.get("url") or "").strip()
    title = str(job.get("title") or "").strip()
    if not url.startswith("https://") or not title:
        return None
    host = urlparse(url).hostname or ""
    text = str(job.get("description") or job.get("raw_text") or "")
    return {"title": title[:200], "url": url, "employer": job.get("employer") or company["name"],
            "location": job.get("location"), "remote": job.get("remote"),
            "employment_type": job.get("employment_type"), "posted_date": job.get("posted_date"),
            "deadline": job.get("deadline"), "salary": job.get("salary"),
            "salary_currency": job.get("salary_currency"), "education": job.get("education"),
            "experience": job.get("experience"), "requisition_id": job.get("requisition_id"),
            "skills": job.get("skills") or [],
            "raw_text": text[:8000], "source_platform": host,
            "discovered_via": "company career page", "source_kind": "job_listing",
            "status_hint": "open", "date_source": job.get("date_source") or (
                "JobPosting datePosted" if job.get("posted_date") else None),
            "extraction_method": job.get("extraction_method") or "career page job link",
            "application_url": url, "evidence": [{"text": text[:300], "source_url": url}],
            "_career_page": page_url}


def _ats_listing(company: dict[str, Any], board: Board, job: dict[str, Any]) -> dict[str, Any] | None:
    """Normalise one job returned by a public ATS board."""
    url, title = str(job.get("url") or "").strip(), str(job.get("title") or "").strip()
    if not url.startswith("https://") or not title:
        return None
    text = str(job.get("description") or "")
    return {"title": title[:200], "url": url, "employer": job.get("employer") or company["name"],
            "location": job.get("location"), "remote": job.get("remote"),
            "employment_type": job.get("employment_type"), "posted_date": job.get("posted_date"),
            "deadline": job.get("valid_through"), "salary": job.get("salary"),
            "salary_currency": job.get("salary_currency"), "education": job.get("education"),
            "experience": job.get("experience"), "requisition_id": job.get("requisition_id"),
            "country": job.get("country"), "skills": job.get("skills") or [], "raw_text": text[:8000],
            "source_platform": board.platform, "discovered_via": "company career board",
            "source_kind": "job_listing", "status_hint": "open",
            "date_source": job.get("date_source") or ("employer job board" if job.get("posted_date") else None),
            "extraction_method": job.get("extraction_method") or f"{board.ats} public job board",
            "application_url": job.get("application_url") or job.get("url"),
            "ats_ref": board.platform, "evidence": [{"text": text[:300], "source_url": url}]}


async def _careers_page_jobs(http: SafeFetcher, company: dict[str, Any], url: str,
                             cancel: Callable[[], None]) -> tuple[list[dict[str, Any]], str, str | None, Board | None]:
    """Read a careers page: detect an ATS from its markup; otherwise take its schema.org postings and job links."""
    cancel()
    result = await http.get(url)
    if not result.ok or not result.text:
        return [], result.state, result.error, None
    board = detect_board(result.text, name=company["name"], page_url=result.final_url or url)
    if board is not None:
        return [], result.state, None, board
    page_url = result.final_url or url
    host = urlparse(page_url).hostname or ""
    jobs: list[dict[str, Any]] = []
    for job in job_postings(result.text, page_url):
        listing = _career_listing(company, job, page_url)
        if listing:
            jobs.append(listing)
    if not jobs:
        from app.services.job_sources.structured import ROLE_HINT
        for link in page_links(page_url, result.text, limit=600):
            href, label = str(link.get("url") or ""), str(link.get("text") or "")
            if not href.startswith("https://") or urlparse(href).hostname != host:
                continue
            if not ROLE_HINT.search(label):
                continue
            listing = _career_listing(company, {"title": label, "url": href}, page_url)
            if listing:
                jobs.append(listing)
            if len(jobs) >= MAX_CAREER_JOBS:
                break
    return jobs[:MAX_CAREER_JOBS], result.state, result.error, None


async def _discover_careers(http: SafeFetcher, company: dict[str, Any], url: str,
                            cancel: Callable[[], None]) -> dict[str, Any]:
    """Static careers-page discovery for a company whose root URL yielded nothing. Never uses a browser or search."""
    cancel()
    try:
        from app.services.job_sources.career_discovery import CareerDiscovery
        return await CareerDiscovery(http, max_sitemaps=2, verify_candidates=1).run(
            company["name"], url, allow_browser=False, allow_search=False)
    except asyncio.CancelledError:
        raise
    except Exception:  # discovery is a best effort; the scan already has its own state
        return {}


async def _scan_one(http: SafeFetcher, store: Any, company: dict[str, Any], *,
                    cancel: Callable[[], None], progress: Callable[[str], None]) -> dict[str, Any]:
    """Scan one registry row. Returns its report and the normalised listings it produced."""
    cancel()
    row = dict(company)
    report: dict[str, Any] = {"company": row["name"], "id": row["id"], "segment": row.get("segment"),
                              "ats": row.get("ats"), "state": SourceState.NO_RESULTS, "jobs": 0,
                              "india_jobs": 0, "error": None, "pages": 0, "ok": False}
    board = Board(row["ats"], row["tenant"], row["name"], row.get("careers_url") or "") \
        if row.get("ats") and row.get("tenant") and row.get("ats") in READERS else None
    jobs: list[dict[str, Any]] = []
    state: str = SourceState.NO_RESULTS
    error: str | None = None
    try:
        if board is None:
            careers_url = str(row.get("careers_url") or "").strip()
            if not careers_url:
                site = str(row.get("domain") or "").strip()
                careers_url = f"https://{site}" if site else ""
            if not careers_url.startswith("https://"):
                report.update(state=SourceState.UNSUPPORTED, error="no verified careers URL")
                return {**report, "listings": []}
            page_jobs, state, error, detected = await _careers_page_jobs(http, row, careers_url, cancel)
            if detected is not None:
                # The company's own page named its ATS: persist the detected tenant and read the board.
                board = Board(detected.ats, detected.tenant, row["name"], detected.careers_url or careers_url)
                store.update_company(row["id"], ats=board.ats, tenant=board.tenant,
                                     careers_url=board.careers_url or careers_url)
                report["ats"] = board.ats
            else:
                jobs = page_jobs
                report.update(pages=1)
                if not jobs:
                    # A homepage/root URL often hides the careers page. Static multi-stage discovery finds it
                    # without a browser or a search provider; it never guesses an ATS tenant.
                    found = await _discover_careers(http, row, careers_url, cancel)
                    if found.get("career_url") and found["career_url"] != careers_url:
                        store.update_company(row["id"], careers_url=found["career_url"])
                        page_jobs, state, error, detected = await _careers_page_jobs(
                            http, row, found["career_url"], cancel)
                        if detected is not None:
                            board = Board(detected.ats, detected.tenant, row["name"],
                                          detected.careers_url or found["career_url"])
                            store.update_company(row["id"], ats=board.ats, tenant=board.tenant)
                            report["ats"] = board.ats
                        else:
                            jobs = page_jobs or [_career_listing(row, item, found["career_url"])
                                                 for item in (found.get("listings") or [])]
                            jobs = [item for item in jobs if item]
                            report.update(pages=report.get("pages", 0) + 1)
        if board is not None:
            reader = READERS.get(board.ats)
            if reader is None or not reader.public:
                # No public feed for this ATS: the ordinary career page was already read where possible.
                if not jobs:
                    careers_url = str(row.get("careers_url") or "").strip()
                    if careers_url.startswith("https://"):
                        page_jobs, state, error, _ = await _careers_page_jobs(http, row, careers_url, cancel)
                        jobs = page_jobs
                        report.update(pages=1)
            else:
                result = await reader.enumerate(http, board, india_only=True)
                state, error, report["pages"] = result.state, result.error, result.pages
                jobs = [listing for listing in (_ats_listing(row, board, job) for job in result.jobs) if listing]
                if not result.ok and not jobs:
                    report.update(state=state, error=error)
                    return {**report, "listings": []}
                # A public board that answered but had no India role is a successful empty scan, not a failure.
                if result.state == SourceState.NO_RESULTS:
                    state = SourceState.NO_RESULTS
        india = [job for job in jobs if is_india(job.get("location"), job.get("country"))]
        # ATS readers already keep India roles; a career-page fallback can list the whole world, so drop a
        # clearly foreign posting there. A role with no stated location is kept (it is often "Remote, India").
        jobs = [job for job in jobs
                if job.get("discovered_via") != "company career page" or is_india(job.get("location"), None)
                or not job.get("location") or str(job.get("location")).casefold() == "remote"]
        # No role found is "no results" (reachable, but nothing to store), never an extraction success. A page that
        # answered is not a failure; a blocked/challenged page is. An empty public ATS board is a success too.
        final_state = state if jobs else (
            SourceState.NO_RESULTS if state in SourceState.SUCCESS or state == SourceState.NO_RESULTS else state)
        report.update(state=final_state, jobs=len(jobs), india_jobs=len(india), error=error,
                      ok=bool(jobs) or state in SourceState.SUCCESS
                      or (state == SourceState.NO_RESULTS and board is not None))
        progress(f"{row['name']}: {len(jobs)} India/open role(s)")
        return {**report, "listings": jobs}
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # one broken company must never stop the batch
        report.update(state=SourceState.SERVER_ERROR, error=f"{type(exc).__name__}: {exc}"[:300])
        return {**report, "listings": []}


async def scan_due(settings: Any, store: Any, preferences: dict[str, Any], *, limit: int = 6,
                   only: list[int] | None = None, progress: Callable[[str], None] | None = None,
                   cancel_event: Any | None = None, fetcher: Any | None = None) -> dict[str, Any]:
    """Scan one batch of due companies. The summary feeds the monitoring status and the coverage dashboard."""
    progress = progress or (lambda _message: None)
    started = time.perf_counter()
    if only:
        wanted = {int(item) for item in only}
        companies = [row for row in (store.company(item) for item in wanted) if row]
        companies.sort(key=lambda row: row["id"])
    else:
        companies = store.companies_due(limit=max(1, min(int(limit or 6), 40)))
    summary: dict[str, Any] = {"kind": "company_registry", "status": "complete", "companies": len(companies),
                               "scanned": [], "stored": 0, "india_jobs": 0, "failures": 0, "new_job_ids": [],
                               "seconds": 0.0}

    def cancel() -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise asyncio.CancelledError

    before = {row.get("canonical_url") for row in store.jobs(limit=5000)}
    semaphore = asyncio.Semaphore(COMPANY_CONCURRENCY)

    async def guarded(http: SafeFetcher, company: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            return await _scan_one(http, store, company, cancel=cancel, progress=progress)

    cache = settings.data_dir / "http-cache.sqlite3"
    if fetcher is not None:
        reports = await asyncio.gather(*(guarded(fetcher, company) for company in companies))
    else:
        async with SafeFetcher(cache_path=cache, cache_ttl=3 * 3600, timeout=20, max_bytes=2_500_000,
                               concurrency=COMPANY_CONCURRENCY, per_host_interval=1.0) as http:
            reports = await asyncio.gather(*(guarded(http, company) for company in companies))

    records: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    for report in reports:
        ok = bool(report.get("ok"))
        if report.get("listings"):
            records.extend(_record(item) for item in report["listings"])
        store.record_company_scan(report["id"], ok=ok, state=str(report.get("state")),
                                  jobs=int(report.get("jobs") or 0), india_jobs=int(report.get("india_jobs") or 0),
                                  error=report.get("error"), cadence_hours=CADENCE_HOURS, now=now)
        if not ok:
            summary["failures"] += 1
        summary["scanned"].append({key: report.get(key) for key in
                                   ("id", "company", "segment", "ats", "state", "jobs", "india_jobs", "pages", "error")})
        summary["india_jobs"] += int(report.get("india_jobs") or 0)
    if records:
        stored = store.upsert_jobs(records)
        summary["stored"] = len(stored)
        summary["new_job_ids"] = [row["id"] for row in stored
                                  if row.get("canonical_url") not in before][:200]
        store.link_jobs_to_employers()
        from app.services.broad_search import rescore_stored
        rescore_stored(store, preferences)
    summary["seconds"] = round(time.perf_counter() - started, 1)
    return summary
