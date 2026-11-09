"""Job-search APIs (v4.3): structured vacancies from providers that permit programmatic access.

Each adapter exposes the same operations: build queries, call the API (with timeouts, through the polite
fetcher), normalise results into the common candidate shape, and report one coverage row per provider.
A provider failure never stops discovery; a provider without its key reports "not configured".

- Himalayas: free public JSON API, no key. Remote jobs with explicit ``locationRestrictions``, a publication
  timestamp and an expiry. robots.txt disallows ``&page=`` URLs, so only page 1 of each query is read.
- Adzuna (optional ``ADZUNA_APP_ID`` + ``ADZUNA_APP_KEY``): official REST API for the Indian market.
- Google for Jobs through SerpApi (optional ``SERPAPI_API_KEY``): Google's job index, which includes listings
  from LinkedIn, Naukri, Indeed and foundit, with one apply link per site. This is the compliant route to those
  portals, whose terms forbid fetching their pages directly.

Only role titles and a location are sent to these providers, never resume content.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import urlencode, urlsplit

from app.services.freshness import parse_date, parse_relative_date
from app.services.job_sources.models import SourceState
from app.services.job_sources.structured import clean_text

# Keyed REST APIs whose robots.txt addresses crawlers, not API clients holding a key under the API terms.
KEYED_API_HOSTS = {"api.adzuna.com", "serpapi.com"}


@dataclass(frozen=True)
class JobAPI:
    source_id: str
    name: str
    env: tuple[str, ...] = ()
    max_queries: int = 4

    def configured(self) -> bool:
        return all(os.getenv(name, "").strip() for name in self.env)


HIMALAYAS = JobAPI("api:himalayas", "Himalayas remote-jobs API", (), 4)
ADZUNA = JobAPI("api:adzuna", "Adzuna India API", ("ADZUNA_APP_ID", "ADZUNA_APP_KEY"), 4)
GOOGLE_JOBS = JobAPI("api:google-jobs", "Google for Jobs (SerpApi)", ("SERPAPI_API_KEY",), 2)
APIS = [HIMALAYAS, ADZUNA, GOOGLE_JOBS]
BY_ID = {api.source_id: api for api in APIS}


def _text(value: Any, limit: int = 8000) -> str:
    return clean_text(re.sub(r"<[^>]+>", " ", str(value or "")), limit)


def _restriction_label(restrictions: list[str]) -> str:
    """Short location text; the full list stays in location_restrictions."""
    if not restrictions:
        return "Worldwide"
    india = next((r for r in restrictions if r.casefold() == "india"), None)
    if india and len(restrictions) > 1:
        return f"India (+{len(restrictions) - 1} other countries)"
    return ", ".join(restrictions[:4]) + (f" (+{len(restrictions) - 4} more)" if len(restrictions) > 4 else "")


# ------------------------------------------------------------------ parsers (pure; tested with fixtures)
def parse_himalayas(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for job in (payload or {}).get("jobs") or []:
        url = str(job.get("guid") or job.get("applicationLink") or "").split("?")[0]
        title = clean_text(job.get("title"), 200)
        if not url.startswith("https://") or not title:
            continue
        restrictions = [str(item) for item in job.get("locationRestrictions") or []]
        posted = None
        if job.get("pubDate"):
            try:
                posted = datetime.fromtimestamp(int(job["pubDate"]), tz=timezone.utc).date().isoformat()
            except (TypeError, ValueError, OSError):
                posted = None
        expiry = None
        if job.get("expiryDate"):
            try:
                expiry = datetime.fromtimestamp(int(job["expiryDate"]), tz=timezone.utc).date().isoformat()
            except (TypeError, ValueError, OSError):
                expiry = None
        items.append({
            "title": title, "url": url, "employer": clean_text(job.get("companyName"), 120),
            "location": "Remote — " + _restriction_label(restrictions), "remote": "remote",
            "location_restrictions": restrictions, "posted_date": posted, "date_source": "job platform API",
            "valid_through": expiry, "employment_type": job.get("employmentType"),
            "description": _text(job.get("description") or job.get("excerpt")),
            "seniority": job.get("seniority") or [], "extraction_method": "Himalayas public API",
            "status_hint": "open" if not expiry or expiry >= date.today().isoformat() else "expired",
            "application_url": url, "api_id": HIMALAYAS.source_id,
        })
    return items


def parse_adzuna(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for job in (payload or {}).get("results") or []:
        url = str(job.get("redirect_url") or "")
        title = clean_text(job.get("title"), 200)
        if not url.startswith("https://") or not title:
            continue
        created = parse_date(str(job.get("created") or "")[:10])
        items.append({
            "title": title, "url": url, "employer": clean_text((job.get("company") or {}).get("display_name"), 120),
            "location": clean_text((job.get("location") or {}).get("display_name"), 120),
            "posted_date": created.isoformat() if created else None, "date_source": "aggregator API",
            "employment_type": job.get("contract_time") or job.get("contract_type"),
            "description": _text(job.get("description"), 4000), "requisition_id": None,
            "extraction_method": "Adzuna API", "api_id": ADZUNA.source_id,
            "salary": (f"{int(job['salary_min'])}–{int(job['salary_max'])}" if job.get("salary_min") and job.get("salary_max")
                       else None),
        })
    return items


def parse_google_jobs(payload: dict[str, Any], *, today: date | None = None) -> list[dict[str, Any]]:
    """Google for Jobs results. The employer's own apply link is preferred; every site is kept as provenance."""
    from app.services.job_sources import portals as portal_policy

    today = today or date.today()
    items = []
    for job in (payload or {}).get("jobs_results") or []:
        title = clean_text(job.get("title"), 200)
        options = [o for o in job.get("apply_options") or [] if str(o.get("link") or "").startswith("https://")]
        if not title or not options:
            continue
        employer_link = next((o for o in options if portal_policy.portal_for(o["link"]) is None
                              and not re.search(r"(google|adzuna|jooble|talent\.com|simplyhired|glassdoor|ziprecruiter)\.",
                                                o["link"])), None)
        primary = employer_link or options[0]
        posted_text = str((job.get("detected_extensions") or {}).get("posted_at") or "")
        posted = parse_relative_date(posted_text, today) if posted_text else None
        sources = [{"platform": urlsplit(o["link"]).hostname, "url": o["link"], "via": f"Google for Jobs · {o.get('title') or ''}".strip(" ·"),
                    "kind": "google jobs apply option"} for o in options]
        items.append({
            "title": title, "url": primary["link"], "employer": clean_text(job.get("company_name"), 120),
            "location": clean_text(job.get("location"), 120),
            "remote": "remote" if (job.get("detected_extensions") or {}).get("work_from_home") else None,
            "posted_date": posted.isoformat() if posted else None,
            "date_source": "listing text (relative date)" if posted else None,
            "employment_type": (job.get("detected_extensions") or {}).get("schedule_type"),
            "description": _text(job.get("description"), 6000), "extraction_method": "Google for Jobs (SerpApi)",
            "application_url": employer_link["link"] if employer_link else None,
            "extra_sources": sources, "via_text": job.get("via"), "api_id": GOOGLE_JOBS.source_id,
        })
    return items


