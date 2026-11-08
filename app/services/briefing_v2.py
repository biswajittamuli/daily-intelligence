"""Actionable, evidence-backed daily briefing assembled from local data only.

Ten sections; each item keeps its source URL. "New" means first seen after the previous
briefing; older items that are still relevant are counted, not repeated. Closed or expired
listings are never recommended.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.services.freshness import parse_date
from app.services.verification import lifecycle

INACTIVE = {"closed", "expired"}


def _after(value: Any, since: str | None) -> bool:
    return bool(value) and (not since or str(value) > since)


def build_briefing(*, jobs: list[dict[str, Any]], notices: list[dict[str, Any]], exams: list[dict[str, Any]],
                   news: list[dict[str, Any]], papers: list[dict[str, Any]], employers: list[dict[str, Any]],
                   signals: list[dict[str, Any]], applications: list[dict[str, Any]], today_plan: dict[str, Any],
                   previous_at: str | None, previous_urls: set[str] | None = None,
                   active_resume: str | None = None, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    previous_urls = previous_urls or set()
    since = previous_at or (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    sections: list[dict[str, Any]] = []

    def section(key, title, items, *, note="", still=0):
        sections.append({"key": key, "title": title, "items": items, "note": note, "still_relevant": still,
                         "new_count": sum(1 for item in items if item.get("new"))})

    # 1. Critical deadlines (next 7 days)
    horizon = today + timedelta(days=7)
    deadlines = []
    for job in jobs:
        due = parse_date(job.get("deadline"))
        if due and today <= due <= horizon and job.get("status") not in INACTIVE:
            deadlines.append({"date": due.isoformat(), "title": f"Apply: {job.get('title')}"
                              + (f" at {job['employer']}" if job.get("employer") else ""), "url": job.get("original_url"),
                              "kind": "job deadline"})
    for notice in notices:
        due = parse_date(notice.get("closing_date"))
        if due and today <= due <= horizon:
            deadlines.append({"date": due.isoformat(), "title": f"Last date: {notice.get('post_name') or notice.get('organization')}",
                              "url": notice.get("application_url") or notice.get("original_url"), "kind": "recruitment"})
    for exam in exams:
        due = parse_date(exam.get("event_date"))
        if due and today <= due <= horizon and exam.get("event_type") in {"application_close", "exam", "admit_card",
                                                                          "correction"}:
            deadlines.append({"date": due.isoformat(), "title": f"{exam.get('exam_name')}: "
                              f"{str(exam.get('event_type')).replace('_', ' ')}", "url": exam.get("original_url"),
                              "kind": "exam"})
    for item in applications:
        for interview in item.get("interview_dates") or []:
            due = parse_date(str(interview.get("at") or "")[:10])
            if due and today <= due <= horizon:
                deadlines.append({"date": str(interview.get("at")), "title": f"Interview: {item.get('role')} at {item.get('company')}",
                                  "url": item.get("job_url"), "kind": "interview"})
    deadlines.sort(key=lambda item: item["date"])
    section("deadlines", "Critical deadlines (7 days)", deadlines)

    # 2. New jobs matching the active resume
    usable = [job for job in jobs if (job.get("eligibility") or {}).get("tier") in {"strong", "possible"}
              and lifecycle(job, today)["state"] not in {"closed", "expired"}]
    usable.sort(key=lambda job: (job.get("eligibility") or {}).get("composite") or 0, reverse=True)
    new_jobs = [job for job in usable if _after(job.get("first_seen"), since)]
    section("jobs", f"New jobs matching your active resume{f' ({active_resume})' if active_resume else ''}", [
        {"title": job.get("title"), "detail": f"{job.get('employer') or 'Employer not stated'} · {job.get('location') or '—'}"
                                              f" · match {job.get('match_score')}"
                                              f" · {(job.get('eligibility') or {}).get('status', 'unknown').replace('_', ' ')}",
         "url": job.get("original_url"), "new": True, "tier": (job.get("eligibility") or {}).get("tier")}
        for job in new_jobs[:8]], still=len(usable) - len(new_jobs),
        note="Strong and possible matches first seen since the previous briefing.")

    # 3. Newly discovered Indian startups and employers
    new_employers = [e for e in employers if _after(e.get("first_discovered"), since)
                     and "built-in verified board list" not in (e.get("discovery_sources") or [])]
    new_signals = [s for s in signals if _after(s.get("first_seen"), since)]
    section("employers", "Newly discovered startups and employers", [
        {"title": e["name"], "detail": " · ".join(part for part in (e.get("country"), e.get("classification"),
                                                                     e.get("career_status")) if part),
         "url": e.get("career_url") or e.get("website"), "new": True} for e in new_employers[:8]] + [
        {"title": s.get("title") or s["company_name"], "detail": f"{s['signal_type'].replace('_', ' ')} signal — not a vacancy",
         "url": s.get("source_url"), "new": True} for s in new_signals[:6]])

    # 4. Government and PSU
    new_notices = [n for n in notices if _after(n.get("first_seen"), since) and n.get("status") != "closed"]
    section("government", "New government and PSU opportunities", [
        {"title": n.get("post_name") or n.get("organization"), "detail": f"{n.get('organization') or ''} · CSE: "
                                                                        f"{str(n.get('cse_eligibility') or 'not verified').replace('_', ' ')}",
         "url": n.get("notification_url") or n.get("original_url"), "new": True} for n in new_notices[:6]])

    # 5. Upcoming exam events (30 days)
    upcoming = sorted((e for e in exams if (parse_date(e.get("event_date")) or date.min) >= today
                       and parse_date(e.get("event_date")) <= today + timedelta(days=30)),
                      key=lambda e: str(e.get("event_date")))
    section("exams", "Upcoming examination events (30 days)", [
        {"title": f"{e.get('exam_name')}: {str(e.get('event_type') or '').replace('_', ' ')}",
         "detail": f"{e.get('event_date')} · {e.get('date_status') or 'unverified'}", "url": e.get("notification_url")
         or e.get("original_url"), "new": _after(e.get("first_seen"), since)} for e in upcoming[:8]])

    # 6. AI developments / 7. research — only new, not repeated from the previous briefing
    def fresh(items):
        return [i for i in items if _after(i.get("first_seen"), since) and i.get("original_url") not in previous_urls]
    section("news", "Important AI developments", [
        {"title": n.get("title"), "detail": " · ".join(part for part in (n.get("publisher"), n.get("topic"), n.get("region"))
                                                       if part), "url": n.get("original_url"), "new": True}
        for n in fresh(news)[:6]], still=0)
    section("research", "Research discoveries", [
        {"title": p.get("title"), "detail": p.get("publisher") or "", "url": p.get("original_url"), "new": True}
        for p in fresh(papers)[:5]])

    # 8. Application follow-ups
    follow = []
    for item in applications:
        due = parse_date(item.get("follow_up_date"))
        if due and due <= today + timedelta(days=2) and item.get("status") not in {"rejected", "withdrawn", "closed", "offer"}:
            follow.append({"title": f"Follow up: {item.get('role')} at {item.get('company') or '—'}",
                           "detail": f"due {due.isoformat()} · status {item.get('status')}", "url": item.get("job_url")})
        elif item.get("status") == "applied" and not item.get("follow_up_date"):
            applied = parse_date(item.get("applied_at"))
            if applied and (today - applied).days >= 7:
                follow.append({"title": f"No reply yet: {item.get('role')} at {item.get('company') or '—'}",
                               "detail": f"applied {applied.isoformat()} ({(today - applied).days} days ago)",
                               "url": item.get("job_url")})
    section("applications", "Application follow-ups", follow)

    # 9. Planning tasks / 10. next actions
    section("planning", "Today's planning tasks", [
        {"title": s["title"], "detail": (s.get("time") or "any time") + (" · overdue" if s.get("overdue") else ""),
         "url": s.get("url")} for s in (today_plan or {}).get("schedule", [])])
    section("actions", "Suggested next actions", [
        {"title": s["title"], "detail": s.get("detail") or "", "url": s.get("url")}
        for s in (today_plan or {}).get("suggestions", [])])

    changes = {s["key"]: s["new_count"] for s in sections}
    return {"date": today.isoformat(), "since": since, "sections": sections, "changes": changes,
            "total_new": sum(changes.values())}
