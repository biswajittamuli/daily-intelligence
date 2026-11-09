"""Deterministic page parsing: links by page region, metadata, JSON-LD JobPosting, embedded app data, sitemaps.

All functions are pure (string in, data out) so they are cheap to test and never call a model.
Retrieved pages are untrusted input: parsing is bounded and nothing in a page is executed.
"""
from __future__ import annotations

import html as html_lib
import json
import re
from typing import Any, Iterable
from urllib.parse import urljoin, urlsplit

from lxml import etree
from lxml import html as lxml_html

from app.services.freshness import parse_date

MAX_PARSE_BYTES = 2_000_000
MAX_JSON_NODES = 20_000


def _doc(content: str):
    if not content or not content.strip():
        return None
    try:
        return lxml_html.document_fromstring(content[:MAX_PARSE_BYTES])
    except (etree.ParserError, ValueError):
        return None


def clean_text(value: Any, limit: int = 20000) -> str:
    text = html_lib.unescape(str(value or ""))
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>|</p>|</li>|</h\d>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()[:limit]


def visible_text(content: str, limit: int = 20000) -> str:
    doc = _doc(content)
    if doc is None:
        return clean_text(content, limit)
    for bad in doc.xpath("//script|//style|//noscript|//template|//svg"):
        bad.drop_tree()
    return " ".join(doc.text_content().split())[:limit]


def _region(element) -> str:
    node = element
    while node is not None:
        tag = str(node.tag).casefold() if isinstance(node.tag, str) else ""
        role = str(node.get("role") or "").casefold() if hasattr(node, "get") else ""
        if tag in {"header", "footer", "nav"}:
            return tag
        if role in {"navigation", "banner", "contentinfo"}:
            return {"navigation": "nav", "banner": "header", "contentinfo": "footer"}[role]
        node = node.getparent()
    return "main"


def page_links(base_url: str, content: str, *, limit: int = 1500) -> list[dict[str, str]]:
    """Every anchor with its absolute URL, visible text, aria-label/title and the page region it sits in."""
    doc = _doc(content)
    if doc is None:
        return []
    base = doc.xpath("//base/@href")
    root = urljoin(base_url, base[0]) if base else base_url
    output, seen = [], set()
    for anchor in doc.xpath("//a[@href]")[: limit * 2]:
        href = str(anchor.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
            continue
        url = urljoin(root, href).split("#")[0]
        if not url.startswith(("http://", "https://")) or url in seen:
            continue
        seen.add(url)
        output.append({"url": url, "text": " ".join(anchor.text_content().split())[:160],
                       "label": " ".join(str(anchor.get("aria-label") or anchor.get("title") or "").split())[:160],
                       "region": _region(anchor)})
        if len(output) >= limit:
            break
    return output


def page_meta(base_url: str, content: str) -> dict[str, str | None]:
    doc = _doc(content)
    if doc is None:
        return {}
    first = lambda xpath: (doc.xpath(xpath) or [None])[0]
    canonical = first("//link[translate(@rel,'CANONICAL','canonical')='canonical']/@href")
    return {
        "title": " ".join(str(first("//title/text()") or "").split())[:300] or None,
        "canonical": urljoin(base_url, canonical) if canonical else None,
        "og_url": first("//meta[@property='og:url']/@content"),
        "og_title": first("//meta[@property='og:title']/@content"),
        "og_site_name": first("//meta[@property='og:site_name']/@content"),
        "description": first("//meta[@name='description']/@content"),
        "generator": first("//meta[@name='generator']/@content"),
    }


def script_json(content: str) -> dict[str, list[Any]]:
    """JSON-LD blocks, Next.js ``__NEXT_DATA__``, Nuxt/other ``application/json`` blobs (parsed, bounded)."""
    doc = _doc(content)
    output: dict[str, list[Any]] = {"jsonld": [], "next_data": [], "app_json": []}
    if doc is None:
        return output
    for script in doc.xpath("//script")[:200]:
        kind = str(script.get("type") or "").casefold()
        sid = str(script.get("id") or "")
        body = (script.text or "").strip()
        if not body or len(body) > 3_000_000:
            continue
        bucket = None
        if kind == "application/ld+json":
            bucket = "jsonld"
        elif sid == "__NEXT_DATA__":
            bucket = "next_data"
        elif kind == "application/json" or sid in {"__NUXT_DATA__", "__APP_STATE__", "ng-state"}:
            bucket = "app_json"
        if bucket is None:
            continue
        try:
            output[bucket].append(json.loads(body))
        except (json.JSONDecodeError, ValueError):
            # Some sites wrap JSON-LD in CDATA or leave trailing commas; try a light repair once.
            repaired = re.sub(r",\s*([}\]])", r"\1", body.replace("<![CDATA[", "").replace("]]>", ""))
            try:
                output[bucket].append(json.loads(repaired))
            except (json.JSONDecodeError, ValueError):
                continue
    return output


def _walk(value: Any, budget: list[int]) -> Iterable[Any]:
    stack = [value]
    while stack and budget[0] > 0:
        node = stack.pop()
        budget[0] -= 1
        yield node
        if isinstance(node, dict):
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)