# ------------------------------------------------------------------ request builders
def himalayas_url(query: str) -> str:
    return "https://himalayas.app/jobs/api/search?" + urlencode({"q": query, "country": "India", "sort": "recent"})


def adzuna_url(query: str, where: str) -> str:
    params = {"app_id": os.getenv("ADZUNA_APP_ID", ""), "app_key": os.getenv("ADZUNA_APP_KEY", ""),
              "what": query, "results_per_page": 50, "max_days_old": 30, "sort_by": "date",
              "content-type": "application/json"}
    if where and where.casefold() != "india":
        params["where"] = where
    return "https://api.adzuna.com/v1/api/jobs/in/search/1?" + urlencode(params)


def google_jobs_url(query: str, where: str) -> str:
    return "https://serpapi.com/search.json?" + urlencode({
        "engine": "google_jobs", "q": f"{query} {where}".strip(), "gl": "in", "hl": "en",
        "location": "India", "api_key": os.getenv("SERPAPI_API_KEY", "")})


async def read_job_apis(http, roles: list[str], *, location: str = "India", skip: dict[str, str] | None = None,
                        apis: list[JobAPI] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Query every configured job API. Returns (items, reports); each report is one coverage row per API."""
    import json

    items: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    where = "" if re.fullmatch(r"(india\s*)+", (location or "").casefold().strip()) else location
    for api in apis or APIS:
        if api.source_id in (skip or {}):
            reports.append({"api": api, "state": SourceState.NOT_TARGETED, "reason": (skip or {})[api.source_id],
                            "count": 0, "queries": 0})
            continue
        if not api.configured():
            reports.append({"api": api, "state": "not_configured", "count": 0, "queries": 0,
                            "reason": "Add the key in Settings → API keys (optional)"})
            continue
        found, errors, statuses, queries = [], [], [], 0
        for role in [r for r in roles if r][: api.max_queries]:
            queries += 1
            if api is HIMALAYAS:
                url, robots, cache = himalayas_url(role), True, True
            elif api is ADZUNA:
                url, robots, cache = adzuna_url(role, where), False, False
            else:
                url, robots, cache = google_jobs_url(role, where or "India"), False, False
            result = await http.get(url, accept_json=True, robots=robots, use_cache=cache)
            statuses.append(result.status)
            if not result.ok:
                errors.append(f"{SourceState.LABELS.get(result.state, result.state)}"
                              f"{' (HTTP ' + str(result.status) + ')' if result.status else ''}")
                if result.state in {SourceState.RATE_LIMITED, SourceState.ACCESS_DENIED, SourceState.AUTH_REQUIRED}:
                    break
                continue
            try:
                payload = json.loads(result.text)
            except ValueError:
                errors.append("response was not JSON")
                continue
            parsed = parse_himalayas(payload) if api is HIMALAYAS else parse_adzuna(payload) if api is ADZUNA \
                else parse_google_jobs(payload)
            for item in parsed:
                item["_via"] = api.name
                item["_query"] = role
            found.extend(parsed)
        if found:
            state = SourceState.PARTIAL if errors else SourceState.EXTRACT_OK
        elif errors:
            state = SourceState.RATE_LIMITED if any("Rate" in e for e in errors) else \
                SourceState.AUTH_REQUIRED if any("401" in e or "403" in e for e in errors) else SourceState.UNAVAILABLE
        else:
            state = SourceState.NO_RESULTS
        items.extend(found)
        reports.append({"api": api, "state": state, "count": len(found), "queries": queries,
                        "reason": "; ".join(dict.fromkeys(errors))[:200] or None,
                        "http_status": next((s for s in statuses if s), None)})
    return items, reports
