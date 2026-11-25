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


# ------------------------------------------------------------------------- v5: notices, exams, digest
ALERTABLE = {"eligible", "likely_eligible"}


def notable_notices(store: Store, notice_ids: list[int]) -> list[dict[str, Any]]:
    """New notices worth an alert: the deterministic verdict is eligible or likely eligible and the window is not closed.

    ``uncertain`` never alerts here: it is listed in the daily digest together with the fact that is missing."""
    wanted = set(notice_ids)
    output = []
    for notice in store.notices(limit=500):
        if notice["id"] not in wanted or notice.get("status") in {"closed", "expired"}:
            continue
        if (notice.get("eligibility") or {}).get("status") in ALERTABLE:
            output.append(notice)
    return output


def _send(title: str, body: str, sender=None) -> bool:
    if sender is not None:
        return bool(sender(title, body))
    if not shutil.which("notify-send"):
        return False
    try:
        subprocess.run(["notify-send", "--app-name=Daily Intelligence", "--icon=dialog-information", title, body[:200]],
                       timeout=5, check=False, capture_output=True)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def notify_opportunities(store: Store, preferences: dict[str, Any], notices: list[dict[str, Any]], *, origin: str,
                         sender=None) -> dict[str, Any]:
    """Record alerts for notices the candidate is eligible for; one desktop notification summarises them."""
    if not notices:
        return {"alerts": 0, "desktop": False}
    alerts = list(store.get_preference("alerts", []) or [])
    known = {a.get("notice_id") for a in alerts if a.get("notice_id") is not None}
    now = datetime.now(timezone.utc).isoformat()
    fresh = [n for n in notices if n["id"] not in known]
    for notice in fresh:
        verdict = notice.get("eligibility") or {}
        alerts.append({"kind": "notice", "notice_id": notice["id"], "title": notice.get("post_name") or notice.get("organization"),
                       "employer": notice.get("organization"), "url": notice.get("document_url") or notice.get("original_url"),
                       "detail": verdict.get("status_label"), "deadline": notice.get("closing_date"), "at": now,
                       "origin": origin, "read": False})
    store.set_preference("alerts", alerts[-80:])
    shown = False
    if fresh and (preferences.get("automation") or {}).get("notify", True):
        top = fresh[0]
        title = "New notice you are eligible for" if len(fresh) == 1 else f"{len(fresh)} new notices you are eligible for"
        body = f"{top.get('post_name') or 'Recruitment notice'}" + (f" — {top['organization']}" if top.get("organization") else "")
        if top.get("closing_date"):
            body += f" (apply by {top['closing_date']})"
        shown = _send(title, body, sender)
    return {"alerts": len(fresh), "desktop": shown}


def exam_expectations(store: Store, *, today: date | None = None) -> list[dict[str, Any]]:
    """For every followed exam: when its notification is expected, and whether it has been seen.

    The expected date comes only from an official calendar event (type "notification") or from a month the user
    entered; nothing is inferred from general knowledge."""
    from app.services.freshness import parse_date
    today = today or date.today()
    manual = store.get_preference("exam_expectations", {}) or {}
    events = store.exams(limit=1000)
    notices = store.notices(limit=500)
    output = []
    for name in store.watchlist("exam"):
        needle = name.casefold()
        mine = [e for e in events if needle in str(e.get("exam_name") or "").casefold()]
        dated = sorted(d for d in (parse_date(e.get("event_date")) for e in mine if e.get("event_type") == "notification") if d)
        expected, source = None, None
        if dated:
            upcoming = [d for d in dated if d >= today]
            expected, source = (upcoming[0] if upcoming else dated[-1]), "official calendar"
        elif manual.get(name):
            expected, source = parse_date(str(manual[name]) + "-01"), "entered by you"
        if expected is None:
            output.append({"exam": name, "state": "no_calendar_date", "expected": None,
                           "detail": "No official calendar date is stored for this exam; add the expected month if you know it"})
            continue
        month = expected.strftime("%B %Y")
        if expected > today:
            output.append({"exam": name, "state": "expected", "expected": expected.isoformat(), "source": source,
                           "detail": f"Notification expected in {month} ({source})"})
            continue
        start = expected.replace(day=1)
        seen = any(e.get("event_type") in {"application_open", "application_close", "exam", "admit_card"}
                   and (parse_date(e.get("event_date")) or date.min) >= start for e in mine) or \
            any(needle in f"{n.get('post_name') or ''} {n.get('organization') or ''}".casefold()
                and str(n.get("first_seen") or "")[:10] >= start.isoformat() for n in notices)
        overdue = (today - expected).days > (31 if source == "entered by you" else 7)
        state = "seen" if seen else ("missing" if overdue else "expected")
        detail = (f"Notification for {month} was found" if seen else
                  f"Notification expected in {month} ({source}) has not been seen on the monitored official sources"
                  if overdue else f"Notification expected in {month} ({source})")
        output.append({"exam": name, "state": state, "expected": expected.isoformat(), "source": source, "detail": detail})
    return output


