"""Background monitoring: followed companies, deadline reminders and local notifications.

- Followed companies: their public boards are re-read (bypassing the short cache) and reconciled, so new
  vacancies appear and removed ones close after two complete misses; verified career pages are re-read.
  New vacancies go through the same ranking as discovery and are stored only if relevant.
- Deadline reminders: saved/applied listings and notices with a deadline in the next 3 days become
  planning tasks (idempotent).
- Notifications: new strong or high-scoring eligible matches are recorded locally and, when enabled,
  shown with the desktop's ``notify-send``. Nothing leaves the machine.
"""
from __future__ import annotations

import shutil
import subprocess
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.config import Settings
from app.memory.store import Store

READABLE = {"greenhouse", "lever", "ashby", "workable", "smartrecruiters", "recruitee"}


async def check_followed(settings: Settings, store: Store, preferences: dict[str, Any], *,
                         progress=None, ats_fetcher=None, http=None) -> dict[str, Any]:
    from app.services import ats_sources
    from app.services.broad_search import BroadJobSearch
    from app.services.job_matching import relevance_gate, active_resume_match
    from app.services.requirements import extract_requirements
    from app.services.verification import reconcile_boards

    progress = progress or (lambda _m: None)
    followed = store.followed_employers()
    summary = {"kind": "followed_check", "employers": len(followed), "boards": 0, "openings": 0, "new": 0,
               "stored": 0, "closed": 0, "career_pages": 0, "new_job_ids": []}
    if not followed:
        return summary
    boards = [{"name": e["name"], "ats": e["ats_provider"], "slug": e["ats_slug"], "employer_id": e["id"]}
              for e in followed if e.get("ats_provider") in READABLE and e.get("ats_slug")]
    before = {job["canonical_url"] for job in store.jobs(limit=5000)}
    jobs: list[dict[str, Any]] = []
    if boards:
        progress(f"Checking {len(boards)} followed company board(s)")
        for board in boards:
            ats_sources._CACHE.pop((board["ats"], board["slug"]), None)  # a fresh read, not a cached copy
        fetcher = ats_fetcher or ats_sources.fetch_company_jobs
        found, coverage = await fetcher(boards)
        by_key = {f"{b['ats']}:{b['slug']}": b["employer_id"] for b in boards}
        for job in found:
            job["employer_id"] = by_key.get(str(job.get("source_platform") or ""))
        jobs.extend(found)
        summary["boards"] = sum(1 for c in coverage if str(c.get("status", "")).startswith("ok"))
        summary["closed"] = reconcile_boards(store, found, coverage)["closed"]
    pages = [e for e in followed if e.get("career_url") and not (e.get("ats_provider") in READABLE and e.get("ats_slug"))]
    harvested: list[dict[str, Any]] = []
    if pages:
        from app.services.job_sources.career_discovery import CareerDiscovery
        from app.services.job_sources.safe_http import SafeFetcher
        owns = http is None
        http = http or SafeFetcher(cache_path=settings.data_dir / "http-cache.sqlite3")
        if owns:
            await http.__aenter__()
        try:
            reader = CareerDiscovery(http)
            for employer in pages:
                progress(f"Reading {employer['name']} career page")
                outcome = await reader.read_career_page(employer["career_url"], employer["name"], lambda *a, **k: None,
                                                        allow_browser=False)
                summary["career_pages"] += 1
                for job in outcome["listings"]:
                    if not job.get("url_is_synthetic"):
                        harvested.append({**job, "employer": employer["name"], "employer_id": employer["id"],
                                          "_via": "Company career page"})
        finally:
            if owns:
                await http.__aexit__(None, None, None)
    summary["openings"] = len(jobs) + len(harvested)
    engine = BroadJobSearch(settings, store, preferences)
    candidates, _dups = engine._candidates([], harvested, jobs)
    resumes = store.resumes()
    active = next((r.get("profile") for r in resumes if r.get("is_default")), None)
    records = []
    from app.mcp.normalizer import canonicalize_url
    for item in candidates:
        if canonicalize_url(item["url"]) in before:
            continue
        summary["new"] += 1
        if relevance_gate(item, active, preferences)["excluded"]:
            continue
        item["_requirements"] = extract_requirements(str(item.get("raw_text") or ""), title=str(item.get("title") or ""))
        match = active_resume_match(item, preferences, resumes)
        if match["eligibility"]["tier"] == "excluded":
            continue
        item.update(match)
        records.append(engine._record(item))
    saved = store.upsert_jobs(records)
    summary["stored"] = len(saved)
    summary["new_job_ids"] = [job["id"] for job in saved]
    store.set_preference("last_followed_check", datetime.now(timezone.utc).isoformat())
    return summary


