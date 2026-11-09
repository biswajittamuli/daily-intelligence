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

USER_AGENT = "DailyIntelligence/3.3 (local personal job scanner)"

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

ATS_TYPES = {"greenhouse", "lever", "ashby", "workable", "smartrecruiters", "recruitee"}
_CACHE: dict[tuple[str, str], tuple[float, list[dict[str, Any]]]] = {}
CACHE_SECONDS = 3 * 3600


def is_arrangement_only(location: str) -> bool:
    """True when a location names only a work arrangement ("Hybrid", "Distributed; Hybrid"), no place."""
    from app.services.job_matching import strip_arrangement
    return bool(str(location or "").strip()) and not strip_arrangement(location)


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
            offices = [str(office.get("name") or "").strip() for office in item.get("offices") or []]
            offices = [office for office in offices if office]
            arrangement = None
            if offices and is_arrangement_only(location):
                # Boards such as Cloudflare's put only "Hybrid"/"Distributed" here; the place is in offices.
                arrangement, location = location, "; ".join(dict.fromkeys(offices))
            jobs.append({
                "title": item.get("title"), "employer": item.get("company_name") or name,
                "location": location, "url": item.get("absolute_url"),
                "posted_date": _iso(item.get("first_published")),
                "updated_date": _iso(item.get("updated_at")),
                "description": _text(item.get("content"))[:12000],
                "employment_type": None,
                "remote": "remote" if "remote" in f"{location} {arrangement or ''}".casefold() else arrangement,
            })
    elif ats == "lever":
        for item in payload or []:
            categories = item.get("categories") or {}
            location = categories.get("location") or ""
            extra = [str(place) for place in categories.get("allLocations") or [] if place and place != location]
            if extra:
                location = "; ".join([location, *extra] if location else extra)
            jobs.append({
                "title": item.get("text"), "employer": name, "location": location,
                "url": item.get("hostedUrl"), "posted_date": _iso(item.get("createdAt")),
                "description": (_text(item.get("descriptionPlain") or item.get("description"))[:8000] + "\n"
                                + "\n".join(f"{_text(part.get('text'))}:\n{_text(part.get('content'))}"
                                             for part in item.get("lists") or [])[:6000]),
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
            extra = [str(entry.get("location") or "") for entry in item.get("secondaryLocations") or []
                     if isinstance(entry, dict)]
            extra = [place for place in extra if place and place not in location]
            if extra:
                location = "; ".join([location, *extra] if location else extra)
            jobs.append({
                "title": item.get("title"), "employer": name, "location": location,
                "url": item.get("jobUrl"), "posted_date": _iso(item.get("publishedAt")),
                "description": _text(item.get("descriptionPlain") or item.get("descriptionHtml"))[:12000],
                "employment_type": item.get("employmentType"),
                "remote": "remote" if item.get("isRemote") else item.get("workplaceType"),
            })
    elif ats == "workable":
        for item in (payload or {}).get("jobs", []):
            location = ", ".join(part for part in (item.get("city"), item.get("state"), item.get("country")) if part)
            jobs.append({
                "title": item.get("title"), "employer": (payload or {}).get("name") or name, "location": location,
                "url": item.get("url") or item.get("shortlink"), "application_url": item.get("application_url"),
                "posted_date": _iso(item.get("published_on") or item.get("created_at")),
                "description": _text(item.get("description"))[:12000],
                "employment_type": item.get("employment_type"),
                "remote": "remote" if item.get("telecommuting") else None,
                "requisition_id": item.get("shortcode"),
            })
    elif ats == "smartrecruiters":
        for item in (payload or {}).get("content", []):
            loc = item.get("location") or {}
            location = ", ".join(str(part) for part in (loc.get("city"), loc.get("region"),
                                                         str(loc.get("country") or "").upper()) if part)
            company_id = (item.get("company") or {}).get("identifier") or company_slug(company)
            jobs.append({
                "title": item.get("name"), "employer": (item.get("company") or {}).get("name") or name,
                "location": location, "url": f"https://jobs.smartrecruiters.com/{company_id}/{item.get('id')}",
                "posted_date": _iso(item.get("releasedDate")), "description": "",
                "employment_type": (item.get("typeOfEmployment") or {}).get("label"),
                "remote": "remote" if loc.get("remote") else None, "requisition_id": item.get("refNumber"),
                "experience_level": (item.get("experienceLevel") or {}).get("label"),
            })
    elif ats == "recruitee":
        for item in (payload or {}).get("offers", []):
            location = item.get("location") or ", ".join(
                part for part in (item.get("city"), item.get("country")) if part)
            jobs.append({
                "title": item.get("title"), "employer": item.get("company_name") or name, "location": location,
                "url": item.get("careers_url") or item.get("careers_apply_url"),
                "application_url": item.get("careers_apply_url"),
                "posted_date": _iso(item.get("published_at") or item.get("created_at")),
                "description": _text(f"{item.get('description') or ''} {item.get('requirements') or ''}")[:12000],
                "employment_type": item.get("employment_type_code"),
                "remote": "remote" if item.get("remote") else None,
                "requisition_id": item.get("slug"),
            })
    output = []
    for job in jobs:
        if job.get("title") and job.get("url"):
            job["source_platform"] = f"{company['ats']}:{company['slug']}"
            job["ats"] = company["ats"]
            output.append(job)
    return output


PAGE_SIZE = {"lever": 100, "smartrecruiters": 100}
MAX_PAGES = 30


def _page_url(company: dict[str, str], offset: int) -> str:
    base = _endpoint(company)
    if company["ats"] == "lever":
        return f"{base}&skip={offset}&limit={PAGE_SIZE['lever']}"
    if company["ats"] == "smartrecruiters":
        return base.replace("limit=100", f"limit={PAGE_SIZE['smartrecruiters']}&offset={offset}")
    return base


async def _read_all_pages(client: httpx.AsyncClient, company: dict[str, str]) -> tuple[list[dict[str, Any]], int, str | None]:
    """Enumerate a board completely. Returns (jobs, pages read, error status or None).

    Greenhouse, Ashby, Workable and Recruitee return every posting in one response. Lever and
    SmartRecruiters are paged (skip/limit, offset/limit); pages are read until a short page, the
    reported total, or MAX_PAGES. A failure after the first page is reported as partial.
    """
    jobs: list[dict[str, Any]] = []
    paged = company["ats"] in PAGE_SIZE
    offset, pages = 0, 0
    while True:
        response = await client.get(_page_url(company, offset) if paged else _endpoint(company))
        pages += 1
        if response.status_code in {401, 403, 429}:
            status = f"blocked ({response.status_code})"
            return jobs, pages, status if not jobs else f"partial: {status} on page {pages}"
        if response.status_code == 404:
            return jobs, pages, "board not found (404)" if not jobs else f"partial: 404 on page {pages}"
        if response.status_code >= 400:
            if not jobs:
                response.raise_for_status()
            return jobs, pages, f"partial: HTTP {response.status_code} on page {pages}"
        payload = response.json()
        page_jobs = _parse(company, payload)
        jobs.extend(page_jobs)
        if not paged:
            return jobs, pages, None
        size = PAGE_SIZE[company["ats"]]
        raw_count = len(payload) if isinstance(payload, list) else len((payload or {}).get("content") or [])
        total = (payload or {}).get("totalFound") if isinstance(payload, dict) else None
        offset += size
        if raw_count < size or (total is not None and offset >= int(total)):
            return jobs, pages, None
        if pages >= MAX_PAGES:
            return jobs, pages, f"partial: stopped after {MAX_PAGES} pages"


def company_slug(company: dict[str, str]) -> str:
    return company.get("slug", "")


def _endpoint(company: dict[str, str]) -> str:
    slug = company["slug"]
    return {
        "workable": f"https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true",
        "smartrecruiters": f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100",
        "greenhouse": f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
        "lever": f"https://api.lever.co/v0/postings/{slug}?mode=json",
        "ashby": f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
        "recruitee": f"https://{slug}.recruitee.com/api/offers/",
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
                             "status": "ok (cached)", "results": len(cached[1]), "ats": company["ats"],
                             "slug": company["slug"], "complete": True})
            return
        async with semaphore:
            if cancel:
                cancel()
            try:
                jobs, pages, error = await _read_all_pages(client, company)
            except (httpx.HTTPError, ValueError) as exc:
                coverage.append({"platform": company["name"], "method": f"{company['ats']} API",
                                 "status": f"error: {type(exc).__name__}", "results": 0,
                                 "ats": company["ats"], "slug": company["slug"]})
                return
            if error:
                coverage.append({"platform": company["name"], "method": f"{company['ats']} API", "status": error,
                                 "results": len(jobs), "pages": pages, "ats": company["ats"], "slug": company["slug"]})
                if not jobs:
                    return
        if not error:  # partial reads are never cached, so the next run retries the whole board
            _CACHE[key] = (time.time(), jobs)
        results.extend(jobs)
        if not error:
            coverage.append({"platform": company["name"], "method": f"{company['ats']} API",
                             "status": "ok", "results": len(jobs), "pages": pages,
                             "ats": company["ats"], "slug": company["slug"], "complete": True})
        progress(f"{company['name']}: {len(jobs)} openings")

    try:
        await asyncio.gather(*(one(company) for company in clean))
    finally:
        if owns:
            await client.aclose()
    return results, coverage
