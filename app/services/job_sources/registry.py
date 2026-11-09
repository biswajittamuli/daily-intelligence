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


def _portal_defs() -> list[SourceDefinition]:
    output = []
    for portal in portals.PORTALS:
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
    SourceDefinition("gov:notices", "Government & PSU recruitment", "government",
                     "Parallel search + fetch of official notices, local-model extraction", ("search", "extract"),
                     "provider-limited", "India", "Official sites often serve PDFs; dates are evidence-checked",
                     "1 search per run"),
    SourceDefinition("gov:exams", "Examination notifications", "government",
                     "Parallel search + fetch, local-model extraction", ("search", "extract"), "provider-limited",
                     "India", "Dates must be quoted from the source", "1 search per run"),
    SourceDefinition("news:ai", "AI developments", "news", "Parallel search", ("search",), "provider-limited",
                     "India first", "", "1 search per day", default_enabled=True),
    SourceDefinition("feed:hasjob", "Hasjob public feed", "feed", "public Atom feed", ("enumerate",), "all-in-one",
                     "India", "Public feed; robots.txt respected", "1 request per run"),
    SourceDefinition("renderer:browser", "Headless browser (Chrome)", "renderer", "Playwright, system Chrome",
                     ("render",), "n/a", "n/a", "Used only when static HTML is insufficient", "1 page at a time"),
    SourceDefinition("extractor:firecrawl", "Firecrawl (optional)", "renderer", "Firecrawl API", ("render",), "n/a",
                     "n/a", "Needs FIRECRAWL_API_KEY; public employer URLs only", "per API plan", default_enabled=False),
]


def definitions() -> list[SourceDefinition]:
    return STATIC_DEFS + _ats_defs() + _portal_defs()


BY_ID = {d.id: d for d in definitions()}
SEARCH_GROUPS = {"portal", "ats", "career", "web", "city", "remote", "startup", "company"}


def source_id_for(report: dict[str, Any]) -> str | None:
    """Map a run-level SourceReport (category/name/method) onto a registry source id."""
    category, name, method = report.get("category"), str(report.get("name") or ""), str(report.get("method") or "")
    if category == "ats_board":
        provider = method.split(" ")[0].casefold()
        return f"ats:{provider}" if f"ats:{provider}" in BY_ID else None
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
        if state in SourceState.BLOCKED:
            entry.blocked = True
        if state not in SourceState.SUCCESS | {SourceState.NO_RESULTS}:
            if report.get("failure_reason"):
                entry.failures.append(str(report["failure_reason"])[:200])
        entry.results += int(report.get("search_results") or 0)
        entry.listings += int(report.get("listings") or 0)
        entry.unique += int(report.get("unique") or 0)
        if state not in {SourceState.POLICY_SKIPPED, SourceState.ROBOTS_DISALLOWED}:
            entry.extraction_total += 1
            entry.extraction_ok += int(state in SourceState.SUCCESS or state == SourceState.NO_RESULTS)
    return stats


def run_state(stats: RunStats) -> str:
    """One clear state per source for a run: successful / partial / failed / access restricted / not attempted."""
    if not stats.attempted:
        return "not_attempted"
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
    return "successful"


RUN_STATE_LABEL = {"no_results": "Searched · no results", "successful": "Successful", "partial": "Partial", "failed": "Failed",
                   "access_restricted": "Access restricted", "not_configured": "Not configured",
                   "not_attempted": "Not attempted", "disabled": "Disabled", "backing_off": "Backing off"}
