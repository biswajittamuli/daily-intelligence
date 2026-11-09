"""Listing re-verification and lifecycle status.

Statuses shown to the user (``lifecycle()``):
  open_verified       open, listed on the employer's own job board within VERIFIED_DAYS
  open_page_checked   open, the listing page itself showed an apply option within VERIFIED_DAYS
                      (a third-party page, so weaker evidence than the employer's board)
  open_not_recent     was verified open, but not recently
  closed / expired / reposted / unverified / unknown

Evidence rules:
- Company ATS boards (Greenhouse/Lever/Ashby/Workable/SmartRecruiters): the listing being on
  the employer's own board is evidence it is open. Missing on two consecutive successful
  board reads -> closed ("not on the employer's board on <dates>"). One miss is only recorded.
- Other pages: re-fetched through Parallel MCP. Explicit wording ("no longer accepting",
  "position has been filled", "this job has expired") -> closed; a passed deadline -> expired;
  apply wording with no closure wording -> verified open. Unreachable pages change nothing.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import replace
from datetime import date, datetime, timezone
from typing import Any, Callable

from app.config import Settings
from app.mcp.normalizer import canonicalize_url
from app.memory.store import Store
from app.services.freshness import parse_date
from app.services.requirements import extract_requirements

VERIFIED_DAYS = 7
CLOSED_WORDS = re.compile(
    r"\b(no longer accepting applications|no longer (?:available|open|active)|position has been filled|"
    r"this (?:job|position|posting|role|vacancy) (?:has|is) (?:expired|closed|been filled|no longer)|"
    r"applications? (?:are |is )?(?:now )?closed|job (?:is )?closed|hiring (?:is )?closed|"
    r"the job you are looking for (?:is|was) (?:not found|no longer)|this job is no longer|"
    r"position (?:is )?no longer available|expired job)\b", re.I)
NOT_FOUND = re.compile(r"\b(page not found|404 not found|error 404|job not found|couldn'?t find (?:the|this) job)\b", re.I)
OPEN_WORDS = re.compile(r"\b(apply now|apply for this job|submit (?:your )?application|easy apply|apply here|"
                        r"apply on company site|i'?m interested|apply)\b", re.I)


def lifecycle(job: dict[str, Any], today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    status = str(job.get("status") or "unverified")
    deadline = parse_date(job.get("deadline"))
    if deadline and deadline < today and status not in {"closed"}:
        return {"state": "expired", "label": "Expired", "detail": f"Deadline {deadline.isoformat()} has passed"}
    if status in {"closed", "expired"}:
        return {"state": status, "label": status.capitalize(), "detail": job.get("status_evidence") or ""}
    if job.get("repost_of") and status in {"open", "unverified"}:
        return {"state": "reposted", "label": "Reposted", "detail": f"Re-listed; earlier listing #{job['repost_of']}"}
    history = job.get("verify_history") or []
    recent = [h.get("outcome") for h in history[-2:]]
    if len(recent) == 2 and all(outcome == "unreachable" for outcome in recent):
        return {"state": "inaccessible", "label": "Inaccessible",
                "detail": f"Could not be retrieved in the last two checks ({history[-1].get('evidence') or ''})".strip()}
    verified = parse_date(str(job.get("last_verified") or "")[:10])
    if status == "open":
        if verified and (today - verified).days <= VERIFIED_DAYS:
            on_board = str(job.get("status_evidence") or "").startswith("Listed on") or \
                job.get("discovered_via") == "company career board"
            suffix = " (reposted)" if job.get("repost_of") else ""
            if on_board:
                return {"state": "open_verified", "label": "Open · verified on employer board",
                        "detail": f"Listed on the employer's job board on {verified.isoformat()}{suffix}"}
            if str(job.get("verification_source") or "").startswith("employer"):
                return {"state": "open_verified", "label": "Open · verified on employer page",
                        "detail": f"The employer's own page showed an apply option on {verified.isoformat()}{suffix}"}
            return {"state": "open_page_checked", "label": "Open · third-party source only",
                    "detail": f"Listing page showed an apply option on {verified.isoformat()}; "
                              f"not confirmed on the employer's own system{suffix}"}
        return {"state": "open_not_recent", "label": "Open · not recently verified",
                "detail": f"Last verified {verified.isoformat()}" if verified else "Never re-verified"}
    if status == "unknown":
        return {"state": "unknown", "label": "Unknown", "detail": job.get("status_evidence") or ""}
    if job.get("conflicts"):
        fields = sorted({c.get("field") for c in job["conflicts"] if isinstance(c, dict)})
        return {"state": "unverified", "label": "Unverified · conflicting sources",
                "detail": "Sources disagree on " + ", ".join(fields)}
    if not job.get("last_verified") and not history:
        return {"state": "pending_verification", "label": "Pending verification",
                "detail": "Discovered; not yet checked against the original page"}
    return {"state": "unverified", "label": "Unverified", "detail": "Open status not confirmed from the source"}


def select_for_verification(store: Store, *, limit: int = 40, job_ids: list[int] | None = None) -> list[dict[str, Any]]:
    jobs = store.jobs(limit=5000)
    if job_ids:
        wanted = set(job_ids)
        return [job for job in jobs if job["id"] in wanted]
    tracked = {app["job_id"] for app in store.applications() if app.get("job_id")}
    states = store.item_states().get("job", {})
    chosen, rest = [], []
    for job in jobs:
        if job.get("status") in {"closed", "expired"}:
            continue
        tier = (job.get("eligibility") or {}).get("tier")
        if job["id"] in tracked or states.get(job["id"]) in {"saved", "applied", "interview"}:
            chosen.append(job)
        elif tier in {"strong", "possible"}:
            rest.append(job)
    rest.sort(key=lambda job: str(job.get("last_verified") or ""))  # least recently verified first
    return (chosen + rest)[:limit]


def _ats_key(job: dict[str, Any]) -> tuple[str, str] | None:
    platform = str(job.get("source_platform") or "")
    if ":" not in platform and job.get("ats_ref"):
        platform = str(job["ats_ref"])
    if ":" in platform and platform.split(":", 1)[0] in {"greenhouse", "lever", "ashby", "workable", "smartrecruiters",
                                                          "recruitee"}:
        ats, slug = platform.split(":", 1)
        return ats, slug
    return None


async def verify_jobs(store: Store, settings: Settings, jobs: list[dict[str, Any]], *,
                      progress: Callable[[str], None] | None = None, cancel: Callable[[], None] | None = None,
                      retriever: Any | None = None, ats_fetcher: Callable[..., Any] | None = None,
                      today: date | None = None, http: Any | None = None) -> dict[str, Any]:
    from app.services.ats_sources import fetch_company_jobs, _CACHE

    progress = progress or (lambda _: None)
    today = today or date.today()
    counts = {"checked": 0, "verified_open": 0, "closed": 0, "expired": 0, "missing_once": 0,
              "unreachable": 0, "unchanged": 0, "not_checked": 0}
    details: list[dict[str, Any]] = []

    per_source: dict[str, list[int]] = {}

    def source_of(job) -> str:
        key = _ats_key(job)
        if key:
            return f"ats:{key[0]}"
        if _employer_page(job):
            return "career:read"
        from app.services.job_sources import portals as portal_policy
        portal = portal_policy.portal_for(str(job.get("original_url") or ""))
        return ("portal:" + re.sub(r"[^a-z0-9]+", "-", portal.name.casefold()).strip("-")) if portal else "search:web"

    def record(job, outcome, *, status=None, evidence="", missing=False, raw_text=None, posted=None):
        counts[outcome] = counts.get(outcome, 0) + 1
        if outcome != "not_checked":
            entry = per_source.setdefault(source_of(job), [0, 0])
            entry[0] += int(outcome in {"verified_open", "closed", "expired"})
            entry[1] += 1
        store.record_verification(job["id"], status=status, evidence=evidence, outcome=outcome, missing=missing,
                                  raw_text=raw_text, posted_date=posted)
        details.append({"id": job["id"], "title": job.get("title"), "outcome": outcome, "evidence": evidence[:160]})

    # Deadline check first (no network needed).
    remaining = []
    for job in jobs:
        deadline = parse_date(job.get("deadline"))
        if deadline and deadline < today:
            counts["checked"] += 1
            record(job, "expired", status="expired", evidence=f"Application deadline {deadline.isoformat()} has passed")
        else:
            remaining.append(job)

    # 1) ATS-backed listings: re-read each employer board once (fresh, not cached).
    ats_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    web_jobs = []
    for job in remaining:
        key = _ats_key(job)
        (ats_groups.setdefault(key, []) if key else web_jobs).append(job)
    if ats_groups:
        progress(f"Re-reading {len(ats_groups)} employer job boards")
        for key in ats_groups:
            _CACHE.pop(key, None)
        fetcher = ats_fetcher or fetch_company_jobs
        companies = [{"ats": ats, "slug": slug, "name": slug} for ats, slug in ats_groups]
        board_jobs, coverage = await fetcher(companies, cancel=cancel)
        ok_boards = {(entry.get("ats") or "", entry.get("slug") or "") for entry in coverage
                     if str(entry.get("status", "")).startswith("ok")}
        ok_names = {entry["platform"] for entry in coverage if str(entry.get("status", "")).startswith("ok")}
        present = {canonicalize_url(str(item.get("url") or "")): item for item in board_jobs}
        for (ats, slug), group in ats_groups.items():
            board_ok = (ats, slug) in ok_boards or slug in ok_names
            for job in group:
                counts["checked"] += 1
                item = present.get(canonicalize_url(str(job.get("original_url") or "")))
                if item:
                    record(job, "verified_open", status="open",
                           evidence=f"Listed on {ats.capitalize()} board '{slug}' on {today.isoformat()}",
                           raw_text=item.get("description"), posted=item.get("posted_date"))
                elif not board_ok:
                    record(job, "unreachable", evidence=f"{ats.capitalize()} board '{slug}' could not be read")
                elif int(job.get("missing_count") or 0) >= 1:
                    record(job, "closed", status="closed", missing=True,
                           evidence=f"Not on {ats.capitalize()} board '{slug}' in two consecutive checks "
                                    f"(last {today.isoformat()})")
                else:
                    record(job, "missing_once", missing=True,
                           evidence=f"Not on {ats.capitalize()} board '{slug}' on {today.isoformat()}; "
                                    "will be marked closed if still missing next check")

    # 2) Other listings. Employer pages are checked first and directly (robots-respecting fetcher);
    #    portals with a search-results-only policy are never fetched; the rest go through Parallel MCP.
    from app.services.job_sources import portals as portal_policy
    direct_jobs, provider_jobs = [], []
    for job in web_jobs:
        target = _employer_page(job)
        if target:
            direct_jobs.append((job, target))
            continue
        allowed, reason = portal_policy.may_fetch(str(job.get("original_url") or ""), via="provider")
        if not allowed:
            counts["checked"] += 1
            record(job, "not_checked", evidence=f"{reason}. Open the original listing to check it.")
            continue
        provider_jobs.append(job)
    if direct_jobs:
        progress(f"Checking {len(direct_jobs)} listings on employer pages")
        await _verify_direct(direct_jobs, record, counts, today, http=http)
    web_jobs = provider_jobs
    if web_jobs:
        from app.mcp.retrieval import ParallelWebRetriever, RetrievalError
        owns = retriever is None
        try:
            if owns:
                retriever = ParallelWebRetriever(settings=replace(
                    settings, max_tool_calls=len(web_jobs) // 5 + 3, max_fetch_urls=20,
                    mcp_timeout=max(settings.mcp_timeout, 45.0)))
                await retriever.__aenter__()
            for start in range(0, len(web_jobs), 5):
                if cancel:
                    cancel()
                chunk = web_jobs[start:start + 5]
                progress(f"Re-fetching listing pages {start + 1}-{start + len(chunk)} of {len(web_jobs)}")
                try:
                    pages = await retriever.fetch([job["original_url"] for job in chunk],
                                                  "Is this job listing still open? Find apply buttons, closure notices and dates.",
                                                  full_content=True)
                except RetrievalError as exc:
                    pages = []
                    for job in chunk:
                        counts["checked"] += 1
                        record(job, "unreachable", evidence=f"Fetch failed: {str(exc)[:120]}")
                    continue
                by_url = {canonicalize_url(str(page.get("url") or "")): page for page in pages}
                for job in chunk:
                    counts["checked"] += 1
                    page = by_url.get(canonicalize_url(job["original_url"]))
                    text = str((page or {}).get("full_content") or (page or {}).get("content") or "")
                    if not text.strip():
                        record(job, "unreachable", evidence="Page could not be retrieved (blocked, login wall or empty)")
                        continue
                    closed = CLOSED_WORDS.search(text)
                    if closed:
                        record(job, "closed", status="closed", evidence=f"Page says: “{closed.group(0)}”")
                        continue
                    if NOT_FOUND.search(text[:2000]):
                        if int(job.get("missing_count") or 0) >= 1:
                            record(job, "closed", status="closed", missing=True,
                                   evidence="Listing page not found in two consecutive checks")
                        else:
                            record(job, "missing_once", missing=True, evidence="Listing page reported not found once")
                        continue
                    reqs = extract_requirements(text[:12000], title=str(job.get("title") or ""))
                    deadline = parse_date(reqs.get("deadline"))
                    if deadline and deadline < today:
                        record(job, "expired", status="expired", evidence=f"Page states deadline {deadline.isoformat()}")
                    elif OPEN_WORDS.search(text):
                        record(job, "verified_open", status="open", evidence="Listing page reachable with apply option",
                               raw_text=text[:8000])
                    else:
                        record(job, "unchanged", evidence="Page reachable; no apply or closure wording found",
                               raw_text=text[:8000])
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # report, never crash the whole verification run
            for job in web_jobs[counts["checked"]:]:
                details.append({"id": job["id"], "title": job.get("title"), "outcome": "unreachable",
                                "evidence": f"{type(exc).__name__}"})
        finally:
            if owns and retriever is not None:
                try:
                    await retriever.__aexit__(None, None, None)
                except Exception:
                    pass
    for source_id, (ok, total) in per_source.items():
        store.record_source_verification(source_id, ok, total)
    return {"kind": "reverify", "status": "complete", **counts, "details": details[:200],
            "at": datetime.now(timezone.utc).isoformat()}


def _employer_page(job: dict[str, Any]) -> str | None:
    """The employer's own page for a listing (official application page, career page or employer URL), if known."""
    from app.services.job_sources import portals as portal_policy
    for candidate in (job.get("application_url"), job.get("employer_url"),
                      job.get("original_url") if job.get("discovered_via") == "company career page" else None):
        if candidate and portal_policy.portal_for(str(candidate)) is None:
            return str(candidate)
    for source in job.get("sources") or []:
        if source.get("via") in {"Company career page", "company career page"} and source.get("url"):
            return str(source["url"])
    return None


