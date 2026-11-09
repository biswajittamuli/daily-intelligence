"""Extensible registry of applicant-tracking systems (ATS).

Each provider declares how to recognise it in a URL or page and whether it offers a documented,
public, unauthenticated job-board interface. Readable providers are read through that interface
(``app.services.ats_sources``); the others are *identified* and their public career pages are read
like any other career page (static HTML, JSON-LD, then browser rendering) — no undocumented private
endpoints are called directly.

Add a provider by appending an ``ATSProvider`` to ``PROVIDERS``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlsplit

RESERVED_SLUGS = {"embed", "api", "v1", "v0", "jobs", "j", "o", "job", "careers", "search", "static", "assets",
                  "www", "app", "login", "signin", "apply", "en", "en-us", "en-in", "home", "boards", "job-boards"}


@dataclass(frozen=True)
class ATSProvider:
    key: str
    name: str
    patterns: tuple[re.Pattern[str], ...]
    readable: bool  # has a documented public job-board API implemented in ats_sources
    board_url: str  # human-facing board URL template ({slug})
    interface: str  # what is used to read it
    listing_pattern: re.Pattern[str] | None = None  # URL shape of one vacancy

    def match(self, url: str) -> str | None:
        for pattern in self.patterns:
            found = pattern.search(url)
            if found:
                slug = found.group(1)
                if slug and slug.casefold() not in RESERVED_SLUGS and len(slug) <= 80:
                    return slug
        return None


def _p(*patterns: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(p, re.I) for p in patterns)


PROVIDERS: list[ATSProvider] = [
    ATSProvider("greenhouse", "Greenhouse", _p(
        r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/embed/job_board(?:/js)?\?for=([A-Za-z0-9_-]+)",
        r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/([A-Za-z0-9_-]+)",
        r"boards-api\.greenhouse\.io/v1/boards/([A-Za-z0-9_-]+)"),
        True, "https://job-boards.greenhouse.io/{slug}", "Greenhouse Job Board API (public)",
        re.compile(r"greenhouse\.io/[^/]+/jobs/\d+|[?&]gh_jid=\d+", re.I)),
    ATSProvider("lever", "Lever", _p(r"jobs\.(?:eu\.)?lever\.co/([A-Za-z0-9_.-]+)", r"api\.lever\.co/v0/postings/([A-Za-z0-9_.-]+)"),
                True, "https://jobs.lever.co/{slug}", "Lever Postings API (public)",
                re.compile(r"jobs\.(?:eu\.)?lever\.co/[^/]+/[0-9a-f-]{8,}", re.I)),
    ATSProvider("ashby", "Ashby", _p(r"jobs\.ashbyhq\.com/([A-Za-z0-9_.%-]+)", r"api\.ashbyhq\.com/posting-api/job-board/([A-Za-z0-9_.-]+)"),
                True, "https://jobs.ashbyhq.com/{slug}", "Ashby Job Posting API (public)",
                re.compile(r"jobs\.ashbyhq\.com/[^/]+/[0-9a-f-]{8,}", re.I)),
    ATSProvider("workable", "Workable", _p(r"apply\.workable\.com/(?!api\b|j/)([A-Za-z0-9_-]+)", r"([a-z0-9-]+)\.workable\.com"),
                True, "https://apply.workable.com/{slug}", "Workable public widget API",
                re.compile(r"apply\.workable\.com/[^/]+/j/[0-9A-F]+", re.I)),
    ATSProvider("smartrecruiters", "SmartRecruiters", _p(r"(?:careers|jobs)\.smartrecruiters\.com/([A-Za-z0-9_-]+)"),
                True, "https://careers.smartrecruiters.com/{slug}", "SmartRecruiters Posting API (public)",
                re.compile(r"jobs\.smartrecruiters\.com/[^/]+/\d{6,}", re.I)),
    ATSProvider("recruitee", "Recruitee", _p(r"([a-z0-9-]+)\.recruitee\.com"), True, "https://{slug}.recruitee.com",
                "Recruitee Careers Site API (public)", re.compile(r"\.recruitee\.com/o/[a-z0-9-]+", re.I)),
    # Identified only: their public career pages are read as career pages (static, JSON-LD, then browser).
    ATSProvider("workday", "Workday", _p(r"([a-z0-9-]+)\.wd\d+\.myworkdayjobs\.com", r"([a-z0-9-]+)\.myworkdayjobs\.com"),
                False, "", "career page (browser-rendered)", re.compile(r"myworkdayjobs\.com/.+/job/", re.I)),
    ATSProvider("freshteam", "Freshteam", _p(r"([a-z0-9-]+)\.freshteam\.com"), False, "https://{slug}.freshteam.com/jobs",
                "career page", re.compile(r"freshteam\.com/jobs/[A-Za-z0-9_-]+", re.I)),
    ATSProvider("zoho_recruit", "Zoho Recruit", _p(r"([a-z0-9-]+)\.zohorecruit\.(?:com|in|eu)"), False,
                "https://{slug}.zohorecruit.in/jobs/Careers", "career page", re.compile(r"zohorecruit\.[a-z]+/jobs/[^/]+/\d+", re.I)),
    ATSProvider("keka", "Keka", _p(r"([a-z0-9-]+)\.keka\.com/careers"), False, "https://{slug}.keka.com/careers",
                "career page (browser-rendered)", re.compile(r"keka\.com/careers/jobdetails/\d+", re.I)),
    ATSProvider("darwinbox", "Darwinbox", _p(r"([a-z0-9-]+)\.darwinbox\.(?:in|com)"), False, "", "career page (browser-rendered)",
                re.compile(r"darwinbox\.[a-z]+/ms/candidate/.+/careers/", re.I)),
    ATSProvider("icims", "iCIMS", _p(r"(?:careers-|jobs-)?([a-z0-9]+)\.icims\.com"), False, "", "career page",
                re.compile(r"icims\.com/jobs/\d+", re.I)),
    ATSProvider("oracle", "Oracle Recruiting Cloud", _p(r"([a-z0-9-]+)\.fa\.[a-z0-9]+\.oraclecloud\.com"), False, "",
                "career page (browser-rendered)", re.compile(r"oraclecloud\.com/hcmUI/CandidateExperience/.+/job/\d+", re.I)),
    ATSProvider("successfactors", "SAP SuccessFactors", _p(r"career(?:\d+)?\.successfactors\.(?:com|eu)/.*?company=([A-Za-z0-9_-]+)",
                                                           r"jobs\.sap\.com"), False, "", "career page"),
    ATSProvider("taleo", "Taleo", _p(r"([a-z0-9-]+)\.taleo\.net"), False, "", "career page"),
    ATSProvider("bamboohr", "BambooHR", _p(r"([a-z0-9-]+)\.bamboohr\.com/(?:careers|jobs)"), False,
                "https://{slug}.bamboohr.com/careers", "career page"),
    ATSProvider("jobvite", "Jobvite", _p(r"jobs\.jobvite\.com/([A-Za-z0-9_-]+)"), False, "https://jobs.jobvite.com/{slug}", "career page"),
    ATSProvider("jazzhr", "JazzHR", _p(r"([a-z0-9-]+)\.applytojob\.com"), False, "https://{slug}.applytojob.com", "career page"),
    ATSProvider("breezy", "Breezy HR", _p(r"([a-z0-9-]+)\.breezy\.hr"), False, "https://{slug}.breezy.hr", "career page"),
    ATSProvider("teamtailor", "Teamtailor", _p(r"([a-z0-9-]+)\.teamtailor\.com"), False, "https://{slug}.teamtailor.com/jobs",
                "career page"),
    ATSProvider("personio", "Personio", _p(r"([a-z0-9-]+)\.jobs\.personio\.(?:de|com)"), False, "https://{slug}.jobs.personio.com",
                "career page"),
    ATSProvider("turbohire", "TurboHire", _p(r"([a-z0-9-]+)\.turbohire\.co"), False, "", "career page (browser-rendered)"),
    ATSProvider("kula", "Kula", _p(r"careers\.kula\.ai/([A-Za-z0-9_-]+)"), False, "https://careers.kula.ai/{slug}", "career page"),
]
BY_KEY = {provider.key: provider for provider in PROVIDERS}
READABLE = {provider.key for provider in PROVIDERS if provider.readable}

# Search-engine site: targets that surface individual boards (and therefore employers) we did not know.
BOARD_SEARCH_DOMAINS = ["job-boards.greenhouse.io", "boards.greenhouse.io", "jobs.lever.co", "jobs.ashbyhq.com",
                        "apply.workable.com", "jobs.smartrecruiters.com", "myworkdayjobs.com", "recruitee.com",
                        "zohorecruit.in", "keka.com", "freshteam.com", "darwinbox.in"]


def detect_url(url: str) -> tuple[ATSProvider, str] | None:
    """The ATS behind a URL and the board identifier, if the URL belongs to one."""
    host = (urlsplit(url).hostname or "").casefold()
    if not host:
        return None
    for provider in PROVIDERS:
        slug = provider.match(url)
        if slug:
            if provider.key == "workable" and host.endswith("workable.com") and slug in {"apply", "www", "jobs"}:
                continue
            return provider, slug
    return None


def detect_in_text(text: str, *, limit: int = 6) -> list[dict[str, object]]:
    """ATS boards referenced anywhere in a page (anchors, iframes, script src, inline config)."""
    found: dict[str, dict[str, object]] = {}
    for url in re.findall(r"https?://[A-Za-z0-9.-]+(?:/[^\s\"'<>)]*)?", text or "")[:5000]:
        hit = detect_url(url)
        if hit and hit[0].key not in found:
            provider, slug = hit
            found[provider.key] = {"provider": provider.key, "name": provider.name, "slug": slug, "url": url,
                                   "readable": provider.readable}
            if len(found) >= limit:
                break
    return sorted(found.values(), key=lambda item: not item["readable"])


def is_ats_listing(url: str) -> bool:
    return any(p.listing_pattern is not None and p.listing_pattern.search(url) for p in PROVIDERS)


def boards_from_urls(urls: Iterable[str]) -> list[dict[str, str]]:
    """Readable boards (provider, slug) referenced by a set of URLs (e.g. search results)."""
    boards: dict[tuple[str, str], dict[str, str]] = {}
    for url in urls:
        hit = detect_url(str(url))
        if hit and hit[0].readable:
            provider, slug = hit
            boards.setdefault((provider.key, slug.casefold()), {"ats": provider.key, "slug": slug, "url": str(url)})
    return list(boards.values())
