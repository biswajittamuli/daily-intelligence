"""Job-portal access policies (Part 6).

A portal in this list is a *discovery target*, not permission to scrape it. Each entry records
what acquisition is permitted and why:

- ``search_results_only``: the portal's terms prohibit automated access/scraping (or it requires a
  login for listings). The app uses only what a search engine already returns (URL, title, snippet)
  and links out to the original. Pages are never fetched — neither directly nor through the search
  provider's fetch tool.
- ``provider_fetch``: terms not reviewed in-app; individual public pages may be retrieved through the
  search provider's fetch tool (never directly from this machine), within run budgets.
- ``official_api``: an authorised API is configured (none is configured by default).

Reaching a portal is reported only when actual records came back from it.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

SEARCH_ONLY = "search_results_only"
PROVIDER_FETCH = "provider_fetch"
OFFICIAL_API = "official_api"


@dataclass(frozen=True)
class PortalPolicy:
    name: str
    domains: tuple[str, ...]
    policy: str
    official_api: str
    reason: str
    region: str = "India"


PORTALS: list[PortalPolicy] = [
    PortalPolicy("LinkedIn Jobs", ("linkedin.com",), SEARCH_ONLY,
                 "Partner-only Job Posting / Talent APIs; no job-search API for individuals",
                 "User Agreement §8.2 and the prohibited-software policy forbid scraping, crawlers and automated access.",
                 "Global"),
    PortalPolicy("Indeed", ("indeed.com", "in.indeed.com", "indeed.co.in"), SEARCH_ONLY,
                 "Publisher Job Search API closed to new integrations; employer-side APIs only",
                 "Terms of Service prohibit scraping and automated access; automated applications are not permitted.",
                 "Global"),
    PortalPolicy("Glassdoor", ("glassdoor.com", "glassdoor.co.in"), SEARCH_ONLY, "No public job-search API",
                 "Terms of Use prohibit scraping and automated collection.", "Global"),
    PortalPolicy("Naukri", ("naukri.com",), SEARCH_ONLY, "No public job-search API (recruiter APIs only)",
                 "Terms & Conditions prohibit robots, spiders, scrapers and deep-linking automation."),
    PortalPolicy("Wellfound", ("wellfound.com", "angel.co"), SEARCH_ONLY, "No public job-search API",
                 "Terms prohibit scraping; listings sit behind bot protection and login.", "Global"),
    PortalPolicy("YC Work at a Startup", ("workatastartup.com",), SEARCH_ONLY, "No public API",
                 "Job listings require a signed-in account.", "Global"),
    PortalPolicy("YC Jobs", ("ycombinator.com",), PROVIDER_FETCH, "No public API",
                 "Public company job pages; terms not reviewed in-app. Fetched only via the search provider.", "Global"),
    PortalPolicy("foundit", ("foundit.in", "foundit.com", "monsterindia.com"), PROVIDER_FETCH, "No public API",
                 "Terms not reviewed in-app."),
    PortalPolicy("Instahyre", ("instahyre.com",), PROVIDER_FETCH, "No public API", "Terms not reviewed in-app."),
    PortalPolicy("Cutshort", ("cutshort.io",), PROVIDER_FETCH, "No public API", "Terms not reviewed in-app."),
    PortalPolicy("Hirist", ("hirist.tech", "hirist.com"), PROVIDER_FETCH, "No public API", "Terms not reviewed in-app."),
    PortalPolicy("TimesJobs", ("timesjobs.com",), PROVIDER_FETCH, "No public API", "Terms not reviewed in-app."),
    PortalPolicy("Freshersworld", ("freshersworld.com",), PROVIDER_FETCH, "No public API", "Terms not reviewed in-app."),
    PortalPolicy("Internshala", ("internshala.com",), PROVIDER_FETCH, "No public API", "Terms not reviewed in-app."),
    PortalPolicy("Apna", ("apna.co",), PROVIDER_FETCH, "No public API", "Terms not reviewed in-app."),
    PortalPolicy("Shine", ("shine.com",), PROVIDER_FETCH, "No public API", "Terms not reviewed in-app."),
    PortalPolicy("iimjobs", ("iimjobs.com",), PROVIDER_FETCH, "No public API", "Terms not reviewed in-app."),
    PortalPolicy("WorkIndia", ("workindia.in",), PROVIDER_FETCH, "No public API", "Terms not reviewed in-app."),
    PortalPolicy("Hasjob", ("hasjob.co",), PROVIDER_FETCH, "Public Atom feed (hasjob.co/feed)",
                 "Read through its public feed; robots.txt respected."),
    PortalPolicy("startup.jobs", ("startup.jobs",), PROVIDER_FETCH, "No public API", "Terms not reviewed in-app.", "Global"),
    PortalPolicy("Talent.com", ("talent.com",), PROVIDER_FETCH, "No public API", "Terms not reviewed in-app.", "Global"),
]


def portal_for(url_or_domain: str) -> PortalPolicy | None:
    value = str(url_or_domain or "")
    host = (urlsplit(value).hostname if "://" in value else value.split("/")[0]) or ""
    host = host.casefold().removeprefix("www.")
    for portal in PORTALS:
        for domain in portal.domains:
            if host == domain or host.endswith("." + domain):
                return portal
    return None


def may_fetch(url: str, *, via: str = "provider") -> tuple[bool, str | None]:
    """Whether a page may be fetched. Non-portal URLs (employer sites, ATS boards) return True here;
    robots.txt is still checked by the direct fetcher."""
    portal = portal_for(url)
    if portal is None:
        return True, None
    if portal.policy == SEARCH_ONLY:
        return False, f"{portal.name}: search results only — {portal.reason}"
    if portal.policy == PROVIDER_FETCH and via == "direct":
        return False, f"{portal.name}: not fetched directly from this computer (terms not reviewed)"
    return True, None


def policy_table() -> list[dict[str, str]]:
    return [{"name": p.name, "domains": ", ".join(p.domains), "policy": p.policy, "official_api": p.official_api,
             "reason": p.reason, "region": p.region} for p in PORTALS]