async def _verify_direct(pairs, record, counts, today: date, *, http: Any | None = None) -> None:
    from app.services.job_sources import structured
    from app.services.job_sources.models import SourceState
    from app.services.job_sources.safe_http import SafeFetcher

    owns = http is None
    if owns:
        http = SafeFetcher(concurrency=4, per_host_interval=1.0)
        await http.__aenter__()
    try:
        results = await http.get_many([target for _, target in pairs], use_cache=False)
        for (job, target), page in zip(pairs, results):
            counts["checked"] += 1
            if page.state in {SourceState.NOT_FOUND}:
                if int(job.get("missing_count") or 0) >= 1:
                    record(job, "closed", status="closed", missing=True,
                           evidence=f"Employer page returned HTTP {page.status} in two consecutive checks")
                else:
                    record(job, "missing_once", missing=True, evidence=f"Employer page returned HTTP {page.status} once")
                continue
            if not page.ok:
                record(job, "unreachable", evidence=f"Employer page: {SourceState.LABELS.get(page.state, page.state)}"
                                                     f"{' — ' + page.error if page.error else ''}")
                continue
            text = structured.visible_text(page.text, 30000)
            postings = structured.job_postings(page.text, page.final_url or target)
            valid = next((parse_date(p.get("deadline")) for p in postings if p.get("deadline")), None)
            closed = CLOSED_WORDS.search(text)
            if closed:
                record(job, "closed", status="closed", evidence=f"Employer page says: “{closed.group(0)}”")
            elif valid and valid < today:
                record(job, "expired", status="expired", evidence=f"JobPosting validThrough {valid.isoformat()} has passed")
            elif postings or OPEN_WORDS.search(text):
                record(job, "verified_open", status="open",
                       evidence=("Employer page has JobPosting data" if postings else "Employer page shows an apply option")
                                + f" ({today.isoformat()})", raw_text=text[:8000],
                       posted=next((p.get("posted_date") for p in postings if p.get("posted_date")), None))
            else:
                record(job, "unchanged", evidence="Employer page reachable; no apply or closure wording found")
    finally:
        if owns:
            await http.__aexit__(None, None, None)


