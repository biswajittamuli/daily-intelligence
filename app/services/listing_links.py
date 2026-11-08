"""Deterministic harvesting of individual job-listing links from index pages.

Job boards and company career pages usually return a *list* page (for example
"AI Engineer jobs in India") rather than one vacancy. Those pages contain many
links to individual listings. This module extracts them without a model so a
single fetched index page can yield many concrete, dated listings.

Only links whose URL shape matches a known individual-listing pattern are kept.
Titles come from the link text (or its markdown title attribute) and must look
like a role; nearby text supplies relative dates ("3 days ago"), location and
skills. Nothing is invented: every field is copied from the page text.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any
from urllib.parse import urljoin, urlparse

from app.services.freshness import parse_relative_date
from app.services.resume import find_skills

# Individual listing URL shapes per board / ATS. Index/search pages are excluded.
LISTING_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"wellfound\.com/jobs/\d+", re.I),
    re.compile(r"angel\.co/company/[^/]+/jobs/\d+", re.I),
    re.compile(r"naukri\.com/job-listings-", re.I),
    re.compile(r"foundit\.(?:in|com)/job/[a-z0-9-]+-\d+", re.I),
    re.compile(r"indeed\.[a-z.]+/(?:viewjob|rc/clk|pagead/clk)", re.I),
    re.compile(r"linkedin\.com/jobs/view/", re.I),
    re.compile(r"instahyre\.com/job-\d+", re.I),
    re.compile(r"cutshort\.io/job/", re.I),
    re.compile(r"hirist\.(?:tech|com)/j/", re.I),
    re.compile(r"workatastartup\.com/jobs/\d+", re.I),
    re.compile(r"ycombinator\.com/companies/[^/]+/jobs/[A-Za-z0-9]", re.I),
    re.compile(r"glassdoor\.[a-z.]+/job-listing/", re.I),
    re.compile(r"(?:boards|job-boards)\.greenhouse\.io/[^/]+/jobs/\d+", re.I),
    re.compile(r"jobs\.lever\.co/[^/]+/[0-9a-f-]{8,}", re.I),
    re.compile(r"jobs\.ashbyhq\.com/[^/]+/[0-9a-f-]{8,}", re.I),
    re.compile(r"myworkdayjobs\.com/.+/job/", re.I),
    re.compile(r"smartrecruiters\.com/[^/]+/\d{6,}", re.I),
    re.compile(r"apply\.workable\.com/[^/]+/j/[0-9A-F]+", re.I),
    re.compile(r"/careers?/[^?#]*(?:job|position|opening)s?/[a-z0-9-]*\d", re.I),
    re.compile(r"/jobs?/(?:view/|details?/)?[a-z0-9-]*-?\d{4,}", re.I),
    re.compile(r"careers\.[^/]+/(?:job|jobs|position)/[^/?#]+", re.I),
]

INDEX_PATTERNS = re.compile(
    r"(/role/l/|/jobs/?$|/jobs\?|/search|[?&](q|query|keywords?)=|/jobs-in-|-jobs-in-|/l/|/location/)",
    re.I)

ROLE_WORDS = re.compile(
    r"\b(engineer|developer|scientist|analyst|intern(ship)?|architect|designer|manager|lead|"
    r"specialist|consultant|sde|programmer|researcher|administrator|devops|sre|tester|qa|"
    r"associate|trainee|fresher|technician|officer|executive)\b", re.I)

NOISE_TITLES = re.compile(r"^(apply( now)?|view( job| details)?|save|share|see more|read more|"
                          r"learn more|details|more|next|previous|sign in|log ?in|register)$", re.I)

MARKDOWN_LINK = re.compile(r"\[([^\]]{2,200})\]\((https?://[^)\s]+|/[^)\s]*)(?:\s+\"([^\"]*)\")?\)")
HTML_LINK = re.compile(r"<a\s[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)
BARE_URL = re.compile(r"https?://[^\s<>()\"']+")

LOCATION_HINT = re.compile(
    r"\b(remote|hybrid|on-?site|work from home|bengaluru|bangalore|hyderabad|pune|mumbai|"
    r"delhi|new delhi|gurgaon|gurugram|noida|chennai|kolkata|ahmedabad|kochi|jaipur|"
    r"chandigarh|indore|guwahati|india|singapore|london|berlin|new york|san francisco|usa|"
    r"united states|europe|canada|dubai)\b", re.I)


def is_listing_url(url: str) -> bool:
    if not url.startswith(("http://", "https://")):
        return False
    if any(pattern.search(url) for pattern in LISTING_PATTERNS):
        path = urlparse(url).path or "/"
        # A bare "/jobs" or a search URL is an index, not a vacancy.
        return not (INDEX_PATTERNS.search(url) and not re.search(r"\d{4,}|[0-9a-f]{8}-", path))
    return False


def looks_like_index(url: str, title: str = "") -> bool:
    """True for aggregator/search pages that list many roles."""
    if is_listing_url(url):
        return False
    lowered = title.casefold()
    return bool(INDEX_PATTERNS.search(url)) or bool(re.search(
        r"\b(\d[\d,]*\+?\s+)?(jobs|vacancies|openings)\b.*\b(in|for|at)\b|\bjobs in\b|careers\s*\|", lowered))


def _clean_title(text: str) -> str:
    text = re.sub(r"[*_`#>]+", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    return " ".join(text.split()).strip(" -|·•:")[:200]


def _strip_links(text: str) -> str:
    text = MARKDOWN_LINK.sub(lambda m: m.group(1), text)
    return re.sub(r"<[^>]+>", " ", text)


def _context(content: str, start: int, end: int) -> tuple[str, str]:
    """Return (text after the link up to the next blank line, short text before it)."""
    window = content[end:end + 400]
    stop = window.find("\n\n")
    tail = window if stop < 0 else window[:stop]
    newline = tail.find("\n[")
    if newline >= 0:  # the next listing starts on the following line
        tail = tail[:newline]
    line_start = content.rfind("\n", 0, start) + 1
    head = content[max(line_start, start - 160):start]
    clean = lambda value: " ".join(_strip_links(value).split())
    return clean(tail)[:400], clean(head)[:160]


def harvest_listings(page_url: str, content: str, *, limit: int = 30,
                     today: date | None = None) -> list[dict[str, Any]]:
    """Return individual listings linked from a fetched page.

    Each item: url, title, context, posted_date (ISO or None), location, skills,
    employer (only when the context states "at <Company>" or "<Company> ·").
    """
    if not content:
        return []
    today = today or date.today()
    page_host = urlparse(page_url).netloc.lower()
    found: dict[str, dict[str, Any]] = {}

    def add(raw_url: str, text: str, title_attr: str, start: int, end: int) -> None:
        url = urljoin(page_url, raw_url.strip()).split("#")[0]
        if url.rstrip("/") == page_url.rstrip("/") or not is_listing_url(url):
            return
        title = _clean_title(text)
        if not title or NOISE_TITLES.match(title) or not ROLE_WORDS.search(title):
            alt = _clean_title(title_attr or "")
            if not (alt and ROLE_WORDS.search(alt) and not NOISE_TITLES.match(alt)):
                return
            title = alt
        tail, head = _context(content, start, end)
        context = f"{head} {tail}".strip()
        key = url.rstrip("/").casefold()
        if key in found:
            return
        posted = parse_relative_date(tail, today) or parse_relative_date(head, today)
        location = LOCATION_HINT.search(f"{title} {tail}") or LOCATION_HINT.search(head)
        employer = None
        at_match = re.search(r"\bat\s+([A-Z][A-Za-z0-9&.,' -]{1,60}?)(?:\s+[|·•(-]|\s+in\s|$)", title)
        if at_match:
            employer = at_match.group(1).strip(" ,.-")
        else:
            lead = re.match(r"\s*([A-Z][\w&.' -]{1,50}?)\s*[·|•]", tail)
            if lead and not LOCATION_HINT.fullmatch(lead.group(1).strip()) \
                    and not parse_relative_date(lead.group(1), today):
                employer = lead.group(1).strip()
        found[key] = {
            "url": url,
            "title": title,
            "context": context,
            "posted_date": posted.isoformat() if posted else None,
            "location": location.group(0) if location else None,
            "skills": find_skills(f"{title} {context}")[:12],
            "employer": employer,
            "index_host": page_host,
        }

    for match in MARKDOWN_LINK.finditer(content):
        add(match.group(2), match.group(1), match.group(3) or "", match.start(), match.end())
        if len(found) >= limit:
            break
    if len(found) < limit:
        for match in HTML_LINK.finditer(content):
            add(match.group(1), re.sub(r"<[^>]+>", " ", match.group(2)), "", match.start(), match.end())
            if len(found) >= limit:
                break
    return list(found.values())[:limit]