def deadline_reminders(store: Store, *, days: int = 3, today: date | None = None) -> int:
    """Saved/applied listings and notices with a deadline within ``days`` become tasks (once)."""
    from app.services.freshness import parse_date
    today = today or date.today()
    horizon = today + timedelta(days=days)
    existing = {task["text"] for task in store.tasks(include_archived=True)}
    states = store.item_states()
    created = 0
    tracked_jobs = {i for i, s in states.get("job", {}).items() if s in {"saved", "applied", "interview"}}
    for job in store.jobs(limit=5000):
        if job["id"] not in tracked_jobs or job.get("status") in {"closed", "expired"}:
            continue
        due = parse_date(job.get("deadline"))
        if due and today <= due <= horizon:
            text = f"Deadline: {job.get('title')}" + (f" at {job['employer']}" if job.get("employer") else "")
            if text[:300] not in existing:
                store.add_task(text[:300], due.isoformat(), source="reminder", category="career")
                created += 1
    for notice in store.notices(limit=500):
        if states.get("notice", {}).get(notice["id"]) not in {"saved", "applied"}:
            continue
        due = parse_date(notice.get("closing_date"))
        if due and today <= due <= horizon:
            text = f"Apply by {due.isoformat()}: {notice.get('post_name') or notice.get('organization')}"
            if text[:300] not in existing:
                store.add_task(text[:300], due.isoformat(), source="reminder", category="career")
                created += 1
    return created


def notable_jobs(store: Store, job_ids: list[int], preferences: dict[str, Any]) -> list[dict[str, Any]]:
    """New listings worth an alert: strong tier, or eligible/likely eligible above the score threshold."""
    threshold = int((preferences.get("automation") or {}).get("notify_min_score", 70) or 70)
    wanted = set(job_ids)
    output = []
    for job in store.jobs(limit=5000):
        if job["id"] not in wanted or job.get("status") in {"closed", "expired"}:
            continue
        e = job.get("eligibility") or {}
        level = e.get("level") or e.get("status")
        if e.get("tier") == "strong" or ((job.get("match_score") or 0) >= threshold and level in {"eligible", "likely_eligible"}):
            output.append(job)
    output.sort(key=lambda j: -((j.get("eligibility") or {}).get("composite") or j.get("match_score") or 0))
    return output


def notify(store: Store, preferences: dict[str, Any], jobs: list[dict[str, Any]], *, origin: str,
           sender=None) -> dict[str, Any]:
    """Record alerts locally and show one desktop notification summarising them (if enabled and available)."""
    if not jobs:
        return {"alerts": 0, "desktop": False}
    alerts = list(store.get_preference("alerts", []) or [])
    now = datetime.now(timezone.utc).isoformat()
    known = {a.get("job_id") for a in alerts}
    fresh = [j for j in jobs if j["id"] not in known]
    for job in fresh:
        alerts.append({"job_id": job["id"], "title": job.get("title"), "employer": job.get("employer"),
                       "score": job.get("match_score"), "url": job.get("original_url"), "at": now, "origin": origin,
                       "read": False})
    store.set_preference("alerts", alerts[-60:])
    shown = False
    if fresh and (preferences.get("automation") or {}).get("notify", True):
        top = fresh[0]
        title = f"{len(fresh)} new strong match{'es' if len(fresh) != 1 else ''}" if len(fresh) > 1 else "New strong match"
        body = f"{top.get('title')}" + (f" — {top['employer']}" if top.get("employer") else "")
        if sender is not None:
            shown = bool(sender(title, body))
        elif shutil.which("notify-send"):
            try:
                subprocess.run(["notify-send", "--app-name=Daily Intelligence", "--icon=dialog-information", title, body[:200]],
                               timeout=5, check=False, capture_output=True)
                shown = True
            except (OSError, subprocess.SubprocessError):
                shown = False
    return {"alerts": len(fresh), "desktop": shown}