REVERIFY_AFTER_DAYS = 3


def select_due_for_verification(store: Store, *, limit: int = 30, today: date | None = None) -> list[dict[str, Any]]:
    """Active listings whose last check is older than REVERIFY_AFTER_DAYS (tracked and well-matched first).

    Listings read from a complete employer-board scan are re-checked by board reconciliation during
    discovery, so they are not selected here unless tracked.
    """
    today = today or date.today()
    tracked = {app["job_id"] for app in store.applications() if app.get("job_id")}
    states = store.item_states().get("job", {})
    candidates = []
    for job in store.jobs(limit=5000):
        if job.get("status") in {"closed", "expired"} or states.get(job["id"]) == "dismissed":
            continue
        is_tracked = job["id"] in tracked or states.get(job["id"]) in {"saved", "applied", "interview"}
        if _ats_key(job) and not is_tracked:
            continue
        checked = parse_date(str(job.get("last_verified") or "")[:10])
        history = job.get("verify_history") or []
        last_try = parse_date(str((history[-1] or {}).get("at") or "")[:10]) if history else None
        last = max(filter(None, [checked, last_try]), default=None)
        if last and (today - last).days < REVERIFY_AFTER_DAYS:
            continue
        candidates.append((not is_tracked, -(job.get("match_score") or 0), job["id"], job))
    candidates.sort(key=lambda item: item[:3])
    return [item[3] for item in candidates[:limit]]


