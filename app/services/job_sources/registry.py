"""Source registry: every acquisition source, what it can do, and how it has behaved.

A *source definition* is static (id, category, method, capabilities, pagination, geography,
access restrictions, rate limit). Its *state* is persisted in ``source_state`` (enabled flag,
attempt/success/result times, counts, extraction and verification rates, consecutive failures,
backoff). Run-level ``SourceReport`` rows (see ``coverage.py``) are folded into this state after
every discovery run by ``record_run``.

Sources are never reported as working because they are listed here: a source's state only changes
when an adapter actually ran and returned (or failed to return) records.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from app.services.job_sources import ats_registry, portals
from app.services.job_sources.models import SourceState


@dataclass(frozen=True)
class SourceDefinition:
    id: str
    name: str
    category: str  # search_engine | ats_board | career_page | job_portal | employer_discovery | government | feed | renderer
    method: str
    capabilities: tuple[str, ...]
    pagination: str  # "none" | "all-in-one" | "offset" | "provider-limited" | "n/a"
    geography: str
    access: str  # human-readable restriction
    rate_limit: str
    alternative: str = ""  # legitimate alternative when access is restricted
    default_enabled: bool = True
    policy: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


FEED_COVERED = {"Hasjob"}


def _portal_defs() -> list[SourceDefinition]:
    output = []
    for portal in portals.PORTALS:
        if portal.name in FEED_COVERED:
            continue  # read through its public feed (feed:*), not registered twice
        sid = "portal:" + re.sub(r"[^a-z0-9]+", "-", portal.name.casefold()).strip("-")
        search_only = portal.policy == portals.SEARCH_ONLY
        output.append(SourceDefinition(
            sid, portal.name, "job_portal",
            "search-engine results only" if search_only else "search-engine results + public pages via search provider",
            ("search",) if search_only else ("search", "index-page expansion", "detail fetch via provider"),
            "provider-limited", portal.region, portal.reason, "search provider quota",
            alternative=("Open the original listing; the same vacancy is matched on the employer's own page "
                         "when it can be found there.") if search_only else "",
            policy=portal.policy))
    return output


def _ats_defs() -> list[SourceDefinition]:
    output = []
    for provider in ats_registry.PROVIDERS:
        pagination = {"lever": "offset", "smartrecruiters": "offset"}.get(provider.key, "all-in-one")
        output.append(SourceDefinition(
            f"ats:{provider.key}", provider.name, "ats_board", provider.interface,
            ("enumerate", "detail", "posting date", "status") if provider.readable else ("career page read",),
            pagination if provider.readable else "n/a", "Global (per employer board)",
            "Public, unauthenticated job board" if provider.readable else
            "No documented public API; read as a rendered career page",
            "1 request per board page; 4 boards in parallel" if provider.readable else "browser: 1 page at a time"))
    return output


STATIC_DEFS: list[SourceDefinition] = [
    SourceDefinition("search:portal", "Portal site searches", "search_engine", "Parallel MCP web_search (site:)",
                     ("search",), "provider-limited", "India first", "Search-provider quota (free tier rate limits)",
                     "provider rate limit"),
    SourceDefinition("search:ats", "ATS host searches", "search_engine", "Parallel MCP web_search (site: ATS hosts)",
                     ("search", "board discovery"), "provider-limited", "Global", "Search-provider quota", "provider rate limit"),
    SourceDefinition("search:career", "Company career-page searches", "search_engine", "Parallel MCP web_search",
                     ("search",), "provider-limited", "India first", "Search-provider quota", "provider rate limit"),
    SourceDefinition("search:web", "Open web searches", "search_engine", "Parallel MCP web_search",
                     ("search",), "provider-limited", "India first", "Search-provider quota", "provider rate limit"),
    SourceDefinition("search:city", "City searches", "search_engine", "Parallel MCP web_search",
                     ("search",), "provider-limited", "Indian tech hubs", "Search-provider quota", "provider rate limit"),
    SourceDefinition("search:remote", "Remote-from-India searches", "search_engine", "Parallel MCP web_search",
                     ("search",), "provider-limited", "Remote (India-eligible)", "Search-provider quota", "provider rate limit"),
    SourceDefinition("search:startup", "Startup job searches", "search_engine", "Parallel MCP web_search",
                     ("search",), "provider-limited", "Indian startups", "Search-provider quota", "provider rate limit"),
    SourceDefinition("search:company", "Named-company searches", "search_engine", "Parallel MCP web_search",
                     ("search",), "provider-limited", "Any", "Search-provider quota", "provider rate limit"),
    SourceDefinition("search:index", "Index-page expansion", "search_engine", "Parallel MCP web_fetch of listing indexes",
                     ("index-page expansion",), "none", "Any", "Only portals whose policy allows provider fetches",
                     "≤10 pages per run"),
    SourceDefinition("career:discovery", "Career-page discovery", "career_page",
                     "static HTML → browser render → embedded data → sitemaps → common paths → search",
                     ("discover", "enumerate", "JSON-LD"), "none", "Employer websites",
                     "robots.txt respected; bot challenges are reported, never bypassed", "1 request/s per host"),
    SourceDefinition("career:read", "Verified career-page re-reads", "career_page", "static HTML (+ render when needed)",
                     ("enumerate", "JSON-LD"), "none", "Employer websites", "robots.txt respected", "1 request/s per host"),
    SourceDefinition("employers:discovery", "Startup & employer discovery", "employer_discovery",
                     "publications, directories, accelerators, VC portfolios via search", ("discover employers",),
                     "provider-limited", "India", "Search-provider quota", "provider rate limit"),
    SourceDefinition("employers:resolution", "Unknown-employer resolution", "employer_discovery",
                     "name → official domain via search", ("resolve domain",), "provider-limited", "Any",
                     "Search-provider quota", "≤3 searches per run"),
    SourceDefinition("gov:notices", "Government & PSU recruitment (search fallback)", "government",
                     "Parallel search + fetch of official notices, local-model extraction — targeted requests only",
                     ("search", "extract"), "provider-limited", "India",
                     "Fallback for requests that name an organisation; official sources are polled directly (gov:*)",
                     "1 search per request"),
    SourceDefinition("gov:exams", "Examination notifications (search fallback)", "government",
                     "Parallel search + fetch, local-model extraction — targeted requests only", ("search", "extract"),
                     "provider-limited", "India", "Dates must be quoted from the source", "1 search per request"),
    SourceDefinition("news:ai", "AI developments", "news", "Parallel search", ("search",), "provider-limited",
                     "India first", "", "1 search per day", default_enabled=True),
    SourceDefinition("feed:hasjob", "Hasjob public feed", "feed", "public Atom feed", ("enumerate",), "all-in-one",
                     "India", "Public feed; robots.txt respected", "1 request per run"),
    SourceDefinition("api:himalayas", "Himalayas remote-jobs API", "job_api",
                     "public JSON API (country=India), page 1 per query (robots.txt disallows paging)",
                     ("search", "location restrictions", "posting date", "expiry date"), "none",
                     "Remote jobs; explicit country restrictions", "Free, no key; credit Himalayas when shown",
                     "≤4 queries per run"),
    SourceDefinition("api:jooble", "Jooble API", "job_api",
                     "official REST API (POST) — job search engine indexing Indian portals and company sites",
                     ("search", "last-updated date"), "provider-limited", "India",
                     "Optional free key — add it in Settings → API keys", "≤4 calls per run",
                     alternative="Without a key the source is reported as not configured."),
    SourceDefinition("api:findwork", "Findwork API", "job_api", "official REST API /api/jobs (token header)",
                     ("search", "posting date"), "provider-limited", "Global; remote and on-site",
                     "Optional free key — add it in Settings → API keys", "≤3 calls per run",
                     alternative="Without a key the source is reported as not configured."),
    SourceDefinition("api:aidevboard", "AI Dev Jobs API", "job_api", "public JSON API /api/v1/jobs (location=India)",
                     ("search", "posting date", "expiry date", "employer apply link"), "none", "India + remote",
                     "Free, no key", "≤3 queries per run"),
    SourceDefinition("api:aijobs", "Artificial Intelligence Jobs API", "job_api",
                     "public JSON API /api/jobs (region=Asia-Pacific), read from AI companies' career pages",
                     ("search", "posting date", "employer apply link"), "none", "Asia-Pacific",
                     "Free, no key; attribution requested (listings link back)", "≤2 queries per run"),
    SourceDefinition("api:remoteok", "Remote OK API", "job_api", "public JSON feed, filtered locally",
                     ("enumerate", "posting date"), "none", "Remote",
                     "Free, no key; terms require linking back to Remote OK (listings keep their Remote OK URL)",
                     "1 call per run"),
    SourceDefinition("renderer:browser", "Headless browser (Chrome)", "renderer", "Playwright, system Chrome",
                     ("render",), "n/a", "n/a", "Used only when static HTML is insufficient", "1 page at a time"),
    SourceDefinition("extractor:firecrawl", "Firecrawl (optional)", "renderer", "Firecrawl API", ("render",), "n/a",
                     "n/a", "Needs a key (Settings → API keys); sends public employer URLs only", "per API plan", default_enabled=False),
]


_GOV_METHOD = {"direct": "listing page polled directly (ETag / content hash); new notifications read as HTML or PDF",
               "render": "listing page rendered in the local headless browser (JavaScript site), Discover runs only",
               "provider": "listing page read through the search provider (server sends a broken TLS chain), Discover runs only",
               "search": "search-engine results only (the site blocks direct access), Discover runs only",
               "unavailable": "not fetched"}


def _gov_defs() -> list[SourceDefinition]:
    """One registry entry per catalogue source (app.services.gov_sources), so state and coverage are per source."""
    from app.services import gov_sources
    output = []
    for source in gov_sources.SOURCES:
        signal = source.category in {"news", "aggregator"}
        output.append(SourceDefinition(
            source.registry_id, source.name, "government", _GOV_METHOD[source.access],
            ("signals",) if signal else ("enumerate", "detail", "PDF text", "eligibility clauses"),
            "none", "India", source.note or ("Discovery signal only — never stored as the organization or the application record"
                                             if signal else "Official source; robots.txt respected"),
            f"every {source.cadence_hours} h, 1 request/s per host",
            alternative="Open the official site; a targeted search request can still find its notices."
            if source.access in {"unavailable", "search"} else "",
            default_enabled=source.enabled and source.access != "unavailable"))
    return output


def definitions() -> list[SourceDefinition]:
    return STATIC_DEFS + _ats_defs() + _portal_defs() + _gov_defs()


BY_ID = {d.id: d for d in definitions()}
SEARCH_GROUPS = {"portal", "ats", "career", "web", "city", "remote", "startup", "company"}


def source_id_for(report: dict[str, Any]) -> str | None:
    """Map a run-level SourceReport (category/name/method) onto a registry source id."""
    category, name, method = report.get("category"), str(report.get("name") or ""), str(report.get("method") or "")
    if category == "ats_board":
        provider = method.split(" ")[0].casefold()
        return f"ats:{provider}" if f"ats:{provider}" in BY_ID else None
    if method == "job API":
        sid = str(report.get("domain") or "")
        return sid if sid in BY_ID else None
    if method == "public feed":
        sid = "feed:" + re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
        return sid if sid in BY_ID else None
    if category == "job_portal":
        portal = next((p for p in portals.PORTALS if p.name.casefold() == name.casefold()
                       or name.casefold() in {d.split(".")[0] for d in p.domains}), None)
        if portal is None:
            portal = portals.portal_for(str(report.get("domain") or ""))
        return "portal:" + re.sub(r"[^a-z0-9]+", "-", portal.name.casefold()).strip("-") if portal else None
    if category == "career_page":
        return "career:read" if "read" in method else "career:discovery"
    if category == "employer_discovery":
        return "employers:resolution" if "resolution" in method else "employers:discovery"
    if category == "search_engine":
        if "index page" in method:
            return "search:index"
        lowered = name.casefold()
        for key, sid in (("ats board", "search:ats"), ("career page", "search:career"), ("open web", "search:web"),
                         ("city", "search:city"), ("remote", "search:remote"), ("startup", "search:startup"),
                         ("company careers", "search:company"), ("site search", "search:portal")):
            if key in lowered:
                return sid
        return "search:portal" if "+" in name else "search:web"
    if category in {"government", "news", "feed"}:
        return report.get("source_id")
    return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def backoff_until(consecutive_failures: int, *, now: datetime | None = None) -> str | None:
    """Exponential backoff after repeated failures: 3 → 6 h, 4 → 12 h, 5 → 24 h, … capped at 7 days."""
    if consecutive_failures < 3:
        return None
    hours = min(6 * 2 ** (consecutive_failures - 3), 24 * 7)
    return ((now or _now()) + timedelta(hours=hours)).isoformat()


@dataclass
class RunStats:
    attempted: bool = False
    success: bool = False
    partial: bool = False
    blocked: bool = False
    results: int = 0
    listings: int = 0
    unique: int = 0
    extraction_ok: int = 0
    extraction_total: int = 0
    rejected: int = 0
    stored: int = 0
    verified: int = 0
    policy_limited: bool = False
    failures: list[str] = field(default_factory=list)
    states: set[str] = field(default_factory=set)


def aggregate(reports: Iterable[dict[str, Any]]) -> dict[str, RunStats]:
    stats: dict[str, RunStats] = {}
    for report in reports:
        sid = source_id_for(report)
        if not sid:
            continue
        entry = stats.setdefault(sid, RunStats())
        state = report.get("state")
        entry.states.add(state)
        if state in {SourceState.NOT_TARGETED, SourceState.TARGETED}:
            continue
        entry.attempted = True
        if state in SourceState.SUCCESS:
            entry.success = entry.success or state != SourceState.PARTIAL
            entry.partial = entry.partial or state == SourceState.PARTIAL
        policy = state in {SourceState.POLICY_SKIPPED, SourceState.ROBOTS_DISALLOWED} or \
            "(policy)" in str(report.get("method") or "") or "search results only" in str(report.get("method") or "")
        entry.policy_limited = entry.policy_limited or policy
        if state in SourceState.BLOCKED and state != SourceState.POLICY_SKIPPED:
            entry.blocked = True
        if state not in SourceState.SUCCESS | {SourceState.NO_RESULTS, SourceState.POLICY_SKIPPED}:
            if report.get("failure_reason"):
                entry.failures.append(str(report["failure_reason"])[:200])
        entry.results += int(report.get("search_results") or 0)
        entry.listings += int(report.get("listings") or 0)
        entry.unique += int(report.get("unique") or 0)
        entry.rejected += int(report.get("rejected") or 0)
        entry.stored += int(report.get("stored") or 0)
        entry.verified += int(report.get("verified") or 0)
        if state not in {SourceState.POLICY_SKIPPED, SourceState.ROBOTS_DISALLOWED}:
            entry.extraction_total += 1
            entry.extraction_ok += int(state in SourceState.SUCCESS or state == SourceState.NO_RESULTS)
    return stats


def run_state(stats: RunStats) -> str:
    """One clear state per source for a run.

    "successful" requires usable records: individual vacancies (listings) or unique candidates from this source.
    An answer with results that yielded no usable vacancy is "no_usable_results"; a portal limited to
    search-engine results by its terms is "search_only", whatever it returned.
    """
    if not stats.attempted:
        return "not_attempted"
    usable = bool(stats.listings or stats.unique)
    if stats.policy_limited and not stats.failures:
        return "search_only"
    if (stats.success or stats.partial) and not usable:
        return "no_usable_results" if stats.results else ("partial" if stats.failures else "no_results")
    if stats.success and not stats.failures:
        return "successful"
    if stats.success or stats.partial:
        return "partial"
    if stats.blocked:
        return "access_restricted"
    if stats.failures:
        return "failed"
    if not (stats.results or stats.listings or stats.unique):
        return "no_results"  # searched and answered, but returned nothing — not counted as a success
    return "successful" if usable else "no_usable_results"


RUN_STATE_LABEL = {"standby": "Standby · used only when needed", "no_usable_results": "Answered · no usable vacancies",
                   "search_only": "Search-engine results only (terms forbid fetching)",
                   "no_results": "Searched · no results", "successful": "Successful", "partial": "Partial", "failed": "Failed",
                   "access_restricted": "Access restricted", "not_configured": "Not configured",
                   "not_attempted": "Not attempted", "disabled": "Disabled", "backing_off": "Backing off"}