def daily_digest(store: Store, preferences: dict[str, Any], *, today: date | None = None, sender=None) -> dict[str, Any]:
    """One digest per day: deadlines, new eligible notices, notices blocked on one missing fact (which is stated),
    exam windows opening or closing, new company roles and expected notifications that did not appear."""
    from app.services.freshness import parse_date
    today = today or date.today()
    since = (today - timedelta(days=1)).isoformat()
    deadlines, new_eligible, needs_fact = [], [], []
    for notice in store.notices(limit=500):
        if notice.get("status") in {"closed", "expired"}:
            continue
        verdict = notice.get("eligibility") or {}
        status = verdict.get("status")
        entry = {"id": notice["id"], "title": notice.get("post_name") or notice.get("organization"),
                 "org": notice.get("organization"), "closing_date": notice.get("closing_date"),
                 "url": notice.get("document_url") or notice.get("original_url"), "eligibility": status,
                 "missing_facts": verdict.get("missing_facts") or []}
        closing = parse_date(notice.get("closing_date"))
        if closing and 0 <= (closing - today).days <= 7 and status != "not_eligible":
            # An uncertain notice is listed only with the fact that would settle it.
            if status in ALERTABLE or entry["missing_facts"]:
                deadlines.append({**entry, "days": (closing - today).days})
        if str(notice.get("first_seen") or "")[:10] >= since:
            if status in ALERTABLE:
                new_eligible.append(entry)
            elif status == "uncertain" and entry["missing_facts"]:
                needs_fact.append(entry)
    followed = [name.casefold() for name in store.watchlist("exam")]
    exams = []
    for event in store.exams(limit=1000):
        when = parse_date(event.get("event_date"))
        if not when or not 0 <= (when - today).days <= 7:
            continue
        if event.get("event_type") not in {"application_open", "application_close", "admit_card", "exam"}:
            continue
        status = (event.get("eligibility") or {}).get("status")
        is_followed = any(name in str(event.get("exam_name") or "").casefold() for name in followed)
        if status == "not_eligible" and not is_followed:
            continue
        exams.append({"id": event["id"], "title": event.get("exam_name"), "event": event.get("event_type"),
                      "date": event.get("event_date"), "days": (when - today).days, "followed": is_followed,
                      "url": event.get("document_url") or event.get("original_url")})
    roles = []
    for job in store.jobs(limit=3000):
        if str(job.get("first_seen") or "")[:10] < since or job.get("status") in {"closed", "expired"}:
            continue
        if job.get("discovered_via") not in {"company career board", "company career page"}:
            continue
        e = job.get("eligibility") or {}
        if e.get("tier") in {"strong", "possible"}:
            roles.append({"id": job["id"], "title": job.get("title"), "org": job.get("employer"), "score": job.get("match_score"),
                          "url": job.get("original_url")})
    roles.sort(key=lambda item: -(item["score"] or 0))
    missing = [item for item in exam_expectations(store, today=today) if item["state"] == "missing"]
    digest = {"date": today.isoformat(), "deadlines": sorted(deadlines, key=lambda d: d["days"])[:20],
              "new_eligible": new_eligible[:20], "needs_fact": needs_fact[:20], "exams": sorted(exams, key=lambda e: e["days"])[:20],
              "company_roles": roles[:10], "missing_notifications": missing,
              "created_at": datetime.now(timezone.utc).isoformat()}
    store.set_preference("daily_digest", digest)
    parts = []
    if digest["deadlines"]:
        parts.append(f"{len(digest['deadlines'])} deadline{'s' if len(digest['deadlines']) != 1 else ''} this week")
    if new_eligible:
        parts.append(f"{len(new_eligible)} new eligible notice{'s' if len(new_eligible) != 1 else ''}")
    if digest["exams"]:
        parts.append(f"{len(digest['exams'])} exam date{'s' if len(digest['exams']) != 1 else ''}")
    if roles:
        parts.append(f"{len(roles)} new company role{'s' if len(roles) != 1 else ''}")
    if missing:
        parts.append(f"{len(missing)} expected notification{'s' if len(missing) != 1 else ''} not seen")
    digest["desktop"] = bool(parts) and (preferences.get("automation") or {}).get("notify", True) and \
        _send("Daily Intelligence — today's digest", " · ".join(parts), sender)
    return digest
