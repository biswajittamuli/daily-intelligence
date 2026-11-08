"""Deterministic planning-note reader: plain text, Markdown and JSON.

Plain text and Markdown files are line-oriented: a line is a task when it is a
checkbox, a bullet, a numbered item, or (for .txt files) any non-empty line.
JSON files accept a list or an object with a ``tasks`` array.

Free-form lines are normalised into actionable tasks:
- intent prefixes are removed ("i want to walk my dog" -> "Walk my dog");
- natural dates/times are parsed ("tomorrow", "on friday", "next week", "by 15 nov",
  "at 6pm", "every morning");
- a keyword category is assigned (career, study, health, personal, errands, finance).
The original line is kept in ``original_text``.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

DATE = re.compile(r"(?:due|deadline|by|before|on)\s*[:@]?\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", re.I)
AT_DATE = re.compile(r"@\s*([0-9]{4}-[0-9]{2}-[0-9]{2})")
BARE_ISO = re.compile(r"\b([0-9]{4}-[0-9]{2}-[0-9]{2})\b")
CHECKBOX = re.compile(r"^\s*[-*+]\s+\[([ xX])\]\s+(.+)")
BULLET = re.compile(r"^\s*[-*+•]\s+(.+)")
NUMBERED = re.compile(r"^\s*\d+[.)]\s+(.+)")
DONE_PREFIX = re.compile(r"^\s*(?:done|completed|finished)\s*[:—-]\s*", re.I)

INTENT_PREFIX = re.compile(
    r"^\s*(?:(?:todo|to-do|task|reminder|note)\s*[:\-]\s*)?"
    r"(?:(?:i|we)\s+(?:really\s+)?(?:want|need|have|got|should|must|would\s+like|'d\s+like|plan|am\s+going|"
    r"will|gotta|wanna)\s*(?:to\s+)?|(?:i'm|im|i\s+am)\s+(?:going|planning)\s+to\s+|"
    r"(?:please\s+)?remind\s+me\s+to\s+|don'?t\s+forget\s+to\s+|remember\s+to\s+|"
    r"need\s+to\s+|have\s+to\s+|must\s+|should\s+|let'?s\s+|going\s+to\s+|gotta\s+)",
    re.I)

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
WEEKDAY_SHORT = {name[:3]: index for index, name in enumerate(WEEKDAYS)}
MONTHS = {name: index for index, name in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

RECURRENCE = re.compile(
    r"\b(?:every\s*day|daily|each\s+day|every\s+(morning|evening|night|afternoon)|"
    r"every\s+(week(?:day)?|weekend|monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
    r"weekly|monthly|every\s+month)\b", re.I)
TIME = re.compile(r"\b(?:at\s+|@\s*)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b|\bat\s+(\d{1,2}):(\d{2})\b", re.I)
PART_OF_DAY = {"morning": "08:00", "afternoon": "14:00", "evening": "18:00", "night": "21:00",
               "tonight": "20:00"}

CATEGORIES = [
    ("career", r"\b(apply|application|job|resume|cv|interview|recruit|linkedin|portfolio|offer|"
               r"hr|referral|cover letter|naukri|wellfound|internship)\b"),
    ("study", r"\b(study|revise|revision|learn|course|read|practice|leetcode|dsa|gate|exam|"
              r"lecture|notes|assignment|homework|syllabus|mock test|project)\b"),
    ("health", r"\b(walk|run|gym|workout|exercise|yoga|meditat\w*|sleep|doctor|medicine|"
               r"diet|swim|cycle|stretch)\b"),
    ("finance", r"\b(pay|bill|rent|bank|emi|tax|invoice|budget|salary|upi|recharge)\b"),
    ("errands", r"\b(buy|shop|grocer\w*|pick up|drop off|order|deliver\w*|clean|laundry|repair|"
                r"courier|post office)\b"),
    ("personal", r"\b(dog|cat|pet|family|mom|dad|friend|call|birthday|movie|cook|visit)\b"),
]

TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".text"}
SKIP_PREFIXES = ("#", "//", "<!--", "```", "---", "===")


def _next_weekday(today: date, weekday: int, *, force_next: bool = False) -> date:
    delta = (weekday - today.weekday()) % 7
    if delta == 0 and force_next:
        delta = 7
    return today + timedelta(days=delta)


def _parse_natural_date(text: str, today: date) -> tuple[str | None, str]:
    """Return (ISO date or None, text with the date phrase removed)."""
    patterns: list[tuple[re.Pattern[str], Any]] = [
        (re.compile(r"\b(?:by\s+|on\s+)?(today|tonight)\b", re.I), lambda m: today),
        (re.compile(r"\b(?:by\s+|on\s+)?(?:tomorrow|tmrw|tmr)\b", re.I), lambda m: today + timedelta(days=1)),
        (re.compile(r"\b(?:by\s+|on\s+)?day after tomorrow\b", re.I), lambda m: today + timedelta(days=2)),
        (re.compile(r"\b(?:by\s+)?(?:this\s+)?weekend\b", re.I), lambda m: _next_weekday(today, 5)),
        (re.compile(r"\bnext\s+week\b", re.I),
         lambda m: _next_weekday(today, 0, force_next=True)),
        (re.compile(r"\bnext\s+month\b", re.I),
         lambda m: (today.replace(day=1) + timedelta(days=32)).replace(day=1)),
        (re.compile(r"\bin\s+(\d{1,2})\s+days?\b", re.I), lambda m: today + timedelta(days=int(m.group(1)))),
        (re.compile(r"\bin\s+(\d{1,2})\s+weeks?\b", re.I), lambda m: today + timedelta(weeks=int(m.group(1)))),
        (re.compile(r"\b(?:by|on|before|this|next)?\s*(" + "|".join(WEEKDAYS) + r"|mon|tue|wed|thu|fri|sat|sun)\b",
                    re.I),
         lambda m: _next_weekday(today, WEEKDAY_SHORT[m.group(1).casefold()[:3]],
                                 force_next=m.group(0).casefold().lstrip().startswith("next"))),
        (re.compile(r"\b(?:by|on|before)?\s*(\d{1,2})(?:st|nd|rd|th)?\s+(" + "|".join(MONTHS) + r")[a-z]*\.?(?:\s+(\d{4}))?\b",
                    re.I),
         lambda m: _month_date(int(m.group(1)), m.group(2), m.group(3), today)),
        (re.compile(r"\b(?:by|on|before)?\s*(" + "|".join(MONTHS) + r")[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?\b",
                    re.I),
         lambda m: _month_date(int(m.group(2)), m.group(1), m.group(3), today)),
    ]
    for pattern, resolver in patterns:
        match = pattern.search(text)
        if not match:
            continue
        try:
            value = resolver(match)
        except (ValueError, KeyError):
            value = None
        if value:
            stripped = (text[:match.start()] + " " + text[match.end():])
            return value.isoformat(), stripped
    return None, text


def _month_date(day: int, month_name: str, year: str | None, today: date) -> date | None:
    month = MONTHS.get(month_name.casefold()[:3])
    if not month:
        return None
    value = date(int(year) if year else today.year, month, day)
    if not year and value < today - timedelta(days=30):
        value = value.replace(year=value.year + 1)
    return value


def _parse_time(text: str) -> tuple[str | None, str]:
    match = TIME.search(text)
    if match:
        if match.group(1):
            hour = int(match.group(1)) % 12
            if match.group(3).casefold() == "pm":
                hour += 12
            minute = int(match.group(2) or 0)
        else:
            hour, minute = int(match.group(4)), int(match.group(5))
        if 0 <= hour < 24 and 0 <= minute < 60:
            return f"{hour:02d}:{minute:02d}", text[:match.start()] + " " + text[match.end():]
    for word, clock in PART_OF_DAY.items():
        found = re.search(rf"\b(?:in the |this |every )?{word}\b", text, re.I)
        if found:
            # "every morning" stays in the text for recurrence detection.
            if found.group(0).casefold().startswith("every"):
                return clock, text
            return clock, text[:found.start()] + " " + text[found.end():]
    return None, text


def _recurrence(text: str) -> tuple[str | None, str]:
    match = RECURRENCE.search(text)
    if not match:
        return None, text
    phrase = match.group(0).casefold()
    if "week" in phrase and "weekday" not in phrase and "weekend" not in phrase:
        value = "weekly"
    elif "weekday" in phrase:
        value = "weekdays"
    elif "weekend" in phrase:
        value = "weekends"
    elif "month" in phrase:
        value = "monthly"
    elif any(day in phrase for day in WEEKDAYS):
        value = "weekly:" + next(day for day in WEEKDAYS if day in phrase)
    else:
        value = "daily"
    return value, text[:match.start()] + " " + text[match.end():]


def categorize(text: str) -> str:
    for name, pattern in CATEGORIES:
        if re.search(pattern, text, re.I):
            return name
    return "personal"


def normalize_task(raw: str, today: date | None = None) -> dict[str, Any]:
    """Turn a free-form note line into a task dict (text, due_date, due_time, recurrence, category)."""
    today = today or date.today()
    original = " ".join(raw.split())
    text = original
    due = None
    match = DATE.search(text) or AT_DATE.search(text) or BARE_ISO.search(text)
    if match:
        due = match.group(1)
        text = text[:match.start()] + " " + text[match.end():]
    due_time, text = _parse_time(text)
    recurrence, text = _recurrence(text)
    if not due:
        due, text = _parse_natural_date(text, today)
    if recurrence and not due:
        due = today.isoformat() if recurrence in {"daily", "weekdays"} or recurrence.endswith(
            WEEKDAYS[today.weekday()]) else None
    text = INTENT_PREFIX.sub("", text, count=1)
    text = re.sub(r"\b(?:by|on|before|due|at|this|in the)\s*$", "", text.strip(), flags=re.I)
    text = re.sub(r"\s+([,.;:!?])", r"\1", " ".join(text.split())).strip(" -–—,:;.")
    if text:
        text = text[0].upper() + text[1:]
    return {"text": text or original, "due_date": due, "due_time": due_time,
            "recurrence": recurrence, "category": categorize(original), "original_text": original}


def _clean_task(text: str) -> tuple[str, str | None]:
    """Backward-compatible helper: (text without the due clause, due date or None)."""
    task = normalize_task(text)
    return task["text"], task["due_date"]


def _parse_text_file(path: Path, raw: str, tasks: list[dict[str, Any]], today: date) -> None:
    plain = path.suffix.lower() not in {".md", ".markdown"}
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(SKIP_PREFIXES):
            continue
        completed = False
        match = CHECKBOX.match(line)
        if match:
            completed = match.group(1).lower() == "x"
            body = match.group(2)
        else:
            match = BULLET.match(line) or NUMBERED.match(line)
            if match:
                body = match.group(1)
            elif plain:
                body = stripped
            else:
                # Markdown prose is not a task; only explicit list items are.
                continue
        if DONE_PREFIX.match(body):
            completed = True
            body = DONE_PREFIX.sub("", body)
        if len(body) > 500:
            continue
        # A prose line with several sentences becomes several tasks.
        parts = [part for part in re.split(r"(?<=[.!?;])\s+(?=[A-Za-z])|\s+and\s+then\s+", body) if part.strip()] \
            if plain and not match else [body]
        for part in parts:
            task = normalize_task(part, today)
            if not task["text"]:
                continue
            task.update({"status": "completed" if completed else "pending", "source": str(path)})
            tasks.append(task)


def note_files(notes_dir: Path) -> list[Path]:
    if not notes_dir.exists():
        return []
    return sorted((p for p in notes_dir.iterdir()
                   if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES | {".json"}),
                  key=lambda p: p.stat().st_mtime, reverse=True)


def read_planning_notes(notes_dir: Path, today: date | None = None, *, max_files: int | None = None) -> dict[str, Any]:
    today = today or date.today()
    tasks: list[dict[str, Any]] = []
    errors: list[str] = []
    files: list[str] = []
    if not notes_dir.exists():
        return {"tasks": tasks, "missing": True, "errors": errors, "files": files, "sources": []}
    paths = note_files(notes_dir)
    if max_files is not None:
        paths = paths[:max_files]
    sources: list[str] = []
    for path in paths:
        files.append(path.name)
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")[:500_000]
            if path.suffix.lower() == ".json":
                data = json.loads(raw)
                items = data if isinstance(data, list) else data.get("tasks", []) if isinstance(data, dict) else []
                for item in items:
                    if isinstance(item, str):
                        item = {"text": item}
                    if not isinstance(item, dict) or not str(item.get("text", item.get("title", ""))).strip():
                        continue
                    status = str(item.get("status", "pending")).lower()
                    text = str(item.get("text", item.get("title"))).strip()[:500]
                    tasks.append({"text": text,
                                  "due_date": str(item.get("due_date", item.get("deadline", "")))[:10] or None,
                                  "due_time": item.get("due_time"), "recurrence": item.get("recurrence"),
                                  "category": item.get("category") or categorize(text),
                                  "original_text": text,
                                  "status": "completed" if status in {"done", "complete", "completed"} else "pending",
                                  "source": str(path)})
            else:
                _parse_text_file(path, raw, tasks, today)
            sources.append(str(path))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}: {exc}")
    for task in tasks:
        due = task["due_date"]
        task["overdue"] = bool(task["status"] == "pending" and due and due < today.isoformat())
        task["due_today"] = bool(task["status"] == "pending" and due == today.isoformat())
    return {"tasks": tasks, "missing": False, "errors": errors, "files": files, "sources": sources}


def safe_note_path(notes_dir: Path, name: str) -> Path:
    """Resolve a note file name strictly inside ``notes_dir`` (no traversal, text types only)."""
    clean = str(name or "").strip()
    if not clean or "/" in clean or "\\" in clean or clean.startswith(".") or "\x00" in clean:
        raise ValueError("Invalid note file name")
    path = (notes_dir / clean)
    if path.suffix.lower() not in {".txt", ".md", ".markdown"}:
        raise ValueError("Only .txt and .md notes can be edited in the app")
    resolved_dir = notes_dir.resolve()
    if path.resolve().parent != resolved_dir:
        raise ValueError("Note must be inside the notes directory")
    return path


def is_due_on(task: dict[str, Any], day: date) -> bool:
    """True when a pending task (including recurring ones) applies to ``day``."""
    if task.get("status") == "completed" and not task.get("recurrence"):
        return False
    recurrence = str(task.get("recurrence") or "")
    if recurrence == "daily":
        return True
    if recurrence == "weekdays":
        return day.weekday() < 5
    if recurrence == "weekends":
        return day.weekday() >= 5
    if recurrence.startswith("weekly:"):
        return WEEKDAYS[day.weekday()] == recurrence.split(":", 1)[1]
    if recurrence == "weekly" and task.get("due_date"):
        try:
            return datetime.fromisoformat(task["due_date"]).date().weekday() == day.weekday()
        except ValueError:
            return False
    if recurrence == "monthly" and task.get("due_date"):
        return str(task["due_date"])[8:10] == f"{day.day:02d}"
    return task.get("due_date") == day.isoformat()
