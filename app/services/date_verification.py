"""Deterministic comparison of publication-date claims from source metadata."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any


def _date(value: Any) -> date | None:
    if not isinstance(value, (str, date, datetime)):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    value = value.strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for pattern in ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    return None


def verify_publication_dates(source: dict[str, Any]) -> dict[str, Any]:
    """Annotate date claims; a lone search date is never considered verified."""
    retrieval = source.get("retrieval_metadata") or {}
    search_date = source.get("publish_date") or source.get("published_date")
    page_date = next((retrieval.get(key) for key in
                      ("publish_date", "published_date", "date_published", "publication_date")
                      if retrieval.get(key)), None)
    claims = []
    if search_date:
        claims.append({"source": "search result", "value": str(search_date)})
    if page_date:
        claims.append({"source": "fetched page metadata", "value": str(page_date)})
    source["publication_date_claims"] = claims
    if search_date and page_date:
        left, right = _date(search_date), _date(page_date)
        source["date_verification"] = (
            "unverified" if left is None or right is None
            else "consistent" if left == right
            else "inconsistent"
        )
    elif search_date or page_date:
        source["date_verification"] = "unverified"
    else:
        source["date_verification"] = "not_available"
    return source
