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

ROLE_VARIANTS: dict[str, list[str]] = {
    "ai engineer": ["AI Engineer", "Machine Learning Engineer", "Applied AI Engineer", "LLM Engineer",
                    "GenAI Engineer"],
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


def role_variants(targets: list[str], limit: int = 8) -> list[str]:
    output: list[str] = []
    for target in targets:
        key = " ".join(str(target).split()).casefold()
        for variant in ROLE_VARIANTS.get(key, [str(target).strip()]):
            if variant and variant.casefold() not in {item.casefold() for item in output}:
                output.append(variant)
    return output[:limit]


class BroadJobSearch:
    def __init__(self, settings: Settings, store: Store, preferences: dict[str, Any], *,
                 retriever: Any | None = None, provider: Any | None = None,
                 ats_fetcher: Callable[..., Any] | None = None) -> None:
        self.settings = settings
        self.store = store
        self.preferences = preferences
        self._retriever = retriever
        self._provider = provider
        self._ats_fetcher = ats_fetcher or fetch_company_jobs

    # ------------------------------------------------------------------ plan
    def plan(self, request: str, pool_size: int) -> dict[str, Any]:
        jobs = self.preferences.get("jobs", {})
        active = self.store.profile()
        profile = (active or {}).get("profile") or {}
        request_role = " ".join(request.split())[:80]
        targets = ([request_role] if request_role else []) + list(jobs.get("roles") or [])
        if profile:
            targets += infer_job_titles(profile)
        if not targets:
            targets = list(jobs.get("scan_roles") or ["Software Engineer"])
        variants = role_variants(targets)
        locations = [item for item in jobs.get("locations") or [] if str(item).strip()][:2]
        location = " ".join(locations) or "India"
        experience = str(jobs.get("experience") or "any")
        level = {"fresher": "fresher entry level", "internship": "internship",
                 "0-1 years": "entry level"}.get(experience, "")
        month = date.today().strftime("%B %Y")
        # Only titles and up to 3 generic skill keywords are sent externally.
        skills = [skill for skill in (profile.get("skills") or jobs.get("skills") or [])
                  if len(str(skill)) <= 20][:3]
        portals = [domain for domain in portal_domains(self.preferences) if domain]
        search_calls = {50: 3, 100: 6, 200: 10}.get(pool_size, max(2, min(12, math.ceil(pool_size / 20))))
        batches: list[dict[str, Any]] = []
        # 1) portal site: queries, rotated across role variants
        for index, domain in enumerate(portals):
            role = variants[index % len(variants)] if variants else "software engineer"
            batches.append({"platform": _platform(domain), "method": "MCP site search",
                            "queries": [f"site:{domain} {role} {location}",
                                        f"site:{domain} {variants[(index + 1) % len(variants)] if variants else role} {level}".strip()]})
        # 2) company career pages + unrestricted discovery, per role variant
        for role in variants:
            batches.append({"platform": "Company career pages", "method": "MCP web search",
                            "queries": [f"{role} careers apply {location} {month}",
                                        f"{role} {level} job opening {location}".strip()]})
            batches.append({"platform": "Open web", "method": "MCP web search",
                            "queries": [f"{role} jobs {location} {month}",
                                        f"{role} {' '.join(skills)} hiring {location}".strip()]})
        ordered = self._interleave(batches)[:search_calls]
        return {"targets": targets, "variants": variants, "location": location,
                "search_calls": len(ordered), "batches": ordered, "pool_size": pool_size,
                "resume": (active or {}).get("label"), "portals": portals,
                "objective": (f"Find individual, currently open job listings for {', '.join(variants[:4])} "
                              f"in {location}. Prefer original job pages with title, company, location, "
                              f"date and an apply link. Exclude articles, salary guides and hiring news.")}

    @staticmethod
    def _interleave(batches: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Alternate portal / career / open-web batches so a small budget still covers each kind."""
        groups: dict[str, list[dict[str, Any]]] = {}
        for batch in batches:
            groups.setdefault(batch["method"] + batch["platform"] if batch["method"] == "MCP site search"
                              else batch["platform"], []).append(batch)
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
        progress = progress or (lambda _: None)
        started = time.perf_counter()
        pool_size = int(pool_size) if int(pool_size or 0) > 0 else 100
        pool_size = max(20, min(300, pool_size))
        plan = self.plan(request, pool_size)
        session_id = self.store.start_search_session("jobs", request or f"Broad job search ({pool_size})")
        self.store.update_search_session(session_id, plan={k: v for k, v in plan.items() if k != "batches"}
                                         | {"queries": [q for b in plan["batches"] for q in b["queries"]]})
        coverage: dict[str, dict[str, Any]] = {}
        failures: list[str] = []
        steps: list[str] = []

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

        companies = self.preferences.get("jobs", {}).get("companies") or DEFAULT_COMPANIES
        ats_task = None
        if include_ats and companies:
            note(f"Reading {len(companies)} company career boards (Greenhouse/Lever/Ashby)")
            ats_task = asyncio.create_task(self._ats_fetcher(companies, cancel=check_cancel))

        mcp_results: list[dict[str, Any]] = []
        listings: list[dict[str, Any]] = []
        index_pages: list[dict[str, Any]] = []
        articles: list[dict[str, Any]] = []
        harvested: list[dict[str, Any]] = []
        retriever = self._retriever
        owns = retriever is None
        fetched_pages = 0
        try:
            if retriever is None:
                retriever = ParallelWebRetriever(settings=replace(
                    self.settings, max_tool_calls=plan["search_calls"] + 4, max_search_queries=8,
                    max_fetch_urls=20))
                await retriever.__aenter__()
            for index, batch in enumerate(plan["batches"], 1):
                check_cancel()
                note(f"Search {index}/{plan['search_calls']}: {batch['platform']} — {batch['queries'][0]}")
                try:
                    results = await retriever.search(batch["queries"], plan["objective"],
                                                     source_guidance="Individual job listing pages",
                                                     freshness_days=30)
                except RetrievalError as exc:
                    cover(batch["platform"], batch["method"], queries=len(batch["queries"]),
                          status=f"failed: {str(exc)[:80]}")
                    failures.append(f"{batch['platform']}: {exc}")
                    if "rate" in str(exc).casefold() or "429" in str(exc):
                        note("Search provider rate limit reached; continuing with results so far")
                        break
                    continue
                cover(batch["platform"], batch["method"], queries=len(batch["queries"]), results=len(results))
                for item in results:
                    item["_via"] = batch["platform"]
                    platform = _platform(str(item.get("domain") or ""))
                    if platform != batch["platform"] and platform in PLATFORM_NAMES.values():
                        cover(platform, "found via other searches", results=1)
                mcp_results.extend(results)
                if index < plan["search_calls"]:
                    await asyncio.sleep(0.6)

            # Classify results: listings vs index pages vs articles.
            seen: set[str] = set()
            for item in mcp_results:
                url = str(item.get("url") or "")
                key = canonicalize_url(url)
                if not url or key in seen:
                    continue
                seen.add(key)
                kind = classify_source("jobs", item)
                if kind == "job_news":
                    articles.append(item)
                elif looks_like_index(url, str(item.get("title") or "")) and not is_listing_url(url):
                    index_pages.append(item)
                else:
                    listings.append(item)
            note(f"Search returned {len(mcp_results)} results: {len(listings)} listings, "
                 f"{len(index_pages)} index pages, {len(articles)} articles/news (excluded)")

            # Expand index pages into individual listings.
            fetch_budget = {50: 4, 100: 6, 200: 10}.get(pool_size, 6)
            to_fetch = index_pages[:fetch_budget]
            detail_candidates = [item for item in listings if is_listing_url(str(item.get("url")))][:4]
            fetch_urls = [item["url"] for item in to_fetch + detail_candidates][:20]
            pages: dict[str, str] = {}
            if fetch_urls:
                check_cancel()
                note(f"Fetching {len(to_fetch)} index pages and {len(detail_candidates)} listing pages")
                try:
                    fetched = await retriever.fetch(fetch_urls, plan["objective"], search_queries=plan["batches"][0]["queries"],
                                                    full_content=True)
                    for page in fetched:
                        content = str(page.get("full_content") or page.get("content") or "")
                        if content:
                            pages[canonicalize_url(str(page.get("url") or ""))] = content
                    fetched_pages = len(pages)
                except RetrievalError as exc:
                    failures.append(f"fetch: {exc}")
            for item in to_fetch:
                content = pages.get(canonicalize_url(item["url"]))
                platform = _platform(str(item.get("domain") or ""))
                if not content:
                    cover(platform, "page fetch", fetched=0, status="not retrievable (blocked or empty)")
                    continue
                links = harvest_listings(item["url"], content)
                cover(platform, "page fetch", fetched=1, listings=len(links))
                for link in links:
                    link["_via"] = platform
                harvested.extend(links)
            for item in detail_candidates:
                content = pages.get(canonicalize_url(item["url"]))
                if content:
                    item["content"] = content
                else:
                    cover(_platform(str(item.get("domain") or "")), "page fetch",
                          status="detail page not retrievable")
            if harvested:
                note(f"Expanded index pages into {len(harvested)} individual listings")
        except asyncio.CancelledError:
            if ats_task:
                ats_task.cancel()
            self.store.update_search_session(session_id, status="cancelled", error="Cancelled by user")
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

        ats_jobs: list[dict[str, Any]] = []
        if ats_task:
            try:
                ats_jobs, ats_coverage = await ats_task
                for entry in ats_coverage:
                    cover(entry["platform"], entry["method"], results=entry["results"], status=entry["status"])
                note(f"Company boards returned {len(ats_jobs)} openings from "
                     f"{sum(1 for e in ats_coverage if e['status'].startswith('ok'))} of {len(ats_coverage)} companies")
            except Exception as exc:  # never fail the whole run for one source type
                failures.append(f"company boards: {type(exc).__name__}")

        # ---------------------------------------------------------- Stage B
        check_cancel()
        candidates = self._candidates(listings, harvested, ats_jobs)
        raw_total = len(mcp_results) + len(harvested) + len(ats_jobs)
        note(f"Ranking {len(candidates)} unique candidates against "
             f"{'resume “' + plan['resume'] + '”' if plan['resume'] else 'your preferences'}")

        if use_llm:
            await self._llm_enrich([item for item in candidates if item.get("_content")][:4])

        resumes = self.store.resumes()
        today = date.today()
        ranked, excluded = [], Counter()
        for item in candidates:
            match = active_resume_match(item, self.preferences, resumes, targets=plan["variants"], today=today)
            eligibility = match["eligibility"]
            if eligibility["tier"] == "excluded":
                excluded[eligibility["excluded_reason"].split(" (")[0].split(" you have")[0]] += 1
                continue
            item.update(match)
            ranked.append(item)
        excluded["Articles / hiring news (not vacancies)"] += len(articles)
        ranked.sort(key=lambda job: (job.get("match_score") or 0, job.get("posted_date") or ""), reverse=True)
        shortlist = ranked[:pool_size]
        saved = self.store.upsert_jobs([self._record(item) for item in shortlist])
        rescore_stored(self.store, self.preferences)  # keep older listings consistent with this ranking
        tiers = Counter((item.get("eligibility") or {}).get("tier") for item in shortlist)

        summary = {
            "category": "jobs", "kind": "broad_search", "status": "complete" if saved else "empty",
            "request": request, "resume": plan["resume"], "pool_size": pool_size,
            "targets": plan["variants"], "search_calls": plan["search_calls"],
            "raw_results": raw_total, "mcp_results": len(mcp_results), "harvested": len(harvested),
            "ats_openings": len(ats_jobs), "unique_candidates": len(candidates),
            "excluded": dict(excluded), "excluded_total": sum(excluded.values()),
            "ranked": len(ranked), "stored": len(saved), "records": len(saved),
            "strong": tiers.get("strong", 0), "possible": tiers.get("possible", 0), "low": tiers.get("low", 0),
            "pages_fetched": fetched_pages, "sources_found": raw_total,
            "coverage": sorted(coverage.values(), key=lambda entry: (-entry.get("results", 0), entry["platform"])),
            "failures": failures, "steps": steps,
            "duration_seconds": round(time.perf_counter() - started, 1),
        }
        if not saved:
            summary["reason"] = "No relevant listing survived ranking; see coverage and exclusions."
        self.store.update_search_session(session_id, status=summary["status"], summary=summary)
        note(f"Stored {len(saved)} ranked listings: {summary['strong']} strong, {summary['possible']} possible")
        return summary

    # ------------------------------------------------------------- helpers
    def _candidates(self, listings: list[dict[str, Any]], harvested: list[dict[str, Any]],
                    ats_jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        today = date.today()
        by_url: dict[str, dict[str, Any]] = {}
        by_title: dict[tuple[str, str], dict[str, Any]] = {}

        def add(item: dict[str, Any]) -> None:
            key = canonicalize_url(item["url"])
            title_key = (re.sub(r"[^a-z0-9]+", " ", str(item.get("title") or "").casefold()).strip(),
                         re.sub(r"[^a-z0-9]+", " ", str(item.get("employer") or "").casefold()).strip())
            existing = by_url.get(key) or (by_title.get(title_key) if title_key[1] else None)
            source = {"platform": item.get("source_platform"), "url": item["url"], "via": item.get("_via")}
            if existing:
                existing["sources"].append(source)
                for field in ("employer", "location", "posted_date", "raw_text", "employment_type"):
                    if not existing.get(field) and item.get(field):
                        existing[field] = item[field]
                return
            item["sources"] = [source]
            by_url[key] = item
            if title_key[1]:
                by_title[title_key] = item

        for result in listings:
            title = TITLE_SUFFIX.sub("", str(result.get("title") or "")).strip()
            excerpts = " ".join(map(str, result.get("excerpts") or []))
            content = str(result.get("content") or "")
            text = f"{excerpts} {content[:5000]}"
            employer = None
            match = AT_EMPLOYER.search(title) or HIRING.search(excerpts[:200])
            if match:
                employer = match.group(1).strip(" ,.-")
            location = LOCATION_RE.search(f"{title} {excerpts}")
            posted = (parse_date(result.get("publish_date")) or parse_relative_date(text, today))
            add({"title": title[:200] or "Untitled role", "url": result["url"], "employer": employer,
                 "location": location.group(0) if location else None,
                 "posted_date": posted.isoformat() if posted else None,
                 "skills": find_skills(f"{title} {text}")[:14], "raw_text": text[:3000],
                 "source_platform": result.get("domain"), "_via": result.get("_via"),
                 "discovered_via": "web search", "source_kind": "job_listing",
                 "_content": content, "evidence": result.get("evidence") or []})
        for link in harvested:
            add({"title": link["title"], "url": link["url"], "employer": link.get("employer"),
                 "location": link.get("location"), "posted_date": link.get("posted_date"),
                 "skills": link.get("skills") or [], "raw_text": link.get("context") or "",
                 "source_platform": urlparse(link["url"]).hostname, "_via": link.get("_via"),
                 "discovered_via": "index page", "source_kind": "harvested",
                 "evidence": [{"text": link.get("context") or "", "source_url": link["url"]}]})
        for job in ats_jobs:
            text = str(job.get("description") or "")
            add({"title": job["title"], "url": job["url"], "employer": job.get("employer"),
                 "location": job.get("location"), "posted_date": job.get("posted_date"),
                 "employment_type": job.get("employment_type"), "remote": job.get("remote"),
                 "skills": find_skills(f"{job['title']} {text}")[:14], "raw_text": text[:3000],
                 "source_platform": job.get("source_platform"), "_via": "Company career board",
                 "discovered_via": "company career board", "source_kind": "job_listing",
                 "status_hint": "open", "evidence": [{"text": text[:300], "source_url": job["url"]}]})
        return list(by_url.values())

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
                    "raw_text": str(item.get("raw_text") or "")[:3000]},
            "last_verified": Store.now(),
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
