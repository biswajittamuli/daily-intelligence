"""Deterministic date parsing and freshness classification."""
from __future__ import annotations

import re
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


_RELATIVE_TODAY = re.compile(
    r"\b(?:posted\s+|active\s+|updated\s+)?(?:today|just\s+now|few\s+(?:hours|minutes)\s+ago|"
    r"\d{1,2}\s*(?:hours?|hrs?|h|minutes?|mins?)\s+ago)\b", re.I)
_RELATIVE_YESTERDAY = re.compile(r"\byesterday\b", re.I)
_RELATIVE_AGO = re.compile(
    r"\b(\d{1,3})\s*\+?\s*(days?|d|weeks?|wks?|w|months?|mos?)\s+ago\b", re.I)


def parse_relative_date(text: Any, today: date | None = None) -> date | None:
    """Parse job-board phrases such as "Posted 3 days ago", "30+ days ago", "today".

    Returns the earliest-reading (most specific) date found in the text, or None.
    Months are approximated as 30 days; this is labelled relative, not exact.
    """
    if not isinstance(text, str) or not text:
        return None
    today = today or date.today()
    match = _RELATIVE_AGO.search(text)
    if match:
        amount = int(match.group(1))
        unit = match.group(2).casefold()
        if unit.startswith(("w",)):
            days = amount * 7
        elif unit.startswith(("mo", "month")):
            days = amount * 30
        else:
            days = amount
        return today - timedelta(days=min(days, 3650))
    if _RELATIVE_TODAY.search(text):
        return today
    if _RELATIVE_YESTERDAY.search(text):
        return today - timedelta(days=1)
    return None


# ----------------------------------------------------------------- v4: posting-date provenance and buckets
DATE_CONFIDENCE = {
    "employer ATS": "high", "JobPosting datePosted": "high", "career page": "medium",
    "feed entry date": "medium", "listing text (relative date)": "medium",
    "search engine page date": "low", "model-extracted from page text": "low",
    # v4.3
    "employer page label": "medium", "listing page label": "medium", "job platform API": "medium",
    "aggregator API": "medium",
}
_RANK = {"high": 3, "medium": 2, "low": 1, "unknown": 0, None: 0}


def date_confidence(source: str | None, posted: Any) -> str:
    if not posted:
        return "unknown"
    return DATE_CONFIDENCE.get(str(source or ""), "low")


def stronger_date(new_date: Any, new_confidence: str | None, old_date: Any, old_confidence: str | None) -> bool:
    """True when a newly observed posting date may replace the stored one (never downgrade confidence)."""
    if not new_date:
        return False
    if not old_date:
        return True
    return _RANK.get(new_confidence, 0) > _RANK.get(old_confidence, 0)


BUCKET_LABEL = {"new_today": "Published today", "new_24h": "Published yesterday", "new_3d": "Published in the last 3 days",
                "new_7d": "Published in the last 7 days", "older_open": "Older but still open", "date_unknown": "Date unknown",
                "closed": "Closed", "expired": "Expired", "verification_required": "Older · verification required"}


def freshness_bucket(job: dict[str, Any], *, now: Any = None, lifecycle_state: str | None = None) -> dict[str, Any]:
    """Freshness from a stated publication date only (v4.3).

    When no trustworthy publication date exists the key is ``date_unknown`` and the label says so, followed by
    when the app first discovered the listing. A listing discovered today but published a month ago is never
    "new"; re-fetching a listing never changes its first-seen time.
    """
    from datetime import datetime, timezone
    from app.services.vacancy_validation import publication_freshness
    now = now or datetime.now(timezone.utc)
    state = lifecycle_state or ""
    if state in {"closed", "expired"} or job.get("status") in {"closed", "expired"}:
        key = "expired" if (state == "expired" or job.get("status") == "expired") else "closed"
        return {"key": key, "label": BUCKET_LABEL[key], "basis": "status"}
    fresh = publication_freshness(job, now=now)
    base = {"window": fresh["window"], "window_label": fresh["window_label"], "published_at": fresh["published_at"],
            "first_discovered": fresh["first_discovered"], "newly_published": fresh["newly_published"],
            "newly_discovered": fresh["newly_discovered"]}
    if fresh["published_at"] is None:
        return {"key": "date_unknown", "label": fresh["label"], "basis": "no trustworthy publication date",
                "age_days": None, **base}
    age_days = fresh["age_days"]
    basis = f"posted {fresh['published_at']} ({job.get('posted_date_source') or 'source'})"
    if age_days <= 0:
        key = "new_today"
    elif age_days <= 1:
        key = "new_24h"
    elif age_days <= 3:
        key = "new_3d"
    elif age_days <= 7:
        key = "new_7d"
    else:
        key = "older_open" if state in {"open_verified", "open_page_checked"} else "verification_required"
    label = fresh["label"] + (" · still open" if key == "older_open" else "")
    return {"key": key, "label": label, "basis": basis, "age_days": age_days, **base}


def vacancy_view(job: dict[str, Any], lifecycle_state: str) -> dict[str, Any]:
    """The normalised freshness/verification fields every vacancy exposes through the API."""
    vacancy = {"closed": "closed", "expired": "expired"}.get(lifecycle_state) or (
        "open" if lifecycle_state in {"open_verified", "open_page_checked", "open_not_recent"} else "unknown")
    verification = {"open_verified": "verified_employer", "open_page_checked": "verified_third_party",
                    "open_not_recent": "verification_due", "inaccessible": "inaccessible",
                    "pending_verification": "pending", "closed": "verified_closed", "expired": "verified_expired"
                    }.get(lifecycle_state, "unverified")
    return {
        "first_seen_at": job.get("first_seen"), "last_seen_at": job.get("last_seen"),
        "published_at": job.get("posted_date"), "updated_at": job.get("updated_date"),
        "verified_at": job.get("last_verified"), "application_deadline": job.get("deadline"),
        "posting_date_source": job.get("posted_date_source"),
        "posting_date_confidence": job.get("posting_date_confidence") or date_confidence(job.get("posted_date_source"),
                                                                                         job.get("posted_date")),
        "verification_status": verification, "vacancy_status": vacancy,
        "source_url": job.get("original_url"), "application_url": job.get("application_url"),
    }
