"""Local exports: iCalendar (.ics) for dated items and CSV for job listings."""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.services.freshness import parse_date


def _ics_escape(value: Any) -> str:
    text = " ".join(str(value or "").split())
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")[:300]


def _fold(line: str) -> str:
    """RFC 5545 line folding at 75 octets."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts, current = [], b""
    for char in line:
        encoded = char.encode("utf-8")
        if len(current) + len(encoded) > 74:
            parts.append(current.decode("utf-8"))
            current = b""
        current += encoded
    parts.append(current.decode("utf-8"))
    return "\r\n ".join(parts)


def _event(uid: str, day: date, summary: str, *, time: str | None = None,
           description: str = "", url: str | None = None, rrule: str | None = None) -> list[str]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VEVENT", f"UID:{uid}@daily-intelligence.local", f"DTSTAMP:{stamp}"]
    if time:
        hour, minute = time.split(":")
        start = f"{day.strftime('%Y%m%d')}T{int(hour):02d}{int(minute):02d}00"
        lines += [f"DTSTART:{start}", "DURATION:PT30M"]
    else:
        lines += [f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}",
                  f"DTEND;VALUE=DATE:{(day + timedelta(days=1)).strftime('%Y%m%d')}"]
    if rrule:
        lines.append(f"RRULE:{rrule}")
    lines.append(f"SUMMARY:{_ics_escape(summary)}")
    if description:
        lines.append(f"DESCRIPTION:{_ics_escape(description)}")
    if url and str(url).startswith(("http://", "https://")):
        lines.append(f"URL:{url}")
    lines.append("END:VEVENT")
    return lines


RRULES = {"daily": "FREQ=DAILY", "weekdays": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
          "weekends": "FREQ=WEEKLY;BYDAY=SA,SU", "weekly": "FREQ=WEEKLY", "monthly": "FREQ=MONTHLY"}
DAY_CODES = {"monday": "MO", "tuesday": "TU", "wednesday": "WE", "thursday": "TH",
             "friday": "FR", "saturday": "SA", "sunday": "SU"}


def calendar_ics(*, tasks: list[dict[str, Any]], jobs: list[dict[str, Any]],
                 exams: list[dict[str, Any]], notices: list[dict[str, Any]]) -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Daily Intelligence//Local//EN",
             "CALSCALE:GREGORIAN", "X-WR-CALNAME:Daily Intelligence"]
    for task in tasks:
        day = parse_date(task.get("due_date"))
        if not day or task.get("status") == "completed":
            continue
        recurrence = str(task.get("recurrence") or "")
        rrule = RRULES.get(recurrence)
        if recurrence.startswith("weekly:"):
            rrule = f"FREQ=WEEKLY;BYDAY={DAY_CODES.get(recurrence.split(':', 1)[1], 'MO')}"
        lines += _event(f"task-{task.get('id')}", day, task.get("text"), time=task.get("due_time"),
                        description=f"Planning task ({task.get('category') or 'personal'})", rrule=rrule)
    for exam in exams:
        day = parse_date(exam.get("event_date"))
        if day:
            lines += _event(f"exam-{exam.get('id')}", day,
                            f"{exam.get('exam_name')}: {str(exam.get('event_type') or 'event').replace('_', ' ')}",
                            description=f"Date status: {exam.get('date_status') or 'unverified'}",
                            url=exam.get("original_url"))
    for notice in notices:
        day = parse_date(notice.get("closing_date"))
        if day:
            lines += _event(f"notice-{notice.get('id')}", day,
                            f"Last date: {notice.get('post_name') or notice.get('organization')}",
                            url=notice.get("application_url") or notice.get("original_url"))
    for job in jobs:
        day = parse_date(job.get("deadline"))
        if day:
            lines += _event(f"job-{job.get('id')}", day,
                            f"Job deadline: {job.get('title')} {('at ' + job['employer']) if job.get('employer') else ''}",
                            url=job.get("original_url"))
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


JOB_COLUMNS = ["title", "employer", "location", "remote", "employment_type", "experience",
               "skills", "salary", "posted_date", "deadline", "status", "match_score",
               "best_resume_label", "source_platform", "original_url", "first_seen", "last_seen"]


def jobs_csv(jobs: list[dict[str, Any]], states: dict[int, str] | None = None) -> str:
    states = states or {}
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(JOB_COLUMNS + ["my_state"])
    for job in jobs:
        row = []
        for column in JOB_COLUMNS:
            value = job.get(column)
            if isinstance(value, list):
                value = "; ".join(map(str, value))
            text = "" if value is None else str(value)
            # Neutralise spreadsheet formula injection from scraped text.
            if text[:1] in {"=", "+", "-", "@"}:
                text = "'" + text
            row.append(text)
        row.append(states.get(int(job.get("id") or 0), ""))
        writer.writerow(row)
    return buffer.getvalue()
