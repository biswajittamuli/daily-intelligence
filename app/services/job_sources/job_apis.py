"""Job-search APIs: structured vacancies from providers that permit programmatic access.

Each adapter builds its requests, calls the API through the polite fetcher (timeouts, robots.txt for the
keyless ones), normalises results into the common candidate shape and reports one coverage row. A provider
failure never stops discovery; a provider without its key reports "not configured".

Keyless (free public JSON APIs):
- Himalayas: remote jobs with explicit ``locationRestrictions``, publication and expiry timestamps. robots.txt
  disallows ``&page=`` URLs, so only page 1 of each query is read.
- AI Dev Jobs (aidevboard.com): AI/ML and backend roles, ``location=India`` filter, publication and expiry dates,
  the employer's own apply link.
- Artificial Intelligence Jobs (artificialintelligencejobs.co): AI-company roles read from the companies' own
  career pages; ``region=Asia-Pacific`` plus free text. Attribution requested: the listing links back to them.
- RemoteOK: one call per run (whole feed), filtered locally by role. Their API terms require linking back to the
  Remote OK listing and naming them as the source, so the stored URL is the Remote OK page.

Keyed (free keys, no card; add them in Settings → API keys):
- Jooble (``JOOBLE_API_KEY``): aggregator that indexes many Indian portals and company sites. POST API.
- Findwork (``FINDWORK_API_KEY``): developer job board, ``Authorization: Token`` header.

LinkedIn, Naukri, Indeed and similar portals forbid fetching their pages; Jooble's index is the compliant
route to listings that those portals also carry. Remotive was evaluated and left out: its robots.txt
disallows ``/api/*``. Only role titles and a location are sent to these
providers, never resume content.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import urlencode

from app.services.freshness import parse_date
from app.services.job_sources.models import SourceState
from app.services.job_sources.structured import clean_text

# Keyed REST APIs whose robots.txt addresses crawlers, not API clients holding a key under the API terms.
KEYED_API_HOSTS = {"jooble.org", "findwork.dev"}


@dataclass(frozen=True)
class JobAPI:
    source_id: str
    name: str
    env: tuple[str, ...] = ()
    max_queries: int = 4

    def configured(self) -> bool:
        return all(os.getenv(name, "").strip() for name in self.env)


HIMALAYAS = JobAPI("api:himalayas", "Himalayas remote-jobs API", (), 4)
AIDEVBOARD = JobAPI("api:aidevboard", "AI Dev Jobs API", (), 3)
AIJOBS = JobAPI("api:aijobs", "Artificial Intelligence Jobs API", (), 2)
REMOTEOK = JobAPI("api:remoteok", "Remote OK API", (), 1)
JOOBLE = JobAPI("api:jooble", "Jooble API", ("JOOBLE_API_KEY",), 4)
FINDWORK = JobAPI("api:findwork", "Findwork API", ("FINDWORK_API_KEY",), 3)
APIS = [HIMALAYAS, JOOBLE, AIDEVBOARD, AIJOBS, FINDWORK, REMOTEOK]
BY_ID = {api.source_id: api for api in APIS}
FEED_APIS = {REMOTEOK.source_id}  # one whole-feed call per run, filtered locally

WORLDWIDE = re.compile(r"^\s*(worldwide|anywhere|global|remote|anywhere in the world)\s*$", re.I)


def _text(value: Any, limit: int = 8000) -> str:
    return clean_text(re.sub(r"<[^>]+>", " ", str(value or "")), limit)


def _https(url: Any) -> str:
    text = str(url or "").strip()
    return text if text.startswith("https://") else ""


def _day(value: Any) -> str | None:
    found = parse_date(str(value or "")[:10]) if value else None
    return found.isoformat() if found else None


def _restriction_label(restrictions: list[str]) -> str:
    """Short location text; the full list stays in location_restrictions."""
    if not restrictions:
        return "Worldwide"
    india = next((r for r in restrictions if r.casefold() == "india"), None)
    if india and len(restrictions) > 1:
        return f"India (+{len(restrictions) - 1} other countries)"
    return ", ".join(restrictions[:4]) + (f" (+{len(restrictions) - 4} more)" if len(restrictions) > 4 else "")


def _restrictions(text: str) -> list[str]:
    """'Worldwide' -> [] (no restriction); 'USA, Canada' -> ['USA', 'Canada']."""
    if not text or WORLDWIDE.match(text):
        return []
    return [part.strip() for part in re.split(r"[,;/|]", text) if part.strip() and not WORLDWIDE.match(part)]


def _role_words(roles: list[str]) -> set[str]:
    stop = {"and", "or", "the", "a", "an", "of", "for", "in", "with", "junior", "senior", "fresher", "entry", "level",
            "graduate", "intern", "remote", "india", "engineer", "developer"}
    words = {w for role in roles for w in re.findall(r"[a-z0-9+#.]+", str(role).casefold()) if len(w) > 1 and w not in stop}
    return words or {"engineer", "developer"}


def _matches_roles(item: dict[str, Any], words: set[str]) -> bool:
    haystack = " ".join([item.get("title") or "", " ".join(item.get("skills") or [])]).casefold()
    return any(re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", haystack) for word in words)


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


def parse_aidevboard(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for job in (payload or {}).get("jobs") or []:
        url, title = _https(job.get("url")), clean_text(job.get("title"), 200)
        if not url or not title or str(job.get("status") or "active") != "active":
            continue
        workplace = str(job.get("workplace") or "").casefold()
        expiry = _day(job.get("expires_at"))
        items.append({
            "title": title, "url": url, "employer": clean_text(job.get("company_name"), 120),
            "location": clean_text(job.get("location"), 120), "remote": workplace or None,
            "posted_date": _day(job.get("published_at")), "date_source": "job platform API",
            "valid_through": expiry, "employment_type": job.get("job_type"),
            "experience": job.get("experience_level"), "skills": [str(t) for t in job.get("tags") or []][:20],
            "description": _text(job.get("description"), 6000), "extraction_method": "AI Dev Jobs API",
            "application_url": _https(job.get("apply_url")) or None, "api_id": AIDEVBOARD.source_id,
        })
    return items


def parse_aijobs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for job in (payload or {}).get("jobs") or []:
        url, title = _https(job.get("url")), clean_text(job.get("title"), 200)
        if not url or not title:
            continue
        items.append({
            "title": title, "url": url, "employer": clean_text(job.get("company"), 120),
            "location": clean_text(job.get("location"), 120), "remote": "remote" if job.get("remote") else None,
            "posted_date": _day(job.get("posted")), "date_source": "job platform API",
            "experience": job.get("level"), "salary": job.get("salary") or None,
            "description": clean_text(f"{job.get('category') or ''} role at {job.get('company') or ''}", 300),
            "extraction_method": "Artificial Intelligence Jobs API",
            "application_url": _https(job.get("apply_url")) or None, "api_id": AIJOBS.source_id,
        })
    return items


def parse_remoteok(payload: Any) -> list[dict[str, Any]]:
    items = []
    for job in payload if isinstance(payload, list) else []:
        if not isinstance(job, dict) or "legal" in job:
            continue
        url, title = _https(job.get("url")), clean_text(job.get("position"), 200)
        if not url or not title:
            continue
        place = clean_text(job.get("location"), 200)
        restrictions = _restrictions(place) if place else None  # empty location = not stated, not "worldwide"
        items.append({
            "title": title, "url": url, "employer": clean_text(job.get("company"), 120),
            "location": "Remote — " + (_restriction_label(restrictions) if restrictions is not None else "location not stated"),
            "remote": "remote", "location_restrictions": restrictions, "posted_date": _day(job.get("date")),
            "date_source": "job platform API", "skills": [str(t) for t in job.get("tags") or []][:20],
            "salary": (f"{int(job['salary_min'])}–{int(job['salary_max'])} USD" if job.get("salary_min") and job.get("salary_max")
                       else None),
            "description": _text(job.get("description"), 6000), "extraction_method": "Remote OK public API",
            "source_platform": "Remote OK", "api_id": REMOTEOK.source_id,
        })
    return items


def parse_jooble(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for job in (payload or {}).get("jobs") or []:
        url, title = _https(job.get("link")), clean_text(job.get("title"), 200)
        if not url or not title:
            continue
        items.append({
            "title": title, "url": url, "employer": clean_text(job.get("company"), 120) or None,
            "location": clean_text(job.get("location"), 120), "posted_date": _day(job.get("updated")),
            "date_source": "aggregator API (last updated)", "employment_type": job.get("type") or None,
            "salary": clean_text(job.get("salary"), 80) or None, "description": _text(job.get("snippet"), 4000),
            "source_platform": clean_text(job.get("source"), 80) or None,
            "extraction_method": "Jooble API", "api_id": JOOBLE.source_id,
        })
    return items


def parse_findwork(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for job in (payload or {}).get("results") or []:
        url, title = _https(job.get("url")), clean_text(job.get("role"), 200)
        if not url or not title:
            continue
        items.append({
            "title": title, "url": url, "employer": clean_text(job.get("company_name"), 120),
            "location": clean_text(job.get("location"), 120) or ("Remote" if job.get("remote") else ""),
            "remote": "remote" if job.get("remote") else None, "posted_date": _day(job.get("date_posted")),
            "date_source": "job platform API", "employment_type": job.get("employment_type"),
            "skills": [str(t) for t in job.get("keywords") or []][:20], "description": _text(job.get("text"), 6000),
            "source_platform": clean_text(job.get("source"), 80) or None,
            "extraction_method": "Findwork API", "api_id": FINDWORK.source_id,
        })
    return items


PARSERS = {HIMALAYAS.source_id: parse_himalayas, AIDEVBOARD.source_id: parse_aidevboard, AIJOBS.source_id: parse_aijobs,
           REMOTEOK.source_id: parse_remoteok, JOOBLE.source_id: parse_jooble,
           FINDWORK.source_id: parse_findwork}


# ------------------------------------------------------------------ request builders
def himalayas_url(query: str) -> str:
    return "https://himalayas.app/jobs/api/search?" + urlencode({"q": query, "country": "India", "sort": "recent"})


def build_request(api: JobAPI, role: str, where: str) -> dict[str, Any]:
    """One API call: {url, kwargs for http.get}. Keys travel in a header or the request path, never in logs."""
    place = where or "India"
    if api is HIMALAYAS:
        return {"url": himalayas_url(role), "kwargs": {}}
    if api is AIDEVBOARD:
        return {"url": "https://aidevboard.com/api/v1/jobs?" + urlencode({"q": role, "location": place}), "kwargs": {}}
    if api is AIJOBS:
        return {"url": "https://artificialintelligencejobs.co/api/jobs?" + urlencode(
            {"q": role, "region": "Asia-Pacific", "limit": 200}), "kwargs": {}}
    if api is REMOTEOK:
        return {"url": "https://remoteok.com/api", "kwargs": {}}
    if api is JOOBLE:
        return {"url": "https://jooble.org/api/" + os.getenv("JOOBLE_API_KEY", "").strip(),
                "kwargs": {"json_body": {"keywords": role, "location": place, "page": "1"},
                           "robots": False, "use_cache": False}}
    if api is FINDWORK:
        return {"url": "https://findwork.dev/api/jobs/?" + urlencode({"search": role, "location": place, "sort_by": "date"}),
                "kwargs": {"headers": {"Authorization": "Token " + os.getenv("FINDWORK_API_KEY", "").strip()},
                           "robots": False, "use_cache": False}}
    raise ValueError(api.source_id)


async def read_job_apis(http, roles: list[str], *, location: str = "India", skip: dict[str, str] | None = None,
                        apis: list[JobAPI] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Query every configured job API. Returns (items, reports); each report is one coverage row per API."""
    from app.secrets_store import redact

    items: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    where = "" if re.fullmatch(r"(india\s*)+", (location or "").casefold().strip()) else location
    roles = [r for r in roles if r]
    words = _role_words(roles)
    for api in apis or APIS:
        if api.source_id in (skip or {}):
            reports.append({"api": api, "state": SourceState.NOT_TARGETED, "reason": (skip or {})[api.source_id],
                            "count": 0, "queries": 0})
            continue
        if not api.configured():
            reports.append({"api": api, "state": "not_configured", "count": 0, "queries": 0,
                            "reason": "Add the key in Settings → API keys (optional)"})
            continue
        feed = api.source_id in FEED_APIS
        found, errors, statuses, queries = [], [], [], 0
        seen: set[str] = set()
        for role in (["(feed)"] if feed else roles[: api.max_queries]):
            queries += 1
            request = build_request(api, role, where)
            kwargs = {"accept_json": True, **request["kwargs"]}
            result = await http.get(request["url"], **kwargs)
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
            for item in PARSERS[api.source_id](payload):
                if item["url"] in seen or (feed and not _matches_roles(item, words)):
                    continue
                seen.add(item["url"])
                item["_via"] = api.name
                item["_query"] = role if not feed else ", ".join(roles[:3])
                found.append(item)
        if found:
            state = SourceState.PARTIAL if errors else SourceState.EXTRACT_OK
        elif errors:
            state = SourceState.RATE_LIMITED if any("Rate" in e for e in errors) else \
                SourceState.AUTH_REQUIRED if any("401" in e or "403" in e for e in errors) else SourceState.UNAVAILABLE
        else:
            state = SourceState.NO_RESULTS
        items.extend(found)
        reports.append({"api": api, "state": state, "count": len(found), "queries": queries,
                        "reason": redact("; ".join(dict.fromkeys(errors))[:200]) or None,
                        "http_status": next((s for s in statuses if s), None)})
    return items, reports

