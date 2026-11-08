"""Zero-token company career-board scanning via public ATS job-board APIs.

Idea credited to Career-Ops (github.com/santifer/career-ops, MIT): many employers
publish every opening through a public applicant-tracking-system feed. Reading
those feeds directly gives complete, dated listings without model calls.

Supported public endpoints (read-only, no authentication, no personal data sent):
- Greenhouse: https://boards-api.greenhouse.io/v1/boards/<token>/jobs
- Lever:      https://api.lever.co/v0/postings/<slug>?mode=json
- Ashby:      https://api.ashbyhq.com/posting-api/job-board/<slug>

Only the company identifier is sent; never resume text or profile data.
"""
from __future__ import annotations

import asyncio
import html
import re
import time
from datetime import datetime, timezone
from typing import Any, Callable

import httpx

USER_AGENT = "DailyIntelligence/3.1 (local personal job scanner)"

# Verified on 2026-11-08 to return public boards. Users can add/remove in Settings.
DEFAULT_COMPANIES: list[dict[str, str]] = [
    {"name": "Groww", "ats": "greenhouse", "slug": "groww"},
    {"name": "Databricks", "ats": "greenhouse", "slug": "databricks"},
    {"name": "MongoDB", "ats": "greenhouse", "slug": "mongodb"},
    {"name": "GitLab", "ats": "greenhouse", "slug": "gitlab"},
    {"name": "Cloudflare", "ats": "greenhouse", "slug": "cloudflare"},
    {"name": "Stripe", "ats": "greenhouse", "slug": "stripe"},
    {"name": "Coinbase", "ats": "greenhouse", "slug": "coinbase"},
    {"name": "Rubrik", "ats": "greenhouse", "slug": "rubrik"},
    {"name": "Airbnb", "ats": "greenhouse", "slug": "airbnb"},
    {"name": "HackerRank", "ats": "greenhouse", "slug": "hackerrank"},
    {"name": "Druva", "ats": "greenhouse", "slug": "druva"},
    {"name": "Elastic", "ats": "greenhouse", "slug": "elastic"},
    {"name": "CRED", "ats": "lever", "slug": "cred"},
    {"name": "Meesho", "ats": "lever", "slug": "meesho"},
    {"name": "Zeta", "ats": "lever", "slug": "zeta"},
    {"name": "Paytm", "ats": "lever", "slug": "paytm"},
    {"name": "Spotify", "ats": "lever", "slug": "spotify"},
    {"name": "Sarvam AI", "ats": "ashby", "slug": "sarvam"},
    {"name": "Notion", "ats": "ashby", "slug": "notion"},
    {"name": "OpenAI", "ats": "ashby", "slug": "openai"},
    {"name": "Linear", "ats": "ashby", "slug": "linear"},
    {"name": "Ramp", "ats": "ashby", "slug": "ramp"},
    {"name": "Plaid", "ats": "ashby", "slug": "plaid"},
    {"name": "Supabase", "ats": "ashby", "slug": "supabase"},
    {"name": "PostHog", "ats": "ashby", "slug": "posthog"},
]

ATS_TYPES = {"greenhouse", "lever", "ashby"}
_CACHE: dict[tuple[str, str], tuple[float, list[dict[str, Any]]]] = {}
CACHE_SECONDS = 3 * 3600


def _text(value: Any) -> str:
    raw = html.unescape(str(value or ""))
    raw = re.sub(r"<[^>]+>", " ", raw)
    return " ".join(raw.split())


