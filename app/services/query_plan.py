"""Dynamic, preference-driven search planning and deterministic source classification."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from urllib.parse import urlparse

from app.services.preferences import interests_for, portal_domains


CATEGORY_LABELS = {
    "jobs": "Jobs",
    "government": "Government & PSU",
    "exams": "Exams",
    "news": "AI News",
    "papers": "Research Papers",
}


@dataclass
class QueryPlan:
    category: str
    objective: str
    queries: list[str]
    freshness_days: int | None
    source_guidance: str = ""
    targets: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "objective": self.objective,
            "queries": self.queries,
            "freshness_days": self.freshness_days,
            "source_guidance": self.source_guidance,
            "targets": self.targets,
        }


def _clean(value: str) -> str:
    return " ".join(str(value or "").split())[:300]


def _dedupe(values: list[str], limit: int) -> list[str]:
    output: list[str] = []
    for value in values:
        clean = _clean(value)
        key = clean.casefold()
        if clean and key not in {item.casefold() for item in output}:
            output.append(clean)
        if len(output) >= limit:
            break
    return output


def _location_clause(preferences: dict[str, Any]) -> str:
    jobs = preferences.get("jobs", {})
    locations = jobs.get("locations") or []
    remote = str(jobs.get("remote") or "any")
    parts = []
    if locations:
        parts.append(" OR ".join(locations[:3]))
    if remote == "remote":
        parts.append("remote")
    return " ".join(parts)


def _role_clause(preferences: dict[str, Any]) -> str:
    jobs = preferences.get("jobs", {})
    roles = jobs.get("roles") or []
    skills = jobs.get("skills") or []
    terms = roles[:3] if roles else skills[:3]
    return " ".join(terms)


def _job_plan(request: str, preferences: dict[str, Any], max_queries: int,
              freshness_days: int | None) -> QueryPlan:
    jobs = preferences.get("jobs", {})
    base = _clean(request)
    roles = [str(role).strip() for role in (jobs.get("roles") or []) if str(role).strip()]
    skills = [str(skill).strip() for skill in (jobs.get("skills") or []) if str(skill).strip()]
    experience = str(jobs.get("experience") or "").strip()
    location = _location_clause(preferences)
    qualifier = " ".join(part for part in (
        "" if experience in {"", "any"} else experience,
        location,
    ) if part)
    month = date.today().strftime("%B %Y")
    recency = ""
    if freshness_days is not None:
        recency = "past week" if freshness_days <= 7 else (
            "past month" if freshness_days <= 30 else "past 3 months")

    # Role queries first so truncation never drops coverage of configured roles.
    role_bases = roles[:4] or ([base] if base else [])
    if not role_bases:
        role_bases = ["software and AI roles"]
    queries: list[str] = []
    if base:
        queries.append(base)
    for role in role_bases[:3]:
        queries.append(" ".join(part for part in (role, qualifier, recency, "jobs", month) if part))
    if skills:
        queries.append(" ".join(part for part in (
            " ".join(role_bases[:2]), " ".join(skills[:3]), qualifier, "jobs") if part))

    custom = [str(site).strip().lower().removeprefix("https://").removeprefix("http://").strip("/")
              for site in jobs.get("custom_sites") or []]
    domains = list(dict.fromkeys([site for site in custom if site] + portal_domains(preferences)))
    site_base = role_bases[0] if role_bases else (base or "software")
    # Company career pages and one unrestricted query come before portal site:
    # queries so truncation to max_queries never drops them.
    queries.append(f"{site_base} company career page apply {location} {recency}".strip())
    queries.append(f"latest {base or site_base} job openings {qualifier} official careers apply".strip())
    employment = jobs.get("employment_types") or []
    if employment:
        queries.append(f"{site_base} {' '.join(employment[:2])} {location}".strip())
    remaining = max(0, max_queries - len(_dedupe(queries, max_queries)))
    selected_domains = [domain for domain in domains if domain][:max(2, remaining)]
    for domain in selected_domains:
        queries.append(f"site:{domain} {site_base} {location} {month}".strip())
    return QueryPlan(
        category="jobs",
        objective=(f"Find currently verifiable job listings for: {base or ', '.join(role_bases[:3])}. "
                   "Cover every configured role and both job boards and company career pages. "
                   "Separate actual vacancies from employment news. Prefer original employer or "
                   "job-board listing pages with an application URL, location, experience and date."),
        queries=_dedupe(queries, max_queries),
        freshness_days=freshness_days,
        source_guidance="Employer career pages and job boards; verify each listing before calling it open.",
        targets=selected_domains,
    )


def _government_plan(request: str, preferences: dict[str, Any], max_queries: int,
                    freshness_days: int | None, organizations: list[str]) -> QueryPlan:
    government = preferences.get("government", {})
    disciplines = government.get("disciplines") or []
    gate = str(government.get("gate_paper") or "").strip()
    base = _clean(request)
    if not base:
        base = "government and PSU technical recruitment"
        if disciplines:
            base += " " + " ".join(disciplines[:2])
        if gate:
            base += f" GATE {gate}"
    queries = [base]
    for organization in organizations[:3]:
        queries.append(f"{organization} recruitment notification official")
    queries.append(f"{base} official notification apply online")
    queries.append(f"site:gov.in {base} recruitment")
    queries.append(f"site:nic.in {base} recruitment")
    if gate:
        queries.append(f"{base} GATE {gate} eligibility")
    return QueryPlan(
        category="government",
        objective=(f"Find official government and public-sector recruitment for: {base}. "
                   "Prefer official advertisements, notifications and application portals. "
                   "Extract qualifications, CSE/IT eligibility, vacancies, deadlines and links."),
        queries=_dedupe(queries, max_queries),
        freshness_days=freshness_days,
        source_guidance="Official organisation and government recruitment domains; treat aggregators as discovery only.",
        targets=organizations,
    )


def _exam_plan(request: str, preferences: dict[str, Any], max_queries: int,
               freshness_days: int | None, exams: list[str]) -> QueryPlan:
    base = _clean(request)
    names = exams[:4]
    queries = []
    if base:
        queries.append(base)
    for name in names:
        queries.append(f"{name} official notification important dates")
    if not queries:
        queries.append("competitive examination official notification upcoming dates")
    queries.append(f"{base or 'examination'} official notification {date.today().year}")
    queries.append(f"site:gov.in {base or 'examination'} notification dates")
    return QueryPlan(
        category="exams",
        objective=(f"Find official examination notifications and dated events for: {base or ', '.join(names) or 'followed examinations'}. "
                   "Extract notification, application, admit-card, exam and result dates with evidence."),
        queries=_dedupe(queries, max_queries),
        freshness_days=freshness_days,
        source_guidance="Official examination authority and government domains.",
        targets=names,
    )


def _topic_plan(category: str, request: str, preferences: dict[str, Any],
                max_queries: int, freshness_days: int | None,
                region: str | None = None, topic: str = "") -> QueryPlan:
    from app.services.news_taxonomy import region_query, region_sources, topic_query

    interests = interests_for(preferences, category)
    topic_terms = topic_query(topic) if topic else ""
    base = _clean(request) or (topic_terms if category == "news" and topic_terms else "") \
        or " ".join(interests[:2])
    if not base:
        base = "artificial intelligence" if category == "news" else "machine learning research"
    sources = [str(item).strip() for item in preferences.get(category, {}).get("sources", []) if str(item).strip()]
    if region is None:
        region = str(preferences.get(category, {}).get("region") or "").strip()
    region = "" if region.casefold() in {"global", "all", "any"} else region
    region_clause = region_query(region) if region and region.casefold() not in base.casefold() else ""
    month = date.today().strftime("%B %Y")
    if category == "papers":
        queries = [base, f"{base} arXiv", f"{base} paper benchmark dataset", f"site:arxiv.org {base}"]
    elif region_clause:
        # Regional news: every query carries the region so results are not generic.
        queries = [f"{base} {region_clause} news {month}",
                   f"{region_clause} {topic_terms if topic_terms.casefold().startswith('ai') else 'AI ' + (topic_terms or 'startups government industry')} {month}",
                   f"latest {base} {region_clause} announcement"]
        for source in region_sources(region)[:3]:
            queries.append(f"site:{source} {topic_terms or 'AI'}")
        if region == "India":
            queries.append(f"IndiaAI mission MeitY {topic_terms or 'AI'} {month}")
    else:
        queries = [base, f"{base} {month}", f"latest {base} announcement"]
        if topic_terms and topic_terms not in base:
            queries.append(f"{topic_terms} {month}")
        queries.append(f"{base} official blog")
    for source in sources[:2]:
        queries.append(f"site:{source} {base}")
    return QueryPlan(
        category=category,
        objective=(f"Find recent, substantive {CATEGORY_LABELS.get(category, category).lower()} about: {base}"
                   f"{(' in or about ' + region) if region_clause else ''}"
                   f"{(' — topic: ' + topic) if topic else ''}. "
                   "Prefer specific, dated stories from original publishers over listicles, "
                   "explainers, vendor marketing and aggregators."),
        queries=_dedupe(queries, max_queries),
        freshness_days=freshness_days,
        source_guidance="Original publishers and repositories; exclude promotional duplicates.",
        targets=sources,
    )


def build_plan(category: str, request: str, preferences: dict[str, Any], *,
               max_queries: int = 6, freshness_days: int | None = None,
               organizations: list[str] | None = None,
               exams: list[str] | None = None,
               region: str | None = None, topic: str = "") -> QueryPlan:
    if category == "jobs":
        return _job_plan(request, preferences, max_queries, freshness_days)
    if category == "government":
        return _government_plan(request, preferences, max_queries, freshness_days, organizations or [])
    if category == "exams":
        return _exam_plan(request, preferences, max_queries, freshness_days, exams or [])
    if category in {"news", "papers"}:
        return _topic_plan(category, request, preferences, max_queries, freshness_days,
                           region=region, topic=topic)
    raise ValueError(f"Unknown discovery category: {category}")


JOB_URL_HINTS = re.compile(r"/(jobs?|careers?|vacanc|recruit|apply|position|opening|hiring)", re.I)
JOB_TITLE_HINTS = re.compile(r"\b(job|vacancy|opening|hiring|career|position|role|intern(ship)?|engineer|developer|scientist)\b", re.I)
NEWS_TITLE_HINTS = re.compile(r"\b(how|why|what|trend|report|survey|layoff|hiring plans|salary|market|news|opinion|guide|tips)\b", re.I)
OFFICIAL_DOMAIN_HINTS = (".gov.in", ".nic.in", ".gov", "recruitment.", "careers.", "career.")


def classify_source(category: str, source: dict[str, Any]) -> str:
    """Deterministically label a source as listing/notice/event/article/paper."""
    url = str(source.get("url") or "").lower()
    title = str(source.get("title") or "")
    domain = urlparse(url).netloc.lower()

    if category == "jobs":
        if NEWS_TITLE_HINTS.search(title) and not JOB_URL_HINTS.search(url):
            return "job_news"
        if JOB_URL_HINTS.search(url) or JOB_TITLE_HINTS.search(title):
            return "job_listing"
        if any(token in domain for token in ("wellfound", "naukri", "indeed", "linkedin", "workatastartup")):
            return "job_listing"
        return "job_news"

    if category == "government":
        if domain.endswith(OFFICIAL_DOMAIN_HINTS) or domain.endswith(".gov.in"):
            return "official_notice"
        if re.search(r"\.pdf($|\?)", url):
            return "official_notice"
        return "discovery_source"

    if category == "exams":
        return "exam_notice"

    if category == "papers":
        if any(token in domain for token in ("arxiv.org", "openreview.net", "aclanthology.org",
                                              "mlr.press", "ieee", "acm.org", "springer", "nature.com")):
            return "paper"
        return "technical_resource"

    return "article"


def is_fresh(published: Any, freshness_days: int | None, today: date | None = None) -> bool:
    from app.services.freshness import parse_date
    if freshness_days is None:
        return True
    value = parse_date(published)
    if value is None:
        return True  # Unknown dates stay visible and are labelled unverified.
    today = today or date.today()
    return (today - value).days <= freshness_days
