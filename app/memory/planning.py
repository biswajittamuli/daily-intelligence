"""Deterministic Markdown, plain-text and JSON planning note reader.

Plain text and Markdown files are line-oriented: a line is a task when it is a
checkbox, a bullet, a numbered item, or (for .txt files) any non-empty line.
JSON files accept a list or an object with a ``tasks`` array.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

DATE = re.compile(r"(?:due|deadline|by|before)\s*[:@]?\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", re.I)
AT_DATE = re.compile(r"@\s*([0-9]{4}-[0-9]{2}-[0-9]{2})")
CHECKBOX = re.compile(r"^\s*[-*+]\s+\[([ xX])\]\s+(.+)")
BULLET = re.compile(r"^\s*[-*+]\s+(.+)")
NUMBERED = re.compile(r"^\s*\d+[.)]\s+(.+)")
DONE_PREFIX = re.compile(r"^\s*(?:done|completed|finished)\s*[:—-]\s*", re.I)

TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".text"}
SKIP_PREFIXES = ("#", "//", "<!--", "```", "---", "===")


def _clean_task(text: str) -> tuple[str, str | None]:
    """Return (text without the due clause, due date or None)."""
    due = None
    match = DATE.search(text) or AT_DATE.search(text)
    if match:
        due = match.group(1)
        text = (text[:match.start()] + text[match.end():]).strip(" -–—,:;")
    return " ".join(text.split()), due


def _parse_text_file(path: Path, raw: str, tasks: list[dict[str, Any]]) -> None:
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
        text, due = _clean_task(body)
        if not text or len(text) > 500:
            continue
        tasks.append({"text": text, "due_date": due,
                      "status": "completed" if completed else "pending",
                      "source": str(path)})


def read_planning_notes(notes_dir: Path, today: date | None = None, *, max_files: int | None = None) -> dict[str, Any]:
    today = today or date.today()
    tasks: list[dict[str, Any]] = []
    errors: list[str] = []
    files: list[str] = []
    if not notes_dir.exists():
        return {"tasks": tasks, "missing": True, "errors": errors, "files": files}
    paths = sorted((p for p in notes_dir.iterdir()
                    if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES | {".json"}),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    if max_files is not None:
        paths = paths[:max_files]
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
                    tasks.append({"text": str(item.get("text", item.get("title"))).strip()[:500],
                                  "due_date": str(item.get("due_date", item.get("deadline", "")))[:10] or None,
                                  "status": "completed" if status in {"done", "complete", "completed"} else "pending",
                                  "source": str(path)})
            else:
                _parse_text_file(path, raw, tasks)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}: {exc}")
    for task in tasks:
        due = task["due_date"]
        task["overdue"] = bool(task["status"] == "pending" and due and due < today.isoformat())
        task["due_today"] = bool(task["status"] == "pending" and due == today.isoformat())
    return {"tasks": tasks, "missing": False, "errors": errors, "files": files}
