"""Two-stage job discovery: broad, multi-source candidate pool -> personalized shortlist.

Stage A (broad discovery)
  - role-title variations from the request, preferences and the ACTIVE resume's
    inferred titles (only titles and a few skill keywords leave the machine);
  - several bounded Parallel MCP web_search calls (~10 results each): portal site:
    queries, company-career queries and unrestricted queries;
  - index/aggregator pages are fetched and expanded into individual listings;
  - public company ATS boards (Greenhouse/Lever/Ashby) are read directly;
  - cross-source dedup keeps every source reference.
Stage B (personalized ranking)
  - deterministic extraction (skills, dates, location, experience) + a small, bounded
    local-model extraction for a few detail pages;
  - eligibility/relevance exclusion and active-resume scoring (job_matching.rank_listing);
  - only relevant listings are stored; exclusions are counted with reasons.

Coverage is reported exactly as observed: what was queried, what each platform
returned, what failed. Nothing is claimed for platforms that were not reached.
"""
from __future__ import annotations

import asyncio
import math
import re
import time
from collections import Counter
from dataclasses import replace
from datetime import date
from typing import Any, Callable
from urllib.parse import urlparse

from app.services.listing_links import infer_employer

from app.config import Settings
from app.mcp.normalizer import canonicalize_url
from app.mcp.retrieval import ParallelWebRetriever, RetrievalError
from app.memory.store import Store
from app.services.ats_sources import DEFAULT_COMPANIES, fetch_company_jobs
from app.services.freshness import parse_date, parse_relative_date
from app.services.job_matching import active_resume_match, infer_job_titles
from app.services.listing_links import harvest_listings, is_listing_url, looks_like_index
from app.services.preferences import portal_domains
from app.services.query_plan import classify_source
from app.services.resume import find_skills

POOL_SIZES = (50, 100, 200)

INDIAN_CITIES = ["Bengaluru", "Bangalore", "Hyderabad", "Pune", "Chennai", "Mumbai", "Delhi NCR", "Delhi", "Gurugram",
                 "Gurgaon", "Noida", "Ahmedabad", "Kochi", "Kolkata", "Jaipur", "Chandigarh", "Indore", "Coimbatore",
                 "Thiruvananthapuram", "Bhubaneswar", "Guwahati", "Mysuru", "Nagpur", "Vadodara", "Lucknow"]


def parse_request(request: str) -> dict[str, Any]:
    """Pull role, city, remote, early-career, startup/funded and company hints out of a free-text request."""
    text = " ".join(str(request or "").split())
    lowered = text.casefold()
    city = next((c for c in INDIAN_CITIES if re.search(rf"\b{re.escape(c.casefold())}\b", lowered)), None)
    remote = None
    if re.search(r"\bremote\b", lowered):
        remote = "Remote worldwide" if re.search(r"worldwide|global|anywhere", lowered) else "Remote India"
    fresher = bool(re.search(r"\b(fresher|freshers|entry[- ]level|new grad|graduate|0-1|junior|intern(ship)?s?|trainee|"
                             r"early[- ]career|campus)\b", lowered))
    intern = bool(re.search(r"\bintern(ship)?s?\b", lowered))
    startup = bool(re.search(r"\bstart-?ups?\b", lowered))
    funded = bool(re.search(r"\b(recently )?funded|raised|funding\b", lowered))
    company = None
    match = re.search(r"\bat ([A-Z][\w&.\- ]{1,40}?)(?:\s+in\b|\s*$|,)", text)
    if match and not re.search(r"\b(indian|startups?|companies)\b", match.group(1), re.I):
        company = match.group(1).strip()
    role = re.sub(r"\b(find|search|show|me|latest|current|new|open|jobs?|vacanc\w*|openings?|for|in|the|a|an|please|"
                  r"roles?|positions?|at|indian|india|startups?|start-ups?|recently|funded|remote|worldwide|fresher|"
                  r"freshers|entry[- ]level|early[- ]career|companies|public|listings?|with|of|and|including|include|"
                  r"plus|also|especially|or|like|such as|etc|across|any|all)\b", " ", text, flags=re.I)
    if city:
        role = re.sub(re.escape(city), " ", role, flags=re.I)
    if company:
        role = role.replace(company, " ")
    role = re.sub(r"[,;:()\[\]!?]+", " ", role)
    role = " ".join(role.split()).strip(" .-&/")[:60]
    return {"role": role, "city": city, "remote": remote, "fresher": fresher, "intern": intern, "startup": startup,
            "funded": funded, "company": company}


ROLE_VARIANTS: dict[str, list[str]] = {
    "ai engineer": ["AI Engineer", "Applied AI Engineer", "Generative AI Engineer", "LLM Engineer",
                    "AI Agent Engineer", "Machine Learning Engineer"],
    "llm engineer": ["LLM Engineer", "Generative AI Engineer", "AI Engineer", "NLP Engineer"],
    "ai agent engineer": ["AI Agent Engineer", "Agentic AI Developer", "LLM Engineer", "AI Engineer"],
    "ai intern": ["AI Intern", "ML Intern", "Machine Learning Intern", "Data Science Intern"],
    "ml intern": ["ML Intern", "AI Intern", "Machine Learning Intern"],
    "nlp engineer": ["NLP Engineer", "LLM Engineer", "Machine Learning Engineer"],
    "python backend developer": ["Python Backend Developer", "Python Developer", "Backend Engineer", "Django Developer",
                                 "FastAPI Developer"],
    "research engineer": ["Research Engineer", "Applied Scientist", "ML Research Engineer"],
    "graduate engineer trainee": ["Graduate Engineer Trainee", "Associate Software Engineer", "Trainee Software Engineer"],
    "machine learning engineer": ["Machine Learning Engineer", "ML Engineer", "AI Engineer",
                                  "Data Scientist"],
    "backend developer": ["Backend Developer", "Backend Engineer", "Python Developer",
                          "Software Engineer Backend"],
    "full stack developer": ["Full Stack Developer", "Full Stack Engineer", "MERN Developer"],
    "frontend developer": ["Frontend Developer", "React Developer", "Frontend Engineer"],
    "data engineer": ["Data Engineer", "Big Data Engineer", "ETL Developer"],
    "data analyst": ["Data Analyst", "Business Intelligence Analyst"],
    "devops engineer": ["DevOps Engineer", "Site Reliability Engineer", "Cloud Engineer"],
    "software engineer": ["Software Engineer", "Software Developer", "SDE", "Graduate Engineer Trainee"],
}

PLATFORM_NAMES = {
    "wellfound.com": "Wellfound", "naukri.com": "Naukri", "indeed.com": "Indeed",
    "linkedin.com": "LinkedIn", "workatastartup.com": "YC Work at a Startup",
    "foundit.in": "foundit", "instahyre.com": "Instahyre", "cutshort.io": "Cutshort",
    "hirist.tech": "Hirist", "glassdoor.co.in": "Glassdoor", "glassdoor.com": "Glassdoor",
    "internshala.com": "Internshala", "ycombinator.com": "YC Jobs",
}

TITLE_SUFFIX = re.compile(r"\s*[|\-–—]\s*(wellfound|naukri(\.com)?|indeed|linkedin|glassdoor|foundit|"
                          r"instahyre|cutshort|hirist|internshala|y combinator|work at a startup)\b.*$", re.I)
AT_EMPLOYER = re.compile(r"\b(?:at|@)\s+([A-Z][\w&.' -]{1,50}?)(?:\s+(?:in|-|\||·|•|\()|,|$)")
HIRING = re.compile(r"^([A-Z][\w&.' -]{1,50}?)\s+(?:is\s+)?hiring\b", re.I)
LOCATION_RE = re.compile(
    r"\b(remote|hybrid|bengaluru|bangalore|hyderabad|pune|mumbai|delhi|new delhi|gurgaon|gurugram|noida|"
    r"chennai|kolkata|ahmedabad|kochi|jaipur|chandigarh|indore|guwahati|india)\b", re.I)


def _platform(domain: str) -> str:
    domain = (domain or "").lower().removeprefix("www.")
    for key, name in PLATFORM_NAMES.items():
        if domain == key or domain.endswith("." + key) or domain.startswith(key.split(".")[0] + "."):
            return name
    return domain or "unknown"


def _site_query(domain: str, role: str, location: str) -> str:
    """site: must be a bare domain (MCP tool contract); a path becomes plain keywords."""
    host, _, path = domain.partition("/")
    extra = " ".join(part for part in path.split("/") if part)
    return " ".join(part for part in (f"site:{host}", role, extra, location) if part)


def role_variants(targets: list[str], limit: int = 8) -> list[str]:
    output: list[str] = []
    for target in targets:
        key = " ".join(str(target).split()).casefold()
        for variant in ROLE_VARIANTS.get(key, [str(target).strip()]):
            if variant and variant.casefold() not in {item.casefold() for item in output}:
                output.append(variant)
    return output[:limit]



def _query_tokens(query: str) -> frozenset[str]:
    return frozenset(re.sub(r"[^a-z0-9:.+#]+", " ", query.casefold()).split())


