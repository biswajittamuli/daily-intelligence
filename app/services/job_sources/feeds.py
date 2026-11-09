"""Public job feeds (Atom/RSS) published for subscribers, read with the polite fetcher (robots.txt respected).

A feed entry is a listing link with a title and the feed's published/updated time; the time is stored
with the confidence "feed entry date", never presented as more than that.
"""
from __future__ import annotations

import re
from email.utils import parsedate_to_datetime
from dataclasses import dataclass
from typing import Any

from lxml import etree

from app.services.freshness import parse_date
from app.services.job_sources.models import SourceState
from app.services.job_sources.structured import clean_text


@dataclass(frozen=True)
class Feed:
    source_id: str
    name: str
    url: str
    region: str = "India"


FEEDS = [Feed("feed:hasjob", "Hasjob", "https://hasjob.co/feed")]

LOCATION = re.compile(r"\b(remote|bengaluru|bangalore|hyderabad|pune|mumbai|delhi|new delhi|gurgaon|gurugram|noida|"
                      r"chennai|kochi|ahmedabad|jaipur|kolkata|india)\b", re.I)


def parse_feed(xml_text: str, *, limit: int = 300) -> list[dict[str, Any]]:
    """Atom or RSS entries -> [{title, url, posted_date, location, description}]. Malformed feeds yield []."""
    if not xml_text or "<" not in xml_text:
        return []
    try:
        parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=True, huge_tree=False)
        root = etree.fromstring(xml_text[:3_000_000].encode("utf-8", "replace"), parser)
    except (etree.XMLSyntaxError, ValueError):
        return []
    if root is None:
        return []
    items = []
    for node in list(root.iter("{*}entry")) + list(root.iter("item")):
        def text(*names):
            for name in names:
                found = node.find(name)
                if found is not None and (found.text or "").strip():
                    return found.text.strip()
            return ""
        link = ""
        for candidate in node.findall("{*}link"):
            href = candidate.get("href") or (candidate.text or "").strip()
            if href and candidate.get("rel") in (None, "alternate"):
                link = href
                break
        if not link:
            link = text("link")
        title = clean_text(text("{*}title", "title"), 200)
        if not title or not link.startswith(("http://", "https://")):
            continue
        description = clean_text(text("{*}content", "{*}summary", "description"), 4000)
        raw_date = text("{*}published", "{*}updated", "pubDate")
        posted = parse_date(raw_date)
        if posted is None and raw_date:
            try:  # RSS uses RFC 822 dates ("Sat, 07 Nov 2026 09:00:00 GMT")
                posted = parsedate_to_datetime(raw_date).date()
            except (TypeError, ValueError, IndexError):
                posted = None
        location = LOCATION.search(f"{title} {description[:400]}")
        items.append({"title": title, "url": link, "posted_date": posted.isoformat() if posted else None,
                      "location": location.group(0) if location else None, "description": description,
                      "extraction_method": "public feed", "date_source": "feed entry date"})
        if len(items) >= limit:
            break
    return items


async def read_feeds(http, *, feeds: list[Feed] | None = None, skip: dict[str, str] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Returns (items, reports). Each report is a coverage row for the feed."""
    items, reports = [], []
    for feed in feeds or FEEDS:
        if feed.source_id in (skip or {}):
            reports.append({"feed": feed, "state": SourceState.NOT_TARGETED, "reason": (skip or {})[feed.source_id], "count": 0})
            continue
        result = await http.get(feed.url, accept_json=True)
        if not result.ok:
            reports.append({"feed": feed, "state": result.state, "reason": result.error, "count": 0,
                            "http_status": result.status})
            continue
        parsed = parse_feed(result.text)
        for item in parsed:
            item["_via"] = feed.name
            item["feed_id"] = feed.source_id
        items.extend(parsed)
        reports.append({"feed": feed, "state": SourceState.EXTRACT_OK if parsed else SourceState.EXTRACT_FAILED,
                        "reason": None if parsed else "feed returned no parseable entries", "count": len(parsed),
                        "http_status": result.status})
    return items, reports
