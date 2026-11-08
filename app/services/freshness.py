"""Deterministic date parsing and freshness classification."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any


FRESHNESS_WINDOWS = {
    "today": 1,
    "3d": 3,
    "7d": 7,
    "30d": 30,
    "90d": 90,
    "all": None,
}

DEFAULT_WINDOWS = {
    "jobs": 30,
    "government": 90,
    "exams": 365,
    "news": 7,
    "papers": 30,
}


def parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for pattern in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d",
                    "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y",
                    "%B %Y", "%b %Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


def window_days(value: Any, category: str) -> int | None:
    if value in FRESHNESS_WINDOWS:
        return FRESHNESS_WINDOWS[value]
    try:
        number = int(value)
        return max(1, min(3650, number)) if number > 0 else None
    except (TypeError, ValueError):
        return DEFAULT_WINDOWS.get(category, 30)


def classify_freshness(*, published: Any = None, updated: Any = None,
                       deadline: Any = None, category: str = "news",
                       window: Any = None, today: date | None = None) -> dict[str, Any]:
    """Return a freshness label without silently replacing one date with another."""
    today = today or date.today()
    days = window_days(window, category)
    published_date = parse_date(published)
    updated_date = parse_date(updated)
    deadline_date = parse_date(deadline)

    claims = []
    if published:
        claims.append({"source": "publication", "value": str(published)})
    if updated:
        claims.append({"source": "updated", "value": str(updated)})
    if deadline:
        claims.append({"source": "deadline", "value": str(deadline)})

    if published_date and updated_date and published_date != updated_date:
        label = "date_conflict"
        reason = "Publication and update dates disagree; both are retained."
    elif published_date and days is not None and published_date >= today - timedelta(days=days):
        label = "recent"
        reason = f"Published within the last {days} days."
    elif updated_date and days is not None and updated_date >= today - timedelta(days=days):
        label = "updated_recently"
        reason = f"Updated within the last {days} days."
    elif published_date and days is not None:
        label = "old"
        reason = f"Published more than {days} days ago."
    elif published_date or updated_date:
        label = "recent" if days is None else "unverified"
        reason = "A date is present but could not be independently verified."
    else:
        label = "date_unavailable"
        reason = "No publication date was extracted."

    status = "unknown"
    if deadline_date:
        status = "closed" if deadline_date < today else "open"
    return {
        "label": label,
        "reason": reason,
        "window_days": days,
        "published_date": published_date.isoformat() if published_date else None,
        "updated_date": updated_date.isoformat() if updated_date else None,
        "deadline": deadline_date.isoformat() if deadline_date else None,
        "deadline_status": status,
        "claims": claims,
    }


def classify_event_date(value: Any, text: str = "", today: date | None = None) -> dict[str, Any]:
    """Classify an examination event date as announced, tentative, past or unknown."""
    today = today or date.today()
    event_date = parse_date(value)
    lowered = (text or "").casefold()
    tentative = any(word in lowered for word in ("tentative", "expected", "likely", "subject to"))
    if event_date is None:
        return {"date": None, "status": "unverified", "tentative": tentative}
    if tentative:
        status = "tentative"
    elif event_date < today:
        status = "past"
    else:
        status = "announced"
    return {"date": event_date.isoformat(), "status": status, "tentative": tentative}
