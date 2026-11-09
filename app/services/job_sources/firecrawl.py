"""Optional Firecrawl fallback for difficult *public employer* pages.

Off unless ``FIRECRAWL_API_KEY`` is set and ``jobs.firecrawl_enabled`` is true in preferences.
Only the public page URL is sent — never resume text, profile data or search requests — and it is
never used for job portals whose policy is "search results only" (the caller checks
``portals.may_fetch``). Local Playwright rendering is always tried first.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from app.services.job_sources.models import SourceState

API_URL = "https://api.firecrawl.dev/v1/scrape"


def configured(preferences: dict[str, Any] | None = None) -> bool:
    enabled = bool(((preferences or {}).get("jobs") or {}).get("firecrawl_enabled"))
    return enabled and bool(os.getenv("FIRECRAWL_API_KEY", "").strip())


async def scrape(url: str, *, timeout: float = 45.0, transport: httpx.AsyncBaseTransport | None = None,
                 api_key: str | None = None) -> dict[str, Any]:
    """Return {state, html, links, error}. Never raises for remote failures."""
    key = (api_key or os.getenv("FIRECRAWL_API_KEY", "")).strip()
    if not key:
        return {"state": SourceState.POLICY_SKIPPED, "html": "", "links": [], "error": "FIRECRAWL_API_KEY not set"}
    payload = {"url": url, "formats": ["html", "links"], "onlyMainContent": False, "timeout": int(timeout * 1000)}
    try:
        async with httpx.AsyncClient(timeout=timeout + 5, transport=transport) as client:
            response = await client.post(API_URL, json=payload, headers={"Authorization": f"Bearer {key}"})
    except httpx.HTTPError as exc:
        return {"state": SourceState.UNAVAILABLE, "html": "", "links": [], "error": type(exc).__name__}
    if response.status_code != 200:
        return {"state": SourceState.from_http(response.status_code), "html": "", "links": [],
                "error": f"Firecrawl HTTP {response.status_code}"}
    try:
        data = (response.json() or {}).get("data") or {}
    except ValueError:
        return {"state": SourceState.UNSUPPORTED, "html": "", "links": [], "error": "invalid JSON"}
    links = [{"url": link, "text": "", "label": "", "region": "main"} for link in data.get("links") or []
             if isinstance(link, str)]
    return {"state": SourceState.FETCH_OK, "html": str(data.get("html") or "")[:2_000_000], "links": links, "error": None}
