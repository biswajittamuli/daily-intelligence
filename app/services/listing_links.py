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
    r"(/role/l/|/role/[a-z0-9-]+/?$|/job-openings/|/jobs/?$|/jobs\?|/search|[?&](q|query|keywords?)=|/jobs-in-|"
    r"-jobs-in-|/l/|/location/)",
    re.I)

ROLE_WORDS = re.compile(
    r"\b(engineer|developer|scientist|analyst|intern(ship)?|architect|designer|manager|lead|"
    r"specialist|consultant|sde|programmer|researcher|administrator|devops|sre|tester|qa|"
    r"associate|trainee|fresher|technician|officer|executive)\b", re.I)

NOISE_TITLES = re.compile(r"^(apply( now)?|view( job| details)?|save|share|see more|read more|"
                          r"learn more|details|more|next|previous|sign in|log ?in|register)$|"
                          r"^(this|these|the following|view all|see all|browse|show all|we are|our)\b", re.I)

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
        r"\b(\d[\d,]*\+?\s+)?(jobs|vacancies|openings)\b.*\b(in|for|at)\b|\bjobs in\b|careers\s*\||grow with us|"
        r"^[\w\s/+.&-]{2,60}\b(jobs|vacancies|openings)\s*($|[(|\-–—:])|job portal", lowered))


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
        if len(title) > 110 or len(title.split()) > 16:
            title = ""
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


def harvest_career_page(page_url: str, content: str, employer: str, *, limit: int = 40) -> list[dict[str, Any]]:
    """Job links on an employer's own career page: same-site links whose text reads as a role title."""
    found: dict[str, dict[str, Any]] = {}
    host = urlparse(page_url).netloc.lower().removeprefix("www.")
    pairs = [(m.group(1), re.sub(r"<[^>]+>", " ", m.group(2))) for m in HTML_LINK.finditer(content or "")]
    pairs += [(m.group(2), m.group(1)) for m in MARKDOWN_LINK.finditer(content or "")]
    for href, text in pairs:
        url = urljoin(page_url, href.strip()).split("#")[0]
        link_host = urlparse(url).netloc.lower().removeprefix("www.")
        if not url.startswith("http") or url.rstrip("/") == page_url.rstrip("/"):
            continue
        same_site = link_host == host or link_host.endswith("." + host.split(".", 1)[-1])
        if not (same_site or is_listing_url(url)):
            continue
        title = _clean_title(text)
        if not title or len(title) > 110 or NOISE_TITLES.match(title) or not ROLE_WORDS.search(title):
            continue
        if not (is_listing_url(url) or re.search(r"/(jobs?|careers?|openings?|positions?|roles?)/[^/]+", url, re.I)):
            continue
        found.setdefault(url.rstrip("/").casefold(), {"url": url, "title": title, "employer": employer,
                                                      "context": "", "posted_date": None, "location": None,
                                                      "skills": find_skills(title), "index_host": host})
        if len(found) >= limit:
            break
    return list(found.values())


# ------------------------------------------------------------------ employer inference
_CITY_SLUGS = ("bengaluru", "bangalore", "hyderabad", "pune", "chennai", "mumbai", "delhi", "new-delhi", "gurugram",
               "gurgaon", "noida", "ahmedabad", "kochi", "kolkata", "jaipur", "remote", "india", "chandigarh",
               "indore", "coimbatore", "thiruvananthapuram", "trivandrum", "mysuru", "mysore", "nagpur", "vadodara")
_FILLER = {"hiring", "urgent", "urgently", "opening", "openings", "immediate", "immediately", "joiner", "joiners",
           "walk", "walkin", "in", "wfh", "work", "from", "home", "for", "at", "with", "we", "are", "job", "role",
           "freshers", "fresher", "required", "requirement", "opportunity", "only"}
_ATS_SUBDOMAIN = re.compile(r"^(?:www\.)?([a-z0-9-]+)\.(?:zohorecruit\.(?:in|com)|freshteam\.com|keka\.com|darwinbox\.in|"
                            r"recruitee\.com|bamboohr\.com|breezy\.hr|teamtailor\.com)$", re.I)