def _types(node: dict[str, Any]) -> set[str]:
    kind = node.get("@type")
    values = kind if isinstance(kind, list) else [kind]
    return {str(v).split("/")[-1].casefold() for v in values if v}


def _first(value: Any) -> Any:
    return value[0] if isinstance(value, list) and value else value


def _location(node: dict[str, Any]) -> tuple[str | None, str | None]:
    places = node.get("jobLocation")
    places = places if isinstance(places, list) else [places] if places else []
    names = []
    for place in places[:6]:
        if not isinstance(place, dict):
            continue
        address = place.get("address") or {}
        if isinstance(address, str):
            names.append(address)
            continue
        country = address.get("addressCountry")
        country = country.get("name") if isinstance(country, dict) else country
        parts = [address.get("addressLocality"), address.get("addressRegion"), country]
        names.append(", ".join(str(p) for p in parts if p))
    remote = None
    if str(node.get("jobLocationType") or "").upper() == "TELECOMMUTE":
        remote = "remote"
    applicant = node.get("applicantLocationRequirements")
    if remote and applicant:
        applicant = _first(applicant)
        if isinstance(applicant, dict) and applicant.get("name"):
            names.append(f"Remote ({applicant['name']})")
    return ("; ".join(n for n in names if n) or None), remote


def _salary(node: dict[str, Any]) -> tuple[str | None, str | None]:
    salary = node.get("baseSalary") or node.get("estimatedSalary")
    salary = _first(salary)
    if not isinstance(salary, dict):
        return (str(salary) if salary else None), None
    currency = salary.get("currency") or salary.get("salaryCurrency")
    value = salary.get("value")
    if isinstance(value, dict):
        low, high, unit = value.get("minValue"), value.get("maxValue"), value.get("unitText")
        amount = value.get("value")
        text = f"{low}–{high}" if low and high else str(amount or low or high or "")
        if unit:
            text += f" per {str(unit).lower()}"
    else:
        text = str(value or "")
    return (f"{currency or ''} {text}".strip() or None), currency


def job_postings(content: str, page_url: str, *, parsed: dict[str, list[Any]] | None = None) -> list[dict[str, Any]]:
    """schema.org JobPosting objects from JSON-LD (and from embedded app JSON that uses the same vocabulary)."""
    parsed = parsed or script_json(content)
    budget = [MAX_JSON_NODES]
    jobs: list[dict[str, Any]] = []
    for block in parsed["jsonld"] + parsed["next_data"] + parsed["app_json"]:
        for node in _walk(block, budget):
            if not isinstance(node, dict) or "jobposting" not in _types(node):
                continue
            title = clean_text(node.get("title") or node.get("name"), 200)
            if not title:
                continue
            org = _first(node.get("hiringOrganization"))
            employer = org.get("name") if isinstance(org, dict) else (org if isinstance(org, str) else None)
            location, remote = _location(node)
            salary, currency = _salary(node)
            identifier = node.get("identifier")
            identifier = identifier.get("value") if isinstance(identifier, dict) else identifier
            education = node.get("educationRequirements")
            education = _first(education)
            if isinstance(education, dict):
                education = education.get("credentialCategory") or education.get("name")
            experience = node.get("experienceRequirements")
            experience = _first(experience)
            if isinstance(experience, dict):
                months = experience.get("monthsOfExperience")
                experience = f"{round(float(months) / 12, 1)} years" if months not in (None, "") else experience.get("description")
            description = clean_text(node.get("description"), 12000)
            url = node.get("url") or page_url
            posted = parse_date(node.get("datePosted"))
            valid = parse_date(node.get("validThrough"))
            employment = node.get("employmentType")
            jobs.append({
                "title": title, "employer": clean_text(employer, 120) or None,
                "url": urljoin(page_url, str(url)), "location": location, "remote": remote,
                "employment_type": ", ".join(employment) if isinstance(employment, list) else employment,
                "posted_date": posted.isoformat() if posted else None,
                "deadline": valid.isoformat() if valid else None,
                "salary": salary, "salary_currency": currency,
                "education": clean_text(education, 200) or None, "experience": clean_text(experience, 200) or None,
                "skills_text": clean_text(node.get("skills") or node.get("qualifications"), 2000) or None,
                "description": description, "requisition_id": str(identifier)[:80] if identifier else None,
                "direct_apply": node.get("directApply"),
                "extraction_method": "schema.org JobPosting (JSON-LD)",
            })
    return jobs


JOB_TITLE_KEYS = ("title", "jobTitle", "job_title", "name", "text", "position", "designation")
JOB_URL_KEYS = ("absolute_url", "hostedUrl", "jobUrl", "applyUrl", "apply_url", "url", "link", "href", "canonicalUrl",
                "shortlink", "careers_url", "jobPostingUrl")
JOB_HINT_KEYS = {"location", "locations", "department", "team", "employmentType", "employment_type", "jobType",
                 "workplaceType", "isRemote", "remote", "datePosted", "publishedAt", "postedAt", "created_at",
                 "createdAt", "updated_at", "requisition_id", "requisitionId", "job_id", "jobId", "experience",
                 "commitment", "categories", "city", "country", "office", "offices"}