def _drop_near_duplicates(batches: list[dict[str, Any]], threshold: float = 0.85) -> list[dict[str, Any]]:
    """Remove queries that are near-copies of an earlier one (token Jaccard), then empty batches."""
    seen: list[frozenset[str]] = []
    output = []
    for batch in batches:
        kept = []
        for query in batch["queries"]:
            tokens = _query_tokens(query)
            if any(len(tokens & other) / max(1, len(tokens | other)) >= threshold for other in seen):
                continue
            seen.append(tokens)
            kept.append(query)
        if kept:
            output.append({**batch, "queries": kept})
    return output


def _slug_name(slug: str) -> str:
    words = [w for w in re.split(r"[-_.]+", slug) if w]
    return " ".join(w.upper() if len(w) <= 2 else w.capitalize() for w in words) or slug


def _ats_state(status: str, results: int) -> str:
    from app.services.job_sources.models import SourceState
    status = str(status or "")
    if status.startswith("partial"):
        return SourceState.PARTIAL
    if status.startswith("ok"):
        return SourceState.EXTRACT_OK if results else SourceState.NO_RESULTS
    if "404" in status:
        return SourceState.NOT_FOUND
    if "429" in status:
        return SourceState.RATE_LIMITED
    if "401" in status:
        return SourceState.AUTH_REQUIRED
    if "403" in status or "blocked" in status:
        return SourceState.ACCESS_DENIED
    if "Timeout" in status:
        return SourceState.TIMEOUT
    if "HTTPStatusError" in status:
        return SourceState.SERVER_ERROR
    if "ValueError" in status or "JSON" in status:
        return SourceState.UNSUPPORTED
    return SourceState.UNAVAILABLE


def _career_state(outcome: str | None) -> str:
    from app.services.job_sources.models import SourceState
    return {"career_verified": SourceState.EXTRACT_OK, "jobs_endpoint": SourceState.EXTRACT_OK,
            "ats_identified": SourceState.PARTIAL, "career_candidate": SourceState.PARTIAL,
            "access_denied": SourceState.ACCESS_DENIED, "domain_unavailable": SourceState.NOT_FOUND,
            "render_failed": SourceState.TIMEOUT, "not_found": SourceState.NO_RESULTS,
            "search_exhausted": SourceState.NO_RESULTS}.get(outcome or "", SourceState.NO_RESULTS)


def _exclusion_name(reason: str) -> str:
    from app.services.job_sources.models import Exclusion
    mapping = {"Job search page": Exclusion.SEARCH_PAGE, "Not a technical role": Exclusion.NON_TECH,
               "Role does not match": Exclusion.IRRELEVANT_ROLE, "Remote role restricted": Exclusion.REMOTE_RESTRICTED,
               "Outside your preferred": Exclusion.GEOGRAPHY}
    return next((value for prefix, value in mapping.items() if reason.startswith(prefix)), reason)


