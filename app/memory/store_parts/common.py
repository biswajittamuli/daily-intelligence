"""Helpers shared by Store and its mixins: JSON columns and (de)serialisation, dedup keys."""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any


JSON_COLUMNS = {
    "job_listings": ("skills_json", "evidence_json", "raw_json", "resume_scores_json",
                     "sources_json", "eligibility_json", "verify_history_json", "conflicts_json"),
    "employers": ("locations_json", "funding_json", "discovery_sources_json", "aliases_json", "evidence_json",
                  "career_discovery_json"),
    "applications": ("interview_dates_json", "history_json"),
    "recruitment_notices": ("evidence_json", "raw_json"),
    "exam_events": ("evidence_json", "raw_json"),
    "intel_items": ("evidence_json", "raw_json"),
}


def _resume_label(filename: str | None) -> str:
    stem = Path(str(filename or "Resume")).stem
    clean = " ".join(stem.replace("_", " ").replace("-", " ").split())
    return clean[:60] or "Resume"


def _json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


_CITY_ALIASES = {"bangalore": "bengaluru", "gurgaon": "gurugram", "bombay": "mumbai", "new delhi": "delhi",
                 "madras": "chennai", "calcutta": "kolkata", "cochin": "kochi"}


def dedup_key(record: dict[str, Any]) -> str | None:
    """employer|normalized title|city — None when employer or title is unknown (no risky merges)."""
    employer = re.sub(r"[^a-z0-9]+", " ", str(record.get("employer") or "").casefold()).strip()
    title = re.sub(r"\b(?:at|@)\s+.*$", "", str(record.get("title") or "").casefold())
    title = re.sub(r"[^a-z0-9+#]+", " ", title).strip()
    if not employer or not title or employer in {"none", "company hidden", "confidential"}:
        return None
    employer = re.sub(r"\b(private limited|pvt ltd|pvt|ltd|limited|inc|llc|technologies|technology|labs?|"
                      r"careers|job board|india)\b", "", employer).strip()
    city = str(record.get("location") or "").casefold().split(",")[0].strip()
    city = re.sub(r"[^a-z ]+", "", city).strip()
    city = _CITY_ALIASES.get(city, city)
    return f"{employer}|{title}|{city}"


def _merge_sources(existing: list[Any], new: list[Any]) -> list[dict[str, Any]]:
    """Keep every distinct source reference for a listing (platform + URL)."""
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in list(existing or []) + list(new or []):
        if not isinstance(item, dict) or not item.get("url"):
            continue
        key = str(item["url"]).rstrip("/").casefold()
        if key in seen:
            continue
        seen.add(key)
        entry = {"platform": item.get("platform"), "url": item["url"], "via": item.get("via")}
        for extra in ("method", "retrieved_at", "kind", "policy"):
            if item.get(extra):
                entry[extra] = item[extra]
        output.append(entry)
    return output[:16]


def _iso_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None
