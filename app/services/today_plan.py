"""Deterministic daily plan: tasks + deadlines + suggested career actions.

Merges planning-note tasks (including recurring ones) with stored intelligence so the
Planning tab and the briefing share one source of truth. No model is involved.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.memory.planning import is_due_on
from app.services.freshness import parse_date


def _bucket(task: dict[str, Any], today: date) -> str:
    if task.get("recurrence") and is_due_on(task, today):
        return "today"
    due = parse_date(task.get("due_date"))
    if due is None:
        return "no_date"
    if due < today:
        return "overdue"
    if due == today:
        return "today"
    if due <= today + timedelta(days=7):
        return "this_week"
    return "later"


def build_today_plan(*, tasks: list[dict[str, Any]], jobs: list[dict[str, Any]],
                     exams: list[dict[str, Any]], notices: list[dict[str, Any]],
                     tracker: list[dict[str, Any]] | None = None,
                     skill_gap: list[dict[str, Any]] | None = None,
                     item_states: dict[str, dict[int, str]] | None = None,
                     today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    item_states = item_states or {}
    job_states = item_states.get("job", {})
    groups: dict[str, list[dict[str, Any]]] = {key: [] for key in
                                               ("overdue", "today", "this_week", "later", "no_date")}
    for task in tasks:
        if task.get("status") == "completed" and not task.get("recurrence"):
            continue
        groups[_bucket(task, today)].append(task)
    for key in groups:
        groups[key].sort(key=lambda item: (item.get("due_date") or "9999", item.get("due_time") or "99"))

    schedule: list[dict[str, Any]] = []
    for task in groups["overdue"] + groups["today"]:
        schedule.append({"time": task.get("due_time"), "kind": "task", "title": task["text"],
                         "category": task.get("category") or "personal", "task_id": task.get("id"),
                         "overdue": task in groups["overdue"], "recurrence": task.get("recurrence"),
                         "done": task.get("status") == "completed"})

    deadlines: list[dict[str, Any]] = []
    horizon = today + timedelta(days=14)
    for exam in exams:
        when = parse_date(exam.get("event_date"))
        if when and today <= when <= horizon:
            deadlines.append({"date": when.isoformat(), "kind": "exam",
                              "title": f"{exam.get('exam_name')}: {str(exam.get('event_type') or 'event').replace('_', ' ')}",
                              "url": exam.get("original_url")})
    for notice in notices:
        when = parse_date(notice.get("closing_date"))
        if when and today <= when <= horizon:
            deadlines.append({"date": when.isoformat(), "kind": "notice",
                              "title": f"Apply: {notice.get('post_name') or notice.get('organization')}",
                              "url": notice.get("original_url")})
    for job in jobs:
        when = parse_date(job.get("deadline"))
        if when and today <= when <= horizon:
            deadlines.append({"date": when.isoformat(), "kind": "job",
                              "title": f"Deadline: {job.get('title')}", "url": job.get("original_url")})
    deadlines.sort(key=lambda item: item["date"])
    for item in deadlines:
        if item["date"] == today.isoformat():
            schedule.append({"time": None, "kind": item["kind"], "title": item["title"],
                             "category": "career", "url": item.get("url")})

    suggestions: list[dict[str, Any]] = []
    candidates = [job for job in jobs
                  if job.get("status") not in {"expired", "closed"}
                  and job.get("match_score") is not None
                  # Never suggest applying where an explicit requirement fails (eligibility gate).
                  and (job.get("eligibility") or {}).get("tier", "possible") in {"strong", "possible"}
                  and (job.get("eligibility") or {}).get("status") != "not_eligible"
                  and job_states.get(int(job.get("id") or 0)) not in {"applied", "interview", "offer",
                                                                      "rejected", "dismissed"}
                  and (job.get("source_kind") or (job.get("raw") or {}).get("source_kind"))
                  not in {"index_page", "search_page"}]
    candidates.sort(key=lambda job: ((job.get("eligibility") or {}).get("composite") or job.get("match_score") or 0,
                                     job.get("posted_date") or ""), reverse=True)
    for job in candidates[:3]:
        resume = f" with your “{job['best_resume_label']}” resume" if job.get("best_resume_label") else ""
        suggestions.append({"kind": "apply", "title": f"Apply to {job.get('title')}"
                            f"{(' at ' + job['employer']) if job.get('employer') else ''}{resume}",
                            "detail": f"{job.get('match_score')}% match", "job_id": job.get("id"),
                            "url": job.get("original_url")})
    for entry in tracker or []:
        applied = parse_date(str(entry.get("applied_at") or "")[:10])
        status = entry.get("status") or entry.get("state")  # application records or legacy tracker rows
        if status == "applied" and applied and (today - applied).days >= 7 and not entry.get("follow_up_date"):
            label = entry.get("role") or entry.get("title")
            if entry.get("company"):
                label += f" at {entry['company']}"
            suggestions.append({"kind": "follow_up", "title": f"Follow up: {label}",
                                "detail": f"Applied {(today - applied).days} days ago",
                                "job_id": entry.get("job_id") or entry.get("id"),
                                "url": entry.get("job_url") or entry.get("original_url")})
    gaps = [item for item in skill_gap or [] if item.get("count", 0) >= 2]
    if gaps:
        top = gaps[0]
        suggestions.append({"kind": "learn", "title": f"Spend 45 minutes on {top['name']}",
                            "detail": f"Requested in {top['count']} stored listings and missing from your resumes"})

    schedule.sort(key=lambda item: (item.get("time") is None, item.get("time") or ""))
    counts = {key: len(value) for key, value in groups.items()}
    return {"date": today.isoformat(), "schedule": schedule, "groups": groups,
            "deadlines": deadlines, "suggestions": suggestions, "counts": counts}