class BroadJobSearch:
    def __init__(self, settings: Settings, store: Store, preferences: dict[str, Any], *,
                 retriever: Any | None = None, provider: Any | None = None,
                 ats_fetcher: Callable[..., Any] | None = None, http: Any | None = None,
                 browser: Any | None = None, direct_fetch: bool | None = None,
                 skip: dict[str, str] | None = None, discover_employers: bool | None = None,
                 feeds: list[Any] | None = None) -> None:
        self.settings = settings
        self.store = store
        self.preferences = preferences
        self._retriever = retriever
        self._provider = provider
        self._ats_fetcher = ats_fetcher or fetch_company_jobs
        self._http = http
        self._browser = browser
        # Direct fetching (employer sites, career pages) and the browser run live by default; tests inject them.
        self._direct = (retriever is None) if direct_fetch is None else direct_fetch
        # Source ids the user disabled or that are backing off after repeated failures (registry ids).
        self.skip = dict(skip or {})
        self._discover_employers = discover_employers
        self._feeds = feeds

    # ------------------------------------------------------------------ plan
    def plan(self, request: str, pool_size: int) -> dict[str, Any]:
        jobs = self.preferences.get("jobs", {})
        active = self.store.profile()
        profile = (active or {}).get("profile") or {}
        intent = parse_request(request)
        request_role = intent["role"]
        # The request's role leads; the active resume only adds titles, it never blocks other searches.
        targets = ([request_role] if request_role else []) + list(jobs.get("roles") or [])
        if profile and not request_role:
            targets += infer_job_titles(profile)
        if intent["intern"]:
            # An internship request searches intern titles first ("AI internships" -> "AI Intern", "ML Intern").
            base = re.sub(r"\b(intern(ship)?s?|trainee)\b", " ", request_role or "", flags=re.I)
            base = " ".join(base.split()) or "Software Engineering"
            base = base[:1].upper() + base[1:]
            interns = [f"{base} Intern", f"{base} Internship"]
            if re.search(r"\b(ai|ml|machine learning|data|llm|genai)\b", base, re.I):
                interns += ["Machine Learning Intern", "Data Science Intern"]
            interns.append("Software Engineering Intern")
            targets = interns + [t for t in targets if t.casefold() != (request_role or "").casefold()]
        if not targets:
            targets = list(jobs.get("scan_roles") or ["Software Engineer"])
        variants = role_variants(targets)
        if intent["city"]:
            location = intent["city"]
        elif intent["remote"]:
            location = "remote India" if intent["remote"] == "Remote India" else "remote"
        else:
            locations = [item for item in jobs.get("locations") or [] if str(item).strip()
                         and str(item).casefold() not in {"any", "anywhere"}][:2]
            location = " ".join(locations) or "India"
        experience = str(jobs.get("experience") or "any")
        level = "fresher entry level" if intent["fresher"] else {"fresher": "fresher entry level",
                                                                 "internship": "internship",
                                                                 "0-1 years": "entry level"}.get(experience, "")
        month = date.today().strftime("%B %Y")
        # Only titles and up to 3 generic skill keywords are sent externally.
        from app.services.resume import SKILL_VOCABULARY
        known = {item.casefold() for item in SKILL_VOCABULARY}
        skills = [skill for skill in (profile.get("skills") or jobs.get("skills") or [])
                  if str(skill).casefold() in known][:3]
        from app.services.job_sources import portals as portal_policy
        def portal_id(domain: str) -> str | None:
            portal = portal_policy.portal_for(domain)
            return "portal:" + re.sub(r"[^a-z0-9]+", "-", portal.name.casefold()).strip("-") if portal else None
        portals = [domain for domain in portal_domains(self.preferences)
                   if domain and portal_id(domain) not in self.skip]
        search_calls = {50: 4, 100: 8, 200: 12}.get(pool_size, max(3, min(14, math.ceil(pool_size / 15))))
        batches: list[dict[str, Any]] = []
        # 1) portal site: queries — two portals per call, rotated across role variants (search index only)
        for index in range(0, len(portals), 2):
            pair = portals[index:index + 2]
            role = variants[(index // 2) % len(variants)] if variants else "software engineer"
            batches.append({"platform": " + ".join(_platform(domain) for domain in pair),
                            "platforms": [_platform(domain) for domain in pair], "domains": pair,
                            "group": "portal", "method": "MCP site search",
                            "queries": [_site_query(domain, role, location) for domain in pair]})
        # 2) public ATS boards: each hit reveals an employer board that is then read in full through its API
        board_pairs = [("job-boards.greenhouse.io", "jobs.lever.co"), ("jobs.ashbyhq.com", "apply.workable.com"),
                       ("jobs.smartrecruiters.com", "myworkdayjobs.com")]
        for index, pair in enumerate(board_pairs):
            role = variants[index % len(variants)] if variants else "software engineer"
            batches.append({"platform": "Public ATS boards", "method": "MCP site search", "group": "ats",
                            "queries": [f"site:{domain} {role} {location}" for domain in pair]})
        # 3) company career pages + unrestricted discovery, per role variant
        for role in variants:
            batches.append({"platform": "Company career pages", "method": "MCP web search", "group": "career",
                            "queries": [f"{role} careers apply {location} {month}",
                                        f"{role} {level} job opening {location}".strip()]})
            batches.append({"platform": "Open web", "method": "MCP web search", "group": "web",
                            "queries": [f"{role} jobs {location} {month}",
                                        f"{role} {' '.join(skills)} hiring {location}".strip()]})
        # 4) city-specific and remote paths when the location is India-wide
        if not intent["city"] and not intent["remote"] and re.fullmatch(r"(india\s*)+", location.casefold().strip()):
            cities = ["Bengaluru", "Hyderabad", "Pune", "Gurugram", "Chennai", "Noida", "Mumbai"]
            for index, role in enumerate(variants[:3]):
                pair = cities[(index * 2) % len(cities):(index * 2) % len(cities) + 2]
                batches.append({"platform": "City search", "method": "MCP web search", "group": "city",
                                "queries": [f"{role} {level} jobs {city}".strip() for city in pair]})
        # 5) Indian startup hubs (rotates across runs so every hub is covered over a few days)
        hubs = ["Bengaluru", "Hyderabad", "Pune", "Mumbai", "Delhi NCR", "Chennai", "Kochi", "Ahmedabad", "Jaipur"]
        start = int(self.store.get_preference("startup_hub_rotation", 0) or 0) % len(hubs)
        rotated = hubs[start:] + hubs[:start]
        if intent["city"]:
            rotated = [intent["city"]] + [h for h in rotated if h.casefold() != intent["city"].casefold()]
        for index, role in enumerate(variants[:3]):
            pair = rotated[index * 2:index * 2 + 2]
            batches.append({"platform": "Startup hubs", "method": "MCP web search", "group": "startup",
                            "hubs": pair, "queries": [f"{role} startup jobs {city} {level}".strip() for city in pair]})
        if not intent["remote"]:
            for role in variants[:2]:
                batches.append({"platform": "Remote search", "method": "MCP web search", "group": "remote",
                                "queries": [f"{role} remote India {level}".strip(), f"remote {role} job India apply"]})
        skipped_groups = sorted({b.get("group") for b in batches if f"search:{b.get('group')}" in self.skip})
        batches = [b for b in batches if f"search:{b.get('group')}" not in self.skip]
        batches = _drop_near_duplicates(batches)
        ordered = self._interleave(batches)[:search_calls]
        if intent["company"]:
            company_batch = {"platform": "Company careers", "method": "MCP web search", "group": "company",
                             "queries": [f"{intent['company']} careers {variants[0] if variants else ''} jobs".strip(),
                                         f"{intent['company']} official careers page"]}
            ordered = ([company_batch] + ordered)[:max(len(ordered), 1)]
        if intent["startup"] or intent["funded"]:
            ordered = ([{"platform": "Startup job boards", "method": "MCP site search", "group": "startup",
                         "queries": [f"site:wellfound.com {variants[0] if variants else 'engineer'} {location}",
                                     f"{variants[0] if variants else 'engineer'} startup India careers {level}".strip()]}]
                       + ordered)[:max(len(ordered), 1)]
        return {"targets": targets, "variants": variants, "location": location, "intent": intent,
                "search_calls": len(ordered), "batches": ordered, "pool_size": pool_size,
                "resume": (active or {}).get("label"), "portals": portals,
                "paths": sorted({batch.get("group") or "other" for batch in ordered}), "skipped_paths": skipped_groups,
                "objective": (f"Find individual, currently open job listings for {', '.join(variants[:4])} "
                              f"in {location}. Prefer original job pages with title, company, location, "
                              f"date and an apply link. Exclude articles, salary guides and hiring news.")}

    @staticmethod
    def _interleave(batches: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Alternate portal / ATS / career / open-web / city / remote batches so a small budget covers each kind."""
        groups: dict[str, list[dict[str, Any]]] = {}
        for batch in batches:
            groups.setdefault(batch.get("group") or batch["platform"], []).append(batch)
        keys = list(groups)
        output = []
        while any(groups.values()):
            for key in keys:
                if groups[key]:
                    output.append(groups[key].pop(0))
        return output

    # ------------------------------------------------------------------- run
    async def run(self, request: str = "", *, pool_size: int = 100,
                  progress: Callable[[str], None] | None = None,
                  cancel_event: Any | None = None, use_llm: bool = True,
                  include_ats: bool = True) -> dict[str, Any]:
        from app.services.job_sources import ats_registry, portals as portal_policy
        from app.services.job_sources.coverage import Coverage
        from app.services.job_sources.models import Category, Exclusion, SourceState

        progress = progress or (lambda _: None)
        started = time.perf_counter()
        pool_size = int(pool_size) if int(pool_size or 0) > 0 else 100
        pool_size = max(20, min(300, pool_size))
        plan = self.plan(request, pool_size)
        intent_pre = plan["intent"]
        if intent_pre["city"] or intent_pre["remote"]:
            # A location named in the request overrides saved locations for this run only.
            jobs_pref = dict(self.preferences.get("jobs", {}))
            jobs_pref["locations"] = ([intent_pre["city"]] if intent_pre["city"]
                                      else ["India"] if intent_pre["remote"] == "Remote India" else [])
            self.preferences = {**self.preferences, "jobs": jobs_pref}
        session_id = self.store.start_search_session("jobs", request or f"Broad job search ({pool_size})")
        self.store.update_search_session(session_id, plan={k: v for k, v in plan.items() if k != "batches"}
                                         | {"queries": [q for b in plan["batches"] for q in b["queries"]]})
        coverage: dict[str, dict[str, Any]] = {}
        cov = Coverage()
        failures: list[str] = []
        steps: list[str] = []
        timings: dict[str, float] = {}

        def note(message: str) -> None:
            steps.append(message)
            progress(message)

        def check_cancel() -> None:
            if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
                raise asyncio.CancelledError

        def cover(platform: str, method: str, **values: Any) -> None:
            entry = coverage.setdefault(f"{platform}|{method}", {"platform": platform, "method": method,
                                                                 "queries": 0, "results": 0, "status": "ok"})
            for key, value in values.items():
                if key in {"queries", "results", "fetched", "listings"}:
                    entry[key] = entry.get(key, 0) + value
                else:
                    entry[key] = value

        def tag(item: dict[str, Any], report) -> dict[str, Any]:
            item.setdefault("_report_keys", set()).add(report.key)
            return item

        intent = plan["intent"]
        jobs_pref = self.preferences.get("jobs", {})
        # Employer stage: discover new employers when the request is about startups/funded companies,
        # or when enabled in preferences; then read every verified public job board we know of.
        discovery_summary = None
        http = self._http
        browser = self._browser
        owns_http = owns_browser = False
        if self._direct and http is None:
            from app.services.job_sources.safe_http import SafeFetcher
            http = SafeFetcher(concurrency=int(jobs_pref.get("http_concurrency") or 6),
                               per_host_interval=1.0, timeout=15.0,
                               cache_path=self.settings.data_dir / "http-cache.sqlite3")
            await http.__aenter__()
            owns_http = True
        if self._direct and browser is None and jobs_pref.get("browser_rendering", True) \
                and "renderer:browser" not in self.skip:
            from app.services.job_sources.browser import BrowserRenderer
            browser = BrowserRenderer(max_pages=int(jobs_pref.get("browser_concurrency") or 1),
                                      timeout_ms=int(jobs_pref.get("browser_timeout_ms") or 15000))
            owns_browser = True

        mcp_results: list[dict[str, Any]] = []
        listings: list[dict[str, Any]] = []
        index_pages: list[dict[str, Any]] = []
        articles: list[dict[str, Any]] = []
        harvested: list[dict[str, Any]] = []
        career_items: list[dict[str, Any]] = []
        discovered_boards: list[dict[str, Any]] = []
        retriever = self._retriever
        owns = retriever is None
        fetched_pages = 0
        extra_search_budget = {50: 1, 100: 2, 200: 3}.get(pool_size, 2)
        ats_task = None
        companies: list[dict[str, Any]] = []
        try:
            if retriever is None:
                retriever = ParallelWebRetriever(settings=replace(
                    self.settings, max_tool_calls=plan["search_calls"] + 14, max_search_queries=8,
                    max_fetch_urls=20, mcp_timeout=max(self.settings.mcp_timeout, 45.0)))
                await retriever.__aenter__()

            wants_employers = self._discover_employers if self._discover_employers is not None else \
                bool(intent["startup"] or intent["funded"] or jobs_pref.get("discover_employers"))
            if wants_employers and "employers:discovery" not in self.skip:
                from app.services.employer_discovery import EmployerDiscovery
                note("Discovering employers (startup publications, directories, VC portfolios, job platforms)")
                t0 = time.perf_counter()
                try:
                    topic = intent["role"] or (plan["variants"][0] if plan["variants"] else "AI")
                    topic = "AI" if re.search(r"\b(ai|ml|llm|genai|machine learning)\b", topic, re.I) else topic
                    discovery_summary = await EmployerDiscovery(
                        self.settings, self.store, retriever=retriever, http=http, browser=browser,
                        direct=self._direct).run(
                        request, topic=topic, search_calls=4 if pool_size <= 100 else 6,
                        progress=lambda message: note(f"Employers: {message}"), cancel_event=cancel_event,
                        use_llm=self._provider is not None or self._retriever is None)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    failures.append(f"employer discovery: {type(exc).__name__}: {str(exc)[:120]}")
                timings["employer_discovery_s"] = round(time.perf_counter() - t0, 1)

            from app.services.employer_discovery import readable_boards
            base = jobs_pref.get("companies") or DEFAULT_COMPANIES
            known = {(c["ats"], c["slug"].casefold()) for c in base}
            companies = list(base) + [c for c in readable_boards(self.store) if (c["ats"], c["slug"].casefold()) not in known]
            known |= {(c["ats"], c["slug"].casefold()) for c in companies}
            skipped_boards = [c for c in companies if f"ats:{c['ats']}" in self.skip]
            companies = [c for c in companies if f"ats:{c['ats']}" not in self.skip]
            if skipped_boards:
                note(f"Skipping {len(skipped_boards)} boards on disabled or backing-off ATS providers")
            if include_ats and companies:
                note(f"Reading {len(companies)} company career boards (Greenhouse/Lever/Ashby/Workable/…)")
                ats_task = asyncio.create_task(self._ats_fetcher(companies, cancel=check_cancel))

            # ------------------------------------------------ search paths
            t0 = time.perf_counter()
            for index, batch in enumerate(plan["batches"], 1):
                check_cancel()
                note(f"Search {index}/{plan['search_calls']}: {batch['platform']} — {batch['queries'][0]}")
                portal_batch = bool(batch.get("platforms"))
                report = cov.report(batch["platform"] if not portal_batch else f"{batch['platform']} (site search)",
                                    Category.SEARCH, "Parallel web_search")
                report.queries += len(batch["queries"])
                try:
                    results = await retriever.search(batch["queries"], plan["objective"],
                                                     source_guidance="Individual job listing pages",
                                                     freshness_days=30)
                except RetrievalError as exc:
                    message = str(exc)
                    rate = "rate" in message.casefold() or "429" in message
                    report.finish(SourceState.RATE_LIMITED if rate else
                                  SourceState.TIMEOUT if "timed out" in message.casefold() or "timeout" in message.casefold()
                                  else SourceState.UNAVAILABLE, failure=message)
                    cover(batch["platform"], batch["method"], queries=len(batch["queries"]),
                          status=f"failed: {message[:80]}")
                    failures.append(f"{batch['platform']}: {exc}")
                    if rate:
                        note("Search provider rate limit reached; continuing with results so far")
                        break
                    continue
                report.search_results += len(results)
                report.finish(SourceState.SEARCH_OK if results else SourceState.NO_RESULTS)
                if portal_batch:
                    for platform, domain in zip(batch["platforms"], batch.get("domains") or []):
                        hits = sum(1 for item in results if _platform(str(item.get("domain") or "")) == platform)
                        cover(platform, batch["method"], queries=1, results=hits,
                              status="ok" if hits else "no results returned")
                        policy = portal_policy.portal_for(domain)
                        portal_report = cov.report(platform, Category.PORTAL,
                                                   "search index" + (" only (policy)" if policy and
                                                                     policy.policy == portal_policy.SEARCH_ONLY else ""),
                                                   domain=domain)
                        portal_report.queries += 1
                        portal_report.search_results += hits
                        portal_report.detail = policy.reason if policy else None
                        portal_report.finish(SourceState.SEARCH_OK if hits else SourceState.NO_RESULTS)
                else:
                    cover(batch["platform"], batch["method"], queries=len(batch["queries"]), results=len(results),
                          status="ok" if results else "no results returned")
                for item in results:
                    platform = _platform(str(item.get("domain") or ""))
                    item["_via"] = platform if portal_batch else batch["platform"]
                    tag(item, report)
                    if platform in PLATFORM_NAMES.values() and (not portal_batch or platform not in batch["platforms"]):
                        cover(platform, "found via open/career searches", results=1)
                        policy = portal_policy.portal_for(str(item.get("url") or ""))
                        portal_report = cov.report(platform, Category.PORTAL, "found via other searches" + (
                            " (search results only)" if policy and policy.policy == portal_policy.SEARCH_ONLY else ""),
                                                   domain=str(item.get("domain") or ""))
                        portal_report.search_results += 1
                        portal_report.detail = policy.reason if policy else None
                        portal_report.finish(SourceState.SEARCH_OK)
                mcp_results.extend(results)
                if index < plan["search_calls"]:
                    await asyncio.sleep(0.6)
            timings["search_s"] = round(time.perf_counter() - t0, 1)
            if any(b.get("group") == "startup" and b.get("hubs") for b in plan["batches"]):
                self.store.set_preference("startup_hub_rotation",
                                          int(self.store.get_preference("startup_hub_rotation", 0) or 0) + 2)
            cov.set("search_results", len(mcp_results))

            # ------------------------------------------- classify results
            seen: set[str] = set()
            for item in mcp_results:
                url = str(item.get("url") or "")
                key = canonicalize_url(url)
                if not url:
                    cov.exclude(item, Exclusion.BROKEN_URL, "classify")
                    continue
                if key in seen:
                    continue
                seen.add(key)
                kind = classify_source("jobs", item)
                if kind == "job_news":
                    articles.append(item)
                    cov.exclude(item, Exclusion.ARTICLE, "classify")
                elif looks_like_index(url, str(item.get("title") or "")) and not is_listing_url(url) \
                        and not ats_registry.is_ats_listing(url):
                    index_pages.append(item)
                else:
                    listings.append(item)
            cov.set("unique_urls", len(seen))
            note(f"Search returned {len(mcp_results)} results: {len(listings)} listings, "
                 f"{len(index_pages)} index pages, {len(articles)} articles/news (excluded)")

            # ---------------------------- boards revealed by search results
            for board in ats_registry.boards_from_urls(str(item.get("url") or "") for item in mcp_results):
                if (board["ats"], board["slug"].casefold()) in known:
                    continue
                known.add((board["ats"], board["slug"].casefold()))
                discovered_boards.append({"name": _slug_name(board["slug"]), "ats": board["ats"], "slug": board["slug"],
                                          "via": "search result", "url": board["url"]})

            # --------------------------- expand index pages (policy-gated)
            fetch_budget = {50: 4, 100: 6, 200: 10}.get(pool_size, 6)
            to_fetch, skipped = [], 0
            for item in index_pages:
                allowed, reason = portal_policy.may_fetch(str(item["url"]), via="provider")
                if not allowed:
                    item["_exclusion_detail"] = reason
                    cov.exclude(item, Exclusion.SEARCH_PAGE, "policy")
                    skipped += 1
                    policy = portal_policy.portal_for(str(item["url"]))
                    rep = cov.report(policy.name if policy else _platform(str(item.get("domain") or "")),
                                     Category.PORTAL, "index page fetch", domain=str(item.get("domain") or ""))
                    rep.rejected += 1
                    rep.finish(SourceState.POLICY_SKIPPED, failure=reason)
                elif len(to_fetch) < fetch_budget:
                    to_fetch.append(item)
                else:
                    item["_exclusion_detail"] = "index page beyond this run's fetch budget"
                    cov.exclude(item, Exclusion.SEARCH_PAGE, "budget")
            detail_candidates = [item for item in listings if is_listing_url(str(item.get("url")))
                                 and portal_policy.may_fetch(str(item["url"]), via="provider")[0]][:4]
            fetch_urls = [item["url"] for item in to_fetch + detail_candidates][:20]
            pages: dict[str, str] = {}
            if fetch_urls:
                check_cancel()
                note(f"Fetching {len(to_fetch)} index pages and {len(detail_candidates)} listing pages"
                     + (f" ({skipped} portal pages skipped by access policy)" if skipped else ""))
                for start in range(0, len(fetch_urls), 5):
                    chunk = fetch_urls[start:start + 5]
                    try:
                        fetched = await retriever.fetch(chunk, plan["objective"],
                                                        search_queries=plan["batches"][0]["queries"],
                                                        full_content=True)
                        for page in fetched:
                            content = str(page.get("full_content") or page.get("content") or "")
                            if content:
                                pages[canonicalize_url(str(page.get("url") or ""))] = content
                    except RetrievalError as exc:
                        message = str(exc).strip() or "timed out"
                        failures.append(f"page fetch ({len(chunk)} URLs): {message[:120]}")
                fetched_pages = len(pages)
            for item in to_fetch:
                content = pages.get(canonicalize_url(item["url"]))
                platform = _platform(str(item.get("domain") or ""))
                rep = cov.report(platform, Category.PORTAL if portal_policy.portal_for(item["url"]) else Category.SEARCH,
                                 "index page via Parallel fetch", domain=str(item.get("domain") or ""))
                if not content:
                    cover(platform, "page fetch", fetched=0, status="not retrievable (blocked or empty)")
                    rep.finish(SourceState.UNAVAILABLE, failure="page not retrievable (blocked or empty)")
                    item["_exclusion_detail"] = "index page could not be retrieved"
                    cov.exclude(item, Exclusion.EXTRACTION_FAILED, "fetch")
                    continue
                links = harvest_listings(item["url"], content)
                rep.fetched += 1
                rep.parsed += 1
                rep.listings += len(links)
                rep.finish(SourceState.EXTRACT_OK if links else SourceState.NO_RESULTS)
                cover(platform, "page fetch", fetched=1, listings=len(links))
                cov.add("pages_parsed")
                for link in links:
                    link["_via"] = platform
                    tag(link, rep)
                harvested.extend(links)
            for item in detail_candidates:
                content = pages.get(canonicalize_url(item["url"]))
                if content:
                    item["content"] = content
                    cov.add("pages_parsed")
                else:
                    cover(_platform(str(item.get("domain") or "")), "page fetch",
                          status="detail page not retrievable")
            if harvested:
                note(f"Expanded index pages into {len(harvested)} individual listings")
            cov.add("pages_fetched", fetched_pages)

            # ------------------------------------------------- public feeds
            if self._direct and http is not None:
                from app.services.job_sources.feeds import read_feeds
                feed_items, feed_reports = await read_feeds(http, feeds=self._feeds, skip=self.skip)
                for entry in feed_reports:
                    feed = entry["feed"]
                    rep = cov.report(feed.name, Category.PORTAL, "public feed", domain=feed.url)
                    rep.listings += entry["count"]
                    rep.http_status = entry.get("http_status")
                    rep.fetched += int(entry["state"] == SourceState.EXTRACT_OK)
                    rep.finish(entry["state"], failure=entry.get("reason"))
                    for item in feed_items:
                        if item.get("feed_id") == feed.source_id:
                            tag(item, rep)
                if feed_items:
                    note(f"Public feeds returned {len(feed_items)} listings")
                harvested.extend(feed_items)
                cov.add("pages_fetched", sum(1 for e in feed_reports if e.get("http_status")))

            # ------------------- unknown employers, career pages, rediscovery
            if self._direct and http is not None and not {"career:discovery", "employers:resolution"} <= set(self.skip):
                t0 = time.perf_counter()
                extra = await self._employer_pages(retriever, http, browser, listings + harvested, intent,
                                                   pool_size, extra_search_budget, cov, note, check_cancel, failures)
                career_items.extend(extra["listings"])
                for board in extra["boards"]:
                    if (board["ats"], board["slug"].casefold()) not in known:
                        known.add((board["ats"], board["slug"].casefold()))
                        discovered_boards.append(board)
                cov.add("pages_fetched", extra["pages"])
                cov.add("pages_parsed", extra["parsed"])
                timings["career_pages_s"] = round(time.perf_counter() - t0, 1)
        except asyncio.CancelledError:
            if ats_task:
                ats_task.cancel()
            self.store.update_search_session(session_id, status="cancelled", error="Cancelled by user")
            await self._close(retriever if owns else None, http if owns_http else None, browser if owns_browser else None)
            raise
        except RetrievalError as exc:
            failures.append(f"search: {exc}")
            note(f"Web search unavailable ({str(exc)[:80]}); continuing with company boards")
        finally:
            if owns and retriever is not None:
                try:
                    await retriever.__aexit__(None, None, None)
                except Exception:
                    pass
                retriever = None

        if discovery_summary:
            company_reports = {}
            for company in discovery_summary.get("companies") or []:
                company_reports[company["name"]] = cov.report(company["name"], Category.EMPLOYER_DISCOVERY,
                                                              "career discovery", domain=company.get("website"))
            for item in discovery_summary.get("career_listings") or []:
                item["_via"] = "Company career page"
                if company_reports.get(item.get("employer")):
                    tag(item, company_reports[item["employer"]])
                harvested.append(item)
            for company in discovery_summary.get("companies") or []:
                status = company.get("career_status") or "website not found"
                cover(company["name"], "employer discovery", results=company.get("ats_jobs") or 0,
                      status=status + (f" ({company['ats_provider']})" if company.get("ats_provider") else ""))
                rep = cov.report(company["name"], Category.EMPLOYER_DISCOVERY, "career discovery",
                                 domain=company.get("website"))
                rep.listings += company.get("career_listings_count") or 0
                rep.detail = status
                rep.finish(SourceState.EXTRACT_OK if company.get("career_outcome") in
                           {"career_verified", "ats_identified", "jobs_endpoint"} else
                           SourceState.ACCESS_DENIED if company.get("career_outcome") == "access_denied" else
                           SourceState.NO_RESULTS)

        # --------------------------------------------- ATS board reads
        ats_jobs: list[dict[str, Any]] = []
        ats_coverage: list[dict[str, Any]] = []
        t0 = time.perf_counter()
        if ats_task:
            try:
                jobs_found, ats_coverage = await ats_task
                ats_jobs.extend(jobs_found)
            except Exception as exc:  # never fail the whole run for one source type
                failures.append(f"company boards: {type(exc).__name__}")
        cap = {50: 8, 100: 15, 200: 25}.get(pool_size, 15)
        discovered_boards = [b for b in discovered_boards if f"ats:{b['ats']}" not in self.skip]
        if include_ats and discovered_boards:
            new_boards = discovered_boards[:cap]
            note(f"Reading {len(new_boards)} newly discovered public job boards")
            try:
                jobs_found, more = await self._ats_fetcher(new_boards, cancel=check_cancel)
                ats_jobs.extend(jobs_found)
                ats_coverage.extend(more)
                self._persist_boards(new_boards, jobs_found, more)
            except Exception as exc:
                failures.append(f"discovered boards: {type(exc).__name__}")
        timings["ats_s"] = round(time.perf_counter() - t0, 1)
        board_reports: dict[str, Any] = {}
        for entry in ats_coverage:
            cover(entry["platform"], entry["method"], results=entry["results"], status=entry["status"])
            rep = cov.report(entry["platform"], Category.ATS, entry["method"])
            rep.listings += entry["results"]
            rep.parsed += 1 if str(entry["status"]).startswith("ok") else 0
            rep.finish(_ats_state(entry["status"], entry["results"]), failure=None if str(entry["status"]).startswith("ok")
                       else entry["status"])
            board_reports[entry["platform"]] = rep
        if ats_coverage:
            note(f"Company boards returned {len(ats_jobs)} openings from "
                 f"{sum(1 for e in ats_coverage if str(e['status']).startswith('ok'))} of {len(ats_coverage)} boards")
        cov.set("ats_openings", len(ats_jobs))
        # Incremental scan: boards read completely tell us which stored vacancies disappeared.
        from app.services.verification import reconcile_boards
        reconciliation = reconcile_boards(self.store, ats_jobs, ats_coverage)
        if reconciliation["checked"]:
            note(f"Board reconciliation: {reconciliation['still_listed']} still listed, {reconciliation['missing_once']} "
                 f"missing once, {reconciliation['closed']} closed after two misses")

        # ---------------------------------------------------------- Stage B
        check_cancel()
        board_employers = {f"{c['ats']}:{c['slug']}": c.get("employer_id") for c in companies + discovered_boards}
        names_by_board = {f"{c['ats']}:{c['slug']}": c.get("name") for c in companies + discovered_boards}
        for job in ats_jobs:
            key = str(job.get("source_platform") or "")
            job["employer_id"] = job.get("employer_id") or board_employers.get(key)
            rep = board_reports.get(names_by_board.get(key) or job.get("employer"))
            if rep is not None:
                tag(job, rep)
        for item in career_items:
            harvested.append(item)
        cov.set("career_page_listings", len(career_items) + sum(1 for h in harvested if h.get("_via") == "Company career page"))
        cov.set("harvested", sum(1 for h in harvested if h.get("_via") not in {"Company career page"}))
        candidates, duplicates = self._candidates(listings, harvested, ats_jobs, cov)
        raw_total = len(mcp_results) + len(harvested) + len(ats_jobs)
        cov.set("listings_extracted", len(listings) + len(harvested) + len(ats_jobs))
        note(f"Ranking {len(candidates)} unique candidates against "
             f"{'resume “' + plan['resume'] + '”' if plan['resume'] else 'your preferences'}")

        t0 = time.perf_counter()
        if use_llm:
            await self._llm_enrich([item for item in candidates if item.get("_content")][:4])
        timings["model_s"] = round(time.perf_counter() - t0, 1)

        resumes = self.store.resumes()
        today = date.today()
        from app.services.requirements import extract_requirements
        ranked, ineligible, excluded, gate_counts = [], [], Counter(), Counter()
        not_vacancy = 0
        t0 = time.perf_counter()
        from app.services.job_matching import relevance_gate
        active_profile = next((r.get("profile") for r in resumes if r.get("is_default")
                               and r.get("status", "processed") == "processed"), None)
        for item in candidates:
            gate = relevance_gate(item, active_profile, self.preferences, targets=plan["variants"])
            if gate["excluded"]:
                # Cheap rejection first: no requirement extraction or assessment for clearly irrelevant openings.
                eligibility = {"tier": "excluded", "excluded_reason": gate["excluded"]}
            else:
                item["_requirements"] = extract_requirements(str(item.get("raw_text") or ""),
                                                             title=str(item.get("title") or ""))
                match = active_resume_match(item, self.preferences, resumes, targets=plan["variants"], today=today)
                eligibility = match["eligibility"]
            if eligibility["tier"] == "excluded":
                reason = eligibility["excluded_reason"].split(" (")[0].split(" you have")[0]
                excluded[reason] += 1
                not_vacancy += int(reason.startswith("Job search page"))
                item["_exclusion_detail"] = eligibility["excluded_reason"]
                cov.exclude(item, _exclusion_name(reason), "relevance")
                item["_rejected"] = True
                continue
            item.update(match)
            if eligibility["tier"] == "ineligible":
                for gate in eligibility.get("gates") or []:
                    gate_counts[gate.split(":")[0]] += 1
                ineligible.append(item)
            else:
                ranked.append(item)
        timings["ranking_s"] = round(time.perf_counter() - t0, 1)
        excluded["Articles / hiring news (not vacancies)"] += len(articles)
        cov.set("valid_jobs", len(candidates) - not_vacancy)
        cov.set("relevant_jobs", len(ranked) + len(ineligible))
        # A request about startups puts listings from known startup employers first (ranking within each
        # group is unchanged); other relevant listings still follow.
        startup_ids, startup_names = set(), set()
        if intent["startup"] or intent["funded"]:
            for employer in self.store.employers(limit=2000):
                if employer.get("classification") == "startup":
                    startup_ids.add(employer["id"])
                    startup_names.add(Store._norm_company(employer["name"]))

        def is_startup(job: dict[str, Any]) -> bool:
            return bool(startup_ids) and (job.get("employer_id") in startup_ids or
                                          Store._norm_company(str(job.get("employer") or "")) in startup_names)
        key = lambda job: (is_startup(job), (job.get("eligibility") or {}).get("composite") or 0,
                           job.get("posted_date") or "")
        ranked.sort(key=key, reverse=True)
        ineligible.sort(key=key, reverse=True)
        # Every relevant listing is kept (up to a safety cap) so recall is not lost to the shortlist size;
        # the UI ranks them. A few high-match ineligible roles stay visible as "stretch" roles.
        store_cap = max(pool_size, int(jobs_pref.get("store_cap") or 500))
        stretch = [job for job in ineligible if (job.get("match_score") or 0) >= 60][:max(10, pool_size // 5)]
        for job in ranked[store_cap:]:
            cov.exclude(job, Exclusion.POOL_LIMIT, "shortlist")
        stretch_ids = {id(job) for job in stretch}
        for job in ineligible:
            if id(job) not in stretch_ids:
                job["_exclusion_detail"] = "; ".join((job.get("eligibility") or {}).get("gates") or [])
                cov.exclude(job, Exclusion.INELIGIBLE, "eligibility")
        shortlist = ranked[:store_cap] + stretch
        records = [self._record(item) for item in shortlist]
        saved = self.store.upsert_jobs(records)
        cov.set("stored_jobs", len(saved))
        self.store.link_jobs_to_employers()
        rescore_stored(self.store, self.preferences)  # keep older listings consistent with this ranking
        tiers = Counter((item.get("eligibility") or {}).get("tier") for item in shortlist)
        expired = sum(1 for record in records if record.get("status") in {"expired", "closed"})
        # Per-source funnel: which sources produced extracted listings, and which made the stored shortlist.
        funnel: dict[str, dict[str, int]] = {}
        shown_ids = {id(item) for item in shortlist}
        relevant_ids = {id(item) for item in ranked + ineligible}
        for item in candidates:
            names = set()
            for source in item.get("sources") or []:
                if source.get("via") == "Company career board":
                    names.add(str(item.get("employer") or source.get("platform") or "company board"))
                else:
                    names.add(_platform(urlparse(str(source.get("url") or "")).hostname or ""))
            for name in names:
                entry = funnel.setdefault(name, {"extracted": 0, "relevant": 0, "stored": 0, "verified": 0})
                entry["extracted"] += 1
                entry["relevant"] += int(id(item) in relevant_ids)
                entry["stored"] += int(id(item) in shown_ids)
                entry["verified"] += int(id(item) in shown_ids and item.get("discovered_via") == "company career board")
            for report_key in item.get("_report_keys") or ():
                report = cov.reports.get(report_key)
                if report is None:
                    continue
                report.unique += 1
                report.rejected += int(bool(item.get("_rejected")))
                report.stored += int(id(item) in shown_ids)
                report.verified += int(id(item) in shown_ids and item.get("discovered_via") == "company career board")
        acquisition = cov.summary()
        resources = self._resources(http, browser, timings)
        summary = {
            "category": "jobs", "kind": "broad_search", "status": "complete" if saved else "empty",
            "request": request, "resume": plan["resume"], "pool_size": pool_size,
            "targets": plan["variants"], "search_calls": plan["search_calls"], "search_paths": plan["paths"],
            "raw_results": raw_total, "mcp_results": len(mcp_results), "harvested": len(harvested),
            "ats_openings": len(ats_jobs), "unique_candidates": len(candidates),
            "career_page_listings": cov.funnel.get("career_page_listings", 0), "boards_discovered": len(discovered_boards),
            "excluded": dict(excluded), "excluded_total": sum(excluded.values()),
            "ranked": len(ranked), "stored": len(saved), "records": len(saved),
            "ineligible": len(ineligible), "ineligible_stored": len(stretch), "ineligible_reasons": dict(gate_counts),
            "duplicates": duplicates, "expired": expired,
            "strong": tiers.get("strong", 0), "possible": tiers.get("possible", 0), "low": tiers.get("low", 0),
            "pages_fetched": cov.funnel.get("pages_fetched", 0), "sources_found": raw_total,
            "coverage": sorted(coverage.values(), key=lambda entry: (-entry.get("results", 0), entry["platform"])),
            "funnel": funnel, "acquisition": acquisition, "resources": resources,
            "reconciliation": reconciliation, "skipped_sources": self.skip,
            "intent": intent, "employer_discovery": {k: v for k, v in (discovery_summary or {}).items()
                                                      if k not in {"companies", "career_listings"}} or None,
            "employers_considered": len(companies) + len(discovered_boards),
            "startup_listings": sum(1 for job in shortlist if is_startup(job)) if startup_ids else None,
            "failures": failures, "steps": steps, "session_id": session_id,
            "duration_seconds": round(time.perf_counter() - started, 1),
        }
        if not saved:
            summary["reason"] = "No relevant listing survived ranking; see coverage and exclusions."
        self.store.update_search_session(session_id, status=summary["status"], summary=summary)
        self.store.save_coverage(session_id, acquisition["sources"], cov.exclusions)
        await self._close(None, http if owns_http else None, browser if owns_browser else None)
        summary["resources"] = self._resources(http, browser, timings)
        self.store.update_search_session(session_id, summary=summary)
        note(f"Stored {len(saved)} ranked listings: {summary['strong']} strong, {summary['possible']} possible")
        return summary

    # ------------------------------------------------- employer pages stage
    async def _employer_pages(self, retriever, http, browser, items, intent, pool_size, search_budget, cov, note,
                              check_cancel, failures) -> dict[str, Any]:
        """Resolve unknown employers seen in results, re-run due career discoveries, read verified career pages."""
        from app.services.employer_discovery import NON_COMPANY_DOMAINS, _registrable, domain_of, name_matches_domain
        from app.services.job_sources import ats_registry
        from app.services.job_sources.career_discovery import CareerDiscovery, discover_many
        from app.services.job_sources.models import Category, SourceState

        output = {"listings": [], "boards": [], "pages": 0, "parsed": 0}
        budget = {"searches": search_budget}

        async def search(queries: list[str]) -> list[dict[str, Any]]:
            if budget["searches"] <= 0:
                return []
            budget["searches"] -= 1
            return await retriever.search(queries[:4], "Find each company's official careers page or public job board.")

        discovery = CareerDiscovery(http, browser=browser, search=search)
        # 1) unknown employers named in this run's results (and the company named in the request)
        names = Counter()
        for item in items:
            employer = str(item.get("employer") or "").strip()
            if not employer:
                match = AT_EMPLOYER.search(TITLE_SUFFIX.sub("", str(item.get("title") or "")))
                employer = match.group(1).strip(" ,.-") if match else ""
            if employer and len(employer) <= 50 and _platform(employer.casefold()) not in PLATFORM_NAMES.values():
                names[employer] += 1
        wanted = [intent["company"]] if intent.get("company") else []
        if "employers:resolution" in self.skip:
            budget["searches"] = 0
        limit = {50: 2, 100: 4, 200: 6}.get(pool_size, 4)
        for name, _count in names.most_common(40):
            if len(wanted) >= limit + len(wanted[:1]):
                break
            if not self.store.find_employer(name) and name.casefold() not in {w.casefold() for w in wanted}:
                wanted.append(name)
        resolved: list[dict[str, Any]] = []
        if wanted and budget["searches"] > 0:
            note(f"Resolving {len(wanted)} employer(s) not yet known: {', '.join(wanted)}")
            check_cancel()
            try:
                results = await search([f"{name} careers" for name in wanted])
            except Exception as exc:
                failures.append(f"employer resolution search: {str(exc)[:120]}")
                results = []
            for name in wanted:
                stored = self.store.find_employer(name)
                entry = {"name": name, "website": (stored or {}).get("website"), "employer_id": (stored or {}).get("id"),
                         "career_discovery": (stored or {}).get("career_discovery")}
                first = re.escape(name.split()[0]) if name.split() else None
                for result in results:
                    url = str(result.get("url") or "")
                    host = domain_of(url) or ""
                    hit = ats_registry.detect_url(url)
                    text = f"{result.get('title') or ''} {url}"
                    if hit and hit[0].readable and first and re.search(first, text, re.I):
                        output["boards"].append({"name": name, "ats": hit[0].key, "slug": hit[1], "via": "employer resolution",
                                                 "url": url})
                        entry.setdefault("ats", {"provider": hit[0].key, "slug": hit[1], "url": url})
                    elif not entry.get("website") and host and host not in NON_COMPANY_DOMAINS and \
                            _registrable(host) not in NON_COMPANY_DOMAINS and name_matches_domain(name, host):
                        entry["website"] = f"https://{_registrable(host)}"
                if entry.get("website") or entry.get("ats"):
                    employer, created = self.store.upsert_employer({
                        "name": name, "website": entry.get("website"),
                        "domain": domain_of(entry["website"]) if entry.get("website") else None,
                        "ats_provider": (entry.get("ats") or {}).get("provider"),
                        "ats_slug": (entry.get("ats") or {}).get("slug"),
                        "career_url": (entry.get("ats") or {}).get("url"),
                        "discovery_sources": ["job search: employer resolution"]})
                    entry["employer_id"] = employer["id"]
                    entry["created"] = created
                    rep = cov.report(name, Category.EMPLOYER_DISCOVERY, "employer resolution", domain=entry.get("website"))
                    rep.detail = ("new employer; " if created else "") + (f"website {entry.get('website')}" if entry.get(
                        "website") else "no website") + (f"; ATS {entry['ats']['provider']}" if entry.get("ats") else "")
                    rep.finish(SourceState.EXTRACT_OK)
                    if entry.get("website"):
                        resolved.append(entry)
                else:
                    rep = cov.report(name, Category.EMPLOYER_DISCOVERY, "employer resolution")
                    rep.finish(SourceState.NO_RESULTS, failure="official domain not found in search results")
        # 2) stored employers whose discovery is due (never run, or retry time reached)
        due = [] if "career:discovery" in self.skip else \
            self.store.employers_due_for_discovery(limit={50: 2, 100: 3, 200: 5}.get(pool_size, 3))
        targets = resolved + [{"name": e["name"], "website": e["website"], "employer_id": e["id"],
                               "career_discovery": e.get("career_discovery")} for e in due
                              if e["id"] not in {r.get("employer_id") for r in resolved}]
        if targets:
            note(f"Career-page discovery for {len(targets)} employer(s)")
            results = await discover_many(targets, discovery, concurrency=3, cancel=check_cancel,
                                          progress=lambda message: note(message))
            for target, result in zip(targets, results):
                if target.get("employer_id"):
                    self.store.save_career_discovery(target["employer_id"], result)
                output["pages"] += sum(1 for m in result.get("methods") or [] if m["state"] in {SourceState.FETCH_OK})
                rep = cov.report(target["name"], Category.CAREER, "career discovery (" + ", ".join(
                    dict.fromkeys(m["method"] for m in result.get("methods") or [])) + ")", domain=target["website"])
                rep.listings += len(result.get("listings") or [])
                rep.detail = result.get("outcome_label")
                rep.finish(_career_state(result.get("outcome")), failure=None if result.get("outcome") in
                           {"career_verified", "ats_identified", "jobs_endpoint"} else result.get("outcome_label"))
                ats = result.get("ats") or {}
                if ats.get("readable"):
                    output["boards"].append({"name": target["name"], "ats": ats["provider"], "slug": ats["slug"],
                                             "employer_id": target.get("employer_id"), "via": "career discovery",
                                             "url": ats.get("url")})
                for job in result.get("listings") or []:
                    if job.get("url_is_synthetic"):
                        continue
                    output["parsed"] += 1
                    output["listings"].append({**job, "employer": job.get("employer") or target["name"],
                                               "employer_id": target.get("employer_id"), "_via": "Company career page",
                                               "_report_keys": {rep.key}})
        # 3) verified career pages without a readable board: re-read the page (static, cached, cheap)
        readable = {"greenhouse", "lever", "ashby", "workable", "smartrecruiters", "recruitee"}
        pages = [e for e in self.store.employers(limit=1000) if e.get("career_outcome") == "career_verified"
                 and e.get("career_url") and not (e.get("ats_provider") in readable and e.get("ats_slug"))
                 and e["id"] not in {t.get("employer_id") for t in targets}][:{50: 3, 100: 6, 200: 10}.get(pool_size, 6)]
        if "career:read" in self.skip:
            pages = []
        for employer in pages:
            check_cancel()
            rep = cov.report(employer["name"], Category.CAREER, "career page read", domain=employer.get("domain"))
            methods: list[dict[str, Any]] = []
            outcome = await discovery.read_career_page(employer["career_url"], employer["name"],
                                                       lambda *a, **k: methods.append({"state": a[2], "detail": a[3] if len(a) > 3 else ""}),
                                                       allow_browser=browser is not None)
            output["pages"] += 1
            jobs = [job for job in outcome["listings"] if not job.get("url_is_synthetic")]
            rep.fetched += 1
            rep.listings += len(jobs)
            last = methods[-1] if methods else {"state": SourceState.UNAVAILABLE, "detail": ""}
            rep.finish(SourceState.EXTRACT_OK if jobs else last["state"] if last["state"] not in SourceState.SUCCESS
                       else SourceState.NO_RESULTS, failure=None if jobs else last.get("detail"))
            for job in jobs:
                output["parsed"] += 1
                output["listings"].append({**job, "employer": job.get("employer") or employer["name"],
                                           "employer_id": employer["id"], "_via": "Company career page",
                                           "_report_keys": {rep.key}})
        return output

    def _persist_boards(self, boards: list[dict[str, Any]], jobs: list[dict[str, Any]],
                        coverage: list[dict[str, Any]]) -> None:
        """Boards found through search that returned openings become (or update) employers."""
        counts = Counter(str(job.get("source_platform") or "") for job in jobs)
        names = {}
        for job in jobs:
            names.setdefault(str(job.get("source_platform") or ""), job.get("employer"))
        for board in boards:
            key = f"{board['ats']}:{board['slug']}"
            if not counts.get(key):
                continue
            name = board.get("name") if board.get("via") != "search result" else (names.get(key) or board["name"])
            employer, _created = self.store.upsert_employer({
                "name": name or board["name"], "ats_provider": board["ats"], "ats_slug": board["slug"],
                "career_url": board.get("url"), "career_status": f"public job board ({board.get('via') or 'discovered'})",
                "discovery_sources": [f"job search: {board.get('via') or 'board'}"], "open_jobs": counts[key]})
            board["employer_id"] = employer["id"]
            for job in jobs:
                if str(job.get("source_platform") or "") == key:
                    job["employer_id"] = employer["id"]

    async def _close(self, retriever, http, browser) -> None:
        for resource in (retriever, http):
            if resource is not None:
                try:
                    await resource.__aexit__(None, None, None)
                except Exception:
                    pass
        if browser is not None:
            try:
                await browser.close()
            except Exception:
                pass

    @staticmethod
    def _resources(http, browser, timings: dict[str, float]) -> dict[str, Any]:
        import resource as _resource
        output: dict[str, Any] = {"timings": timings,
                                  "peak_app_rss_mb": round(_resource.getrusage(_resource.RUSAGE_SELF).ru_maxrss / 1024, 1)}
        try:
            with open("/proc/self/status") as handle:
                for line in handle:
                    if line.startswith("VmRSS:"):
                        output["app_rss_mb"] = round(int(line.split()[1]) / 1024, 1)
        except OSError:
            pass
        if http is not None and hasattr(http, "summary"):
            output["http"] = http.summary()
        if browser is not None and hasattr(browser, "summary"):
            output["browser"] = browser.summary()
        return output
    # ------------------------------------------------------------- helpers
    def _candidates(self, listings: list[dict[str, Any]], harvested: list[dict[str, Any]],
                    ats_jobs: list[dict[str, Any]], cov: Any | None = None) -> tuple[list[dict[str, Any]], int]:
        """Normalise every acquisition path into one candidate per vacancy.

        Employer-owned sources are added first (public ATS boards, then career pages), so when the same
        vacancy is also found on a portal or through web search the employer's page stays canonical and
        every other sighting is kept as a source reference.
        """
        from app.services.job_sources.models import Exclusion, utc_now
        today = date.today()
        by_url: dict[str, dict[str, Any]] = {}
        by_title: dict[tuple[str, str], dict[str, Any]] = {}
        duplicates = 0
        retrieved = utc_now()

        def title_key(item: dict[str, Any]) -> tuple[str, str]:
            title = re.sub(r"\s+(?:at|@)\s+.*$", "", str(item.get("title") or ""), flags=re.I)
            return (re.sub(r"[^a-z0-9]+", " ", title.casefold()).strip(),
                    re.sub(r"[^a-z0-9]+", " ", Store._norm_company(str(item.get("employer") or ""))).strip())

        def add(item: dict[str, Any]) -> None:
            nonlocal duplicates
            key = canonicalize_url(item["url"])
            tkey = title_key(item)
            existing = by_url.get(key) or (by_title.get(tkey) if tkey[1] and tkey[0] else None)
            source = {"platform": item.get("source_platform"), "url": item["url"], "via": item.get("_via"),
                      "method": item.get("extraction_method"), "retrieved_at": retrieved,
                      "kind": item.get("discovered_via")}
            if existing:
                duplicates += 1
                if not any(s["url"] == item["url"] for s in existing["sources"]):
                    existing["sources"].append(source)
                for field in ("employer", "location", "posted_date", "raw_text", "employment_type", "deadline",
                              "salary", "education", "employer_id"):
                    if not existing.get(field) and item.get(field):
                        existing[field] = item[field]
                existing.setdefault("_report_keys", set()).update(item.get("_report_keys") or ())
                if cov is not None:
                    for report_key in item.get("_report_keys") or ():
                        report = cov.reports.get(report_key)
                        if report is not None:
                            report.duplicates += 1
                    cov.exclude({**item, "_exclusion_detail": f"merged into {existing['url'][:200]}"},
                                Exclusion.DUPLICATE, "dedup")
                return
            item["sources"] = [source]
            by_url[key] = item
            if tkey[1] and tkey[0]:
                by_title[tkey] = item

        for job in ats_jobs:
            text = str(job.get("description") or "")
            ats = str(job.get("ats") or str(job.get("source_platform") or "").split(":")[0])
            add({"title": job["title"], "url": job["url"], "employer": job.get("employer"),
                 "location": job.get("location"), "posted_date": job.get("posted_date"),
                 "employment_type": job.get("employment_type"), "remote": job.get("remote"),
                 "skills": find_skills(f"{job['title']} {text}")[:14], "raw_text": text[:8000],
                 "source_platform": job.get("source_platform"), "_via": "Company career board",
                 "discovered_via": "company career board", "source_kind": "job_listing",
                 "status_hint": "open", "employer_id": job.get("employer_id"),
                 "application_url": job.get("application_url"), "requisition_id": job.get("requisition_id"),
                 "extraction_method": f"{ats} public job-board API", "ats_ref": job.get("source_platform"),
                 "updated_date": job.get("updated_date"),
                 "date_source": "employer ATS" if job.get("posted_date") else None,
                 "_report_keys": set(job.get("_report_keys") or ()),
                 "evidence": [{"text": text[:300], "source_url": job["url"]}]})
        ordered = sorted(harvested, key=lambda link: link.get("_via") != "Company career page")
        for link in ordered:
            career = link.get("_via") == "Company career page"
            text = str(link.get("description") or link.get("context") or "")
            add({"title": link["title"], "url": link["url"],
                 "employer": link.get("employer") or infer_employer(link["url"], link["title"])[0],
                 "location": link.get("location"), "posted_date": link.get("posted_date"),
                 "deadline": link.get("deadline"), "salary": link.get("salary"),
                 "salary_currency": link.get("salary_currency"), "education": link.get("education"),
                 "employment_type": link.get("employment_type"), "remote": link.get("remote"),
                 "requisition_id": link.get("requisition_id"),
                 "skills": link.get("skills") or find_skills(f"{link['title']} {text}")[:14], "raw_text": text[:8000],
                 "source_platform": urlparse(link["url"]).hostname, "_via": link.get("_via"),
                 "discovered_via": "company career page" if career else ("public feed" if link.get("feed_id") else "index page"),
                 "date_source": link.get("date_source") or (
                     "JobPosting datePosted" if str(link.get("extraction_method") or "").startswith("schema.org") and link.get("posted_date") else
                     "career page" if career and link.get("posted_date") else
                                                            "listing text (relative date)" if link.get("posted_date") else None),
                 "employer_id": link.get("employer_id"), "source_kind": "job_listing" if career else "harvested",
                 "extraction_method": link.get("extraction_method") or ("career page link" if career else "index page link"),
                 "application_url": link["url"] if career else None,
                 "_report_keys": set(link.get("_report_keys") or ()),
                 "evidence": [{"text": text[:300], "source_url": link["url"]}]})
        for result in listings:
            title = TITLE_SUFFIX.sub("", str(result.get("title") or "")).strip()
            excerpts = " ".join(map(str, result.get("excerpts") or []))
            content = str(result.get("content") or "")
            text = f"{excerpts} {content[:5000]}"
            employer = None
            match = AT_EMPLOYER.search(title) or HIRING.search(excerpts[:200])
            if match:
                employer = match.group(1).strip(" ,.-")
            else:
                employer, _how = infer_employer(str(result.get("url") or ""), title, f"{excerpts} {content[:20000]}")
            location = LOCATION_RE.search(f"{title} {excerpts}")
            relative = parse_relative_date(text, today)
            page_date = parse_date(result.get("publish_date"))
            # A relative date in the listing text ("3 days ago") is better evidence than the search engine's page date.
            posted = relative or page_date
            date_source = "listing text (relative date)" if relative else ("search engine page date" if page_date else None)
            ats_hit = None
            from app.services.job_sources import ats_registry
            ats_hit = ats_registry.detect_url(str(result["url"]))
            add({"title": title[:200] or "Untitled role", "url": result["url"], "employer": employer,
                 "location": location.group(0) if location else None,
                 "posted_date": posted.isoformat() if posted else None,
                 "skills": find_skills(f"{title} {text}")[:14], "raw_text": text[:8000],
                 "source_platform": result.get("domain"), "_via": result.get("_via"),
                 "discovered_via": "web search", "source_kind": "job_listing",
                 "extraction_method": "search result + page fetch" if content else "search result snippet",
                 "date_source": date_source,
                 "ats_ref": f"{ats_hit[0].key}:{ats_hit[1]}" if ats_hit else None,
                 "_report_keys": set(result.get("_report_keys") or ()),
                 "_content": content, "evidence": result.get("evidence") or []})
        return list(by_url.values()), duplicates

    async def _llm_enrich(self, items: list[dict[str, Any]]) -> None:
        """Bounded local-model extraction for a few fetched detail pages (fills gaps only)."""
        if not items:
            return
        from app.services.discovery import DiscoveryEngine
        engine = DiscoveryEngine(self.settings, self.store, provider=self._provider,
                                 retriever=object(), preferences=self.preferences)
        sources = [{"title": item["title"], "url": item["url"], "content": item.get("_content"),
                    "source_kind": "job_listing"} for item in items]
        try:
            records = await engine._extract("jobs", "", sources, max_sources=4)
        except Exception:
            return
        by_url = {canonicalize_url(item["url"]): item for item in items}
        for record in records:
            item = by_url.get(canonicalize_url(str(record.get("_source_url") or "")))
            if not item:
                continue
            for field in ("employer", "location", "experience", "employment_type", "salary", "deadline"):
                if record.get(field) and not item.get(field):
                    item[field] = record[field]
            if record.get("posted_date") and not item.get("posted_date"):
                item["posted_date"] = record["posted_date"]
                item["date_source"] = "model-extracted from page text"
            if record.get("status") in {"open", "closed", "expired"}:
                item["status_hint"] = record["status"]
            item["skills"] = list(dict.fromkeys((item.get("skills") or []) + (record.get("skills") or [])))[:16]

    @staticmethod
    def _record(item: dict[str, Any]) -> dict[str, Any]:
        status = item.get("status_hint") or "unverified"
        deadline = parse_date(item.get("deadline"))
        if deadline and deadline < date.today():
            status = "expired"
        return {
            "url": item["url"], "original_url": item["url"], "canonical_url": canonicalize_url(item["url"]),
            "title": item["title"], "employer": item.get("employer"), "location": item.get("location"),
            "remote": item.get("remote"), "employment_type": item.get("employment_type"),
            "experience": item.get("experience"), "skills": item.get("skills") or [],
            "salary": item.get("salary"), "posted_date": item.get("posted_date"),
            "deadline": item.get("deadline"), "status": status,
            "source_platform": item.get("source_platform"),
            "match_score": item.get("match_score"), "match_reason": item.get("match_reason"),
            "best_resume_id": item.get("best_resume_id"), "best_resume_label": item.get("best_resume_label"),
            "resume_scores": item.get("resume_scores"), "eligibility": item.get("eligibility"),
            "sources": item.get("sources"), "discovered_via": item.get("discovered_via"),
            "evidence": item.get("evidence") or [],
            "raw": {"source_kind": item.get("source_kind") or "job_listing",
                    "raw_text": str(item.get("raw_text") or "")[:8000]},
            "requisition_id": item.get("requisition_id") or (item.get("eligibility") or {}).get("requisition_id"),
            "employer_id": item.get("employer_id"), "application_url": item.get("application_url"),
            # Only a listing read from the employer's own job board counts as verified open.
            "last_verified": Store.now() if item.get("discovered_via") == "company career board" else None,
            "status_evidence": ("Listed on the employer's public job board" if item.get("discovered_via") ==
                                "company career board" else None),
            "extraction_method": item.get("extraction_method"),
            "posted_date_source": item.get("date_source") if item.get("posted_date") else None,
            "updated_date": item.get("updated_date"),
            "evidence_confidence": (item.get("eligibility") or {}).get("confidence"),
            "ats_ref": item.get("ats_ref"), "salary_currency": item.get("salary_currency"),
            "education": item.get("education"),
            "verification_source": ("employer public job board" if item.get("discovered_via") == "company career board"
                                    else "employer career page (not re-checked)" if item.get("discovered_via") ==
                                    "company career page" else None),
            "employer_url": item["url"] if item.get("discovered_via") in {"company career board", "company career page"}
            else None,
        }


def rescore_stored(store: Store, preferences: dict[str, Any]) -> int:
    """Re-rank every stored listing against the active resume and current preferences."""
    resumes = store.resumes()
    updates = []
    for job in store.jobs(limit=5000):
        kind = (job.get("raw") or {}).get("source_kind")
        result = active_resume_match({**job, "raw_text": (job.get("raw") or {}).get("raw_text") or ""},
                                     preferences, resumes)
        if kind in {"search_page", "index_page"}:
            result["match_reason"] = "Search result only; open the original listing to verify details. " \
                + (result.get("match_reason") or "")
        updates.append({"id": job["id"], **result})
    store.update_job_matches(updates)
    return len(updates)