ROLE_HINT = re.compile(r"\b(engineer|developer|scientist|analyst|intern|designer|manager|lead|architect|"
                       r"specialist|consultant|associate|executive|sde|programmer|researcher|devops|sre|qa|tester|"
                       r"trainee|officer|administrator|head|director|recruiter|writer)\b", re.I)


def jobs_from_json(value: Any, base_url: str, *, limit: int = 300) -> list[dict[str, Any]]:
    """Job-like objects inside arbitrary public JSON (Next.js page props, a career page's public API response).

    A node counts only if it has a role-like title AND either a link or at least two job-specific keys,
    so navigation menus and blog lists are not mistaken for vacancies.
    """
    budget = [MAX_JSON_NODES]
    found: dict[str, dict[str, Any]] = {}
    for node in _walk(value, budget):
        if not isinstance(node, dict):
            continue
        title = next((node[k] for k in JOB_TITLE_KEYS if isinstance(node.get(k), str) and node.get(k).strip()), None)
        if not title or len(title) > 140 or not ROLE_HINT.search(title):
            continue
        hints = JOB_HINT_KEYS & set(node)
        link = next((node[k] for k in JOB_URL_KEYS if isinstance(node.get(k), str) and node.get(k).strip()), None)
        if link and not re.match(r"^(https?://|/)", link):
            link = None
        if not link and len(hints) < 2:
            continue
        if not link:
            ident = node.get("id") or node.get("jobId") or node.get("job_id") or node.get("slug")
            if not ident:
                continue
            link = f"{base_url.rstrip('/')}#job-{ident}"
        url = urljoin(base_url, link)
        location = node.get("location") or node.get("city") or node.get("locations") or node.get("office")
        if isinstance(location, dict):
            location = location.get("name") or location.get("city") or location.get("label")
        if isinstance(location, list):
            location = ", ".join(str(l.get("name") if isinstance(l, dict) else l) for l in location[:4])
        posted = parse_date(node.get("datePosted") or node.get("publishedAt") or node.get("postedAt")
                            or node.get("created_at") or node.get("createdAt"))
        description = node.get("description") or node.get("descriptionPlain") or node.get("content") or ""
        found.setdefault(url, {
            "title": clean_text(title, 200), "url": url, "location": clean_text(location, 160) or None,
            "posted_date": posted.isoformat() if posted else None,
            "employment_type": node.get("employmentType") or node.get("employment_type") or node.get("commitment"),
            "remote": "remote" if node.get("isRemote") is True or str(node.get("workplaceType") or "").casefold() == "remote" else None,
            "description": clean_text(description, 8000) if isinstance(description, str) else "",
            "requisition_id": str(node.get("requisitionId") or node.get("requisition_id") or "")[:80] or None,
            "extraction_method": "embedded public JSON",
            "url_is_synthetic": "#job-" in url,
        })
        if len(found) >= limit:
            break
    return list(found.values())


def sitemap_locations(xml_text: str, *, limit: int = 5000) -> tuple[list[str], list[str]]:
    """(page URLs, nested sitemap URLs) from a sitemap or sitemap index. Malformed XML yields nothing."""
    if not xml_text or "<" not in xml_text:
        return [], []
    try:
        parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False, recover=True)
        root = etree.fromstring(xml_text[:MAX_PARSE_BYTES].encode("utf-8", "replace"), parser)
    except (etree.XMLSyntaxError, ValueError):
        return [], []
    if root is None:
        return [], []
    pages, nested = [], []
    tag = etree.QName(root).localname.casefold() if isinstance(root.tag, str) else ""
    for loc in root.iter("{*}loc"):
        value = (loc.text or "").strip()
        if not value.startswith(("http://", "https://")):
            continue
        (nested if tag == "sitemapindex" else pages).append(value)
        if len(pages) + len(nested) >= limit:
            break
    return pages, nested


def same_site(url: str, other: str) -> bool:
    a = (urlsplit(url).hostname or "").casefold().removeprefix("www.")
    b = (urlsplit(other).hostname or "").casefold().removeprefix("www.")
    if not a or not b:
        return False
    return a == b or registrable(a) == registrable(b) and registrable(a) not in SHARED_HOSTS


# Hosts where sibling subdomains belong to different owners.
SHARED_HOSTS = {"github.io", "vercel.app", "netlify.app", "herokuapp.com", "pages.dev", "web.app", "firebaseapp.com",
                "blogspot.com", "wordpress.com", "notion.site", "webflow.io", "framer.website", "wixsite.com"}


def registrable(host: str) -> str:
    """Registrable domain (handles common two-level suffixes such as .co.in, .com.au)."""
    host = (host or "").casefold().removeprefix("www.").rstrip(".")
    parts = host.split(".")
    if len(parts) >= 3 and parts[-2] in {"co", "com", "net", "org", "gov", "ac", "edu"} and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    candidate = ".".join(parts[-2:])
    if candidate in SHARED_HOSTS and len(parts) >= 3:
        return ".".join(parts[-3:])
    return candidate