def _iso(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            return datetime.fromtimestamp(int(value) / 1000, timezone.utc).date().isoformat()
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date().isoformat()
    except (ValueError, OSError):
        return None


def normalize_company(entry: Any) -> dict[str, str] | None:
    if not isinstance(entry, dict):
        return None
    ats = str(entry.get("ats") or "").strip().lower()
    slug = re.sub(r"[^A-Za-z0-9_.-]", "", str(entry.get("slug") or ""))[:80]
    name = " ".join(str(entry.get("name") or slug).split())[:80]
    if ats not in ATS_TYPES or not slug:
        return None
    return {"name": name or slug, "ats": ats, "slug": slug}


def _parse(company: dict[str, str], payload: Any) -> list[dict[str, Any]]:
    ats, name = company["ats"], company["name"]
    jobs: list[dict[str, Any]] = []
    if ats == "greenhouse":
        for item in (payload or {}).get("jobs", []):
            location = (item.get("location") or {}).get("name") or ""
            jobs.append({
                "title": item.get("title"), "employer": item.get("company_name") or name,
                "location": location, "url": item.get("absolute_url"),
                "posted_date": _iso(item.get("first_published") or item.get("updated_at")),
                "description": _text(item.get("content"))[:6000],
                "employment_type": None,
                "remote": "remote" if "remote" in location.casefold() else None,
            })
    elif ats == "lever":
        for item in payload or []:
            categories = item.get("categories") or {}
            location = categories.get("location") or ""
            jobs.append({
                "title": item.get("text"), "employer": name, "location": location,
                "url": item.get("hostedUrl"), "posted_date": _iso(item.get("createdAt")),
                "description": _text(item.get("descriptionPlain") or item.get("description"))[:6000]
                               + " " + " ".join(_text(part.get("content")) for part in item.get("lists") or [])[:3000],
                "employment_type": categories.get("commitment"),
                "remote": item.get("workplaceType"),
                "country": item.get("country"),
            })
    elif ats == "ashby":
        for item in (payload or {}).get("jobs", []):
            if item.get("isListed") is False:
                continue
            address = ((item.get("address") or {}).get("postalAddress") or {})
            location = ", ".join(part for part in (item.get("location"), address.get("addressCountry")) if part)
            jobs.append({
                "title": item.get("title"), "employer": name, "location": location,
                "url": item.get("jobUrl"), "posted_date": _iso(item.get("publishedAt")),
                "description": _text(item.get("descriptionPlain") or item.get("descriptionHtml"))[:6000],
                "employment_type": item.get("employmentType"),
                "remote": "remote" if item.get("isRemote") else item.get("workplaceType"),
            })
    output = []
    for job in jobs:
        if job.get("title") and job.get("url"):
            job["source_platform"] = f"{company['ats']}:{company['slug']}"
            job["ats"] = company["ats"]
            output.append(job)
    return output


def _endpoint(company: dict[str, str]) -> str:
    slug = company["slug"]
    return {
        "greenhouse": f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
        "lever": f"https://api.lever.co/v0/postings/{slug}?mode=json",
        "ashby": f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
    }[company["ats"]]


async def fetch_company_jobs(companies: list[dict[str, Any]], *, timeout: float = 20.0,
                             concurrency: int = 4,
                             progress: Callable[[str], None] | None = None,
                             cancel: Callable[[], None] | None = None,
                             client: httpx.AsyncClient | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fetch every configured company board. Returns (jobs, per-company coverage)."""
    progress = progress or (lambda _: None)
    clean = [company for company in (normalize_company(item) for item in companies) if company]
    semaphore = asyncio.Semaphore(max(1, concurrency))
    coverage: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    owns = client is None
    client = client or httpx.AsyncClient(timeout=timeout, headers={"User-Agent": USER_AGENT},
                                         follow_redirects=True)

    async def one(company: dict[str, str]) -> None:
        key = (company["ats"], company["slug"])
        cached = _CACHE.get(key)
        if cached and time.time() - cached[0] < CACHE_SECONDS:
            results.extend(cached[1])
            coverage.append({"platform": company["name"], "method": f"{company['ats']} API",
                             "status": "ok (cached)", "results": len(cached[1])})
            return
        async with semaphore:
            if cancel:
                cancel()
            try:
                response = await client.get(_endpoint(company))
                if response.status_code in {401, 403, 429}:
                    coverage.append({"platform": company["name"], "method": f"{company['ats']} API",
                                     "status": f"blocked ({response.status_code})", "results": 0})
                    return
                if response.status_code == 404:
                    coverage.append({"platform": company["name"], "method": f"{company['ats']} API",
                                     "status": "board not found (404)", "results": 0})
                    return
                response.raise_for_status()
                jobs = _parse(company, response.json())
            except (httpx.HTTPError, ValueError) as exc:
                coverage.append({"platform": company["name"], "method": f"{company['ats']} API",
                                 "status": f"error: {type(exc).__name__}", "results": 0})
                return
        _CACHE[key] = (time.time(), jobs)
        results.extend(jobs)
        coverage.append({"platform": company["name"], "method": f"{company['ats']} API",
                         "status": "ok", "results": len(jobs)})
        progress(f"{company['name']}: {len(jobs)} openings")

    try:
        await asyncio.gather(*(one(company) for company in clean))
    finally:
        if owns:
            await client.aclose()
    return results, coverage