def reconcile_boards(store: Store, board_jobs: list[dict[str, Any]], coverage: list[dict[str, Any]], *,
                     today: date | None = None) -> dict[str, int]:
    """Compare stored listings with boards that were read completely in this run.

    Present on the board → verified open. Missing once → recorded; missing on two consecutive complete
    reads → closed. Boards read partially, served from the short-lived cache, or not read at all change nothing
    (a failed request is not a closure, and a cached copy is not a second observation).
    """
    today = today or date.today()
    complete = {f"{entry.get('ats')}:{entry.get('slug')}" for entry in coverage
                if entry.get("complete") and entry.get("status") == "ok" and entry.get("ats") and entry.get("slug")}
    counts = {"checked": 0, "still_listed": 0, "missing_once": 0, "closed": 0, "boards": len(complete)}
    if not complete:
        return counts
    present = {canonicalize_url(str(job.get("url") or "")) for job in board_jobs}
    for job in store.jobs(limit=5000):
        key = _ats_key(job)
        if not key or f"{key[0]}:{key[1]}" not in complete or job.get("status") in {"closed", "expired"}:
            continue
        counts["checked"] += 1
        ats, slug = key
        if canonicalize_url(str(job.get("original_url") or "")) in present:
            counts["still_listed"] += 1
            if str(job.get("last_verified") or "")[:10] != today.isoformat():
                store.record_verification(job["id"], status="open", outcome="verified_open",
                                          evidence=f"Listed on {ats.capitalize()} board '{slug}' on {today.isoformat()}")
        elif int(job.get("missing_count") or 0) >= 1:
            counts["closed"] += 1
            store.record_verification(job["id"], status="closed", outcome="closed", missing=True,
                                      evidence=f"Not on {ats.capitalize()} board '{slug}' in two consecutive complete reads "
                                               f"(last {today.isoformat()})")
        else:
            counts["missing_once"] += 1
            store.record_verification(job["id"], status=None, outcome="missing_once", missing=True,
                                      evidence=f"Not on {ats.capitalize()} board '{slug}' on {today.isoformat()}; "
                                               "closed if still missing next time")
    return counts