_ICIMS = re.compile(r"^(?:careers-|jobs-|india-)?([a-z0-9]+)\.icims\.com$", re.I)
_TITLE_EMPLOYER = re.compile(r"(?:job details|careers?|jobs)\s*[|\-–—]\s*([A-Z][\w&.,' ]{1,60}?)\s*$", re.I)
_TITLE_PREFIX = re.compile(r"^([A-Z][\w&.' ]{1,40}?)\s+-\s+.+\bin\s+[A-Z]")
_INDEED_CMP = re.compile(r"indeed\.[a-z.]+/cmp/([A-Za-z0-9][A-Za-z0-9\-]{1,60})", re.I)
_WELLFOUND_CO = re.compile(r"wellfound\.com/company/([a-z0-9][a-z0-9-]{1,60})", re.I)
_LEGAL = re.compile(r"\b(inc|llc|ltd|limited|pvt|private|corp|corporation|services)\.?$", re.I)


def _slug_to_name(slug: str) -> str:
    words = [w for w in re.split(r"[-_]+", slug) if w]
    return " ".join(w.upper() if len(w) <= 3 and w.isalpha() and w not in {"and", "the", "of"} else w.capitalize()
                    for w in words)


def infer_employer(url: str, title: str = "", text: str = "") -> tuple[str | None, str | None]:
    """Employer name from evidence already in hand: URL slug, ATS subdomain, page title or page links.

    Returns (name, how) — ``how`` says which evidence was used; (None, None) when nothing is reliable.
    """
    parsed = urlparse(url or "")
    host = (parsed.hostname or "").casefold()
    path = parsed.path or ""
    # Naukri: /job-listings-<title>-<company>-<city>-<years>-<id>
    if host.endswith("naukri.com") and "/job-listings-" in path:
        slug = path.split("/job-listings-", 1)[1].casefold()
        rest = None
        for variant in (title.casefold(), re.sub(r"\(.*?\)", "", title.casefold())):
            title_slug = re.sub(r"[^a-z0-9+#]+", "-", variant.replace("+", "-").replace("#", "-")).strip("-")
            title_slug = re.sub(r"-+", "-", title_slug)
            if title_slug and slug.startswith(title_slug):
                rest = slug[len(title_slug):].strip("-")
                break
        if rest:
            words = rest.split("-")
            while words and words[0] in _FILLER:
                words.pop(0)
            parts = []
            for word in words:
                if word in _CITY_SLUGS or word.isdigit():
                    break
                parts.append(word)
            if 0 < len(parts) <= 6:
                return _slug_to_name("-".join(parts)), "Naukri listing URL"
    match = _ATS_SUBDOMAIN.match(host) or _ICIMS.match(host)
    if match:
        return _slug_to_name(match.group(1)), "employer recruitment subdomain"
    match = _TITLE_EMPLOYER.search(title or "")
    if match and not re.search(r"\b(naukri|indeed|linkedin|wellfound|glassdoor|foundit|aimlroles|startup)\b",
                               match.group(1), re.I):
        return _LEGAL.sub("", match.group(1).strip(" ,.")).strip(" ,.") or None, "page title"
    match = _TITLE_PREFIX.search(title or "")
    if match:
        return _LEGAL.sub("", match.group(1).strip()).strip(" ,.") or None, "page title"
    if "indeed." in host:
        names = [m.group(1) for m in _INDEED_CMP.finditer(text or "")]
        if names and len({n.casefold() for n in names}) == 1:
            return _slug_to_name(names[0]), "Indeed company link on the listing page"
    if host.endswith("wellfound.com"):
        names = [m.group(1) for m in _WELLFOUND_CO.finditer(text or "")]
        if names and len(set(names)) == 1:
            return _slug_to_name(names[0]), "Wellfound company link on the listing page"
    return None, None
