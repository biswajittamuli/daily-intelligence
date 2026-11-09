"""Multi-stage career-page discovery (Part 4).

Stage A  static inspection: robots.txt sitemaps, homepage HTML anchors (header/nav/footer weighted),
         metadata, JSON-LD and ATS references in the raw HTML.
Stage B  JavaScript rendering (only when A found no career link or ATS): rendered DOM anchors,
         permitted reveal clicks (careers-labelled controls or the nav-menu toggle), public JSON the
         page loaded itself.
Stage C  embedded application data: ``__NEXT_DATA__``, JSON-LD, ``application/json`` blobs — career
         URLs and job objects inside them.
Stage D  public sitemaps (robots.txt declarations, /sitemap.xml, /sitemap_index.xml).
Verify   the best candidates are fetched (static, then rendered if the page is a JS shell): a career
         page is *verified* only with job evidence (listings, JobPosting data, an ATS board, or careers
         wording on a careers-titled page).
Stage F  search fallback through the existing search provider (``<name> careers``) when nothing was found.
Stage E  the outcome is classified precisely; every attempted method is recorded with its state.

No career URL is ever invented: every URL in the result was seen in a page, sitemap or search result.
"""
from __future__ import annotations

import asyncio
import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urljoin, urlsplit

from app.services.job_sources import ats_registry, structured
from app.services.job_sources.models import SourceState, utc_now
from app.services.job_sources.portals import portal_for
from app.services.job_sources.safe_http import SafeFetcher

OUTCOMES = {
    "career_verified": "Career page verified",
    "career_candidate": "Career page candidate found",
    "jobs_endpoint": "Public jobs endpoint found",
    "ats_identified": "ATS identified",
    "not_found": "Career page not found",
    "render_failed": "JavaScript rendering failed",
    "access_denied": "Access denied",
    "domain_unavailable": "Domain unavailable",
    "search_exhausted": "Search exhausted",
}
SUCCESS_OUTCOMES = {"career_verified", "jobs_endpoint", "ats_identified"}

PATH_TERMS = re.compile(r"(?:^|[/_.-])(careers?|jobs?|hiring|join(?:-?us|-?our-?team)?|work-?with-?us|opportunities|"
                        r"open-?positions|openings|current-?openings|vacanc(?:y|ies)|recruitment|talent|life-?at|"
                        r"we-?are-?hiring)(?:$|[/_.?#-])", re.I)
TEXT_TERMS = re.compile(r"^\s*(careers?|jobs|job openings|open (?:positions|roles)|current openings|join (?:us|our team)|"
                        r"we(?:'|’)?re hiring|we are hiring|hiring|work with us|opportunities|vacancies|recruitment|"
                        r"life at [\w ]{1,30})\s*[›→>»]?\s*$", re.I)
NEGATIVE_PATH = re.compile(r"/(blog|news|press|articles?|stories|insights|resources|events|podcast|webinars?|"
                           r"career-?advice|career-?tips|guides?)(/|$)", re.I)
CAREER_WORDING = re.compile(r"\b(open (?:positions|roles)|current openings|job openings|join our team|we(?:'|’)?re hiring|"
                            r"we are hiring|apply now|view (?:all )?(?:jobs|openings|roles)|no open (?:positions|roles)|"
                            r"no current openings|explore (?:roles|opportunities)|life at)\b", re.I)
CAREER_TITLE = re.compile(r"\b(careers?|jobs|join us|hiring|work with us|openings|opportunities)\b", re.I)


def score_link(link: dict[str, Any], base_url: str) -> int:
    url = str(link.get("url") or "")
    parts = urlsplit(url)
    host = (parts.hostname or "").casefold()
    text = f"{link.get('text') or ''} {link.get('label') or ''}".strip()
    if not url.startswith(("http://", "https://")) or portal_for(url) is not None:
        return 0
    ats = ats_registry.detect_url(url)
    same = structured.same_site(url, base_url)
    career_sub = host.split(".")[0] in {"careers", "jobs", "career", "join", "hiring", "work"}
    if not (same or ats):
        return 0
    score = 0
    if PATH_TERMS.search(parts.path or "") or career_sub:
        score += 3
    if TEXT_TERMS.match(text) or re.search(r"\b(careers?|jobs|hiring|join us|join our team|work with us)\b", text, re.I):
        score += 2
    if ats:
        score += 4
    if score and link.get("region") in {"header", "nav", "footer"}:
        score += 1
    if NEGATIVE_PATH.search(parts.path or ""):
        score -= 4
    if (parts.path or "/").count("/") > 4:
        score -= 1
    return max(score, 0)


def career_candidates(links: list[dict[str, Any]], base_url: str, *, limit: int = 6) -> list[dict[str, Any]]:
    scored = []
    for link in links:
        score = score_link(link, base_url)
        if score >= 3:
            scored.append({**link, "score": score})
    scored.sort(key=lambda item: (-item["score"], len(item["url"])))
    output, seen = [], set()
    for item in scored:
        key = item["url"].rstrip("/").casefold().split("?")[0]
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output[:limit]


def _json_strings(value: Any, budget: int = 20000) -> list[str]:
    out, stack = [], [value]
    while stack and budget > 0:
        node = stack.pop()
        budget -= 1
        if isinstance(node, str):
            if len(node) < 300 and ("/" in node):
                out.append(node)
        elif isinstance(node, dict):
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return out


def links_from_embedded(parsed: dict[str, list[Any]], base_url: str) -> list[dict[str, Any]]:
    """Career-looking URLs mentioned inside embedded app data (e.g. a Next.js navigation config)."""
    links = []
    for block in parsed.get("next_data", []) + parsed.get("app_json", []) + parsed.get("jsonld", []):
        for value in _json_strings(block):
            if not re.match(r"^(https?://|/)[^\s]*$", value):
                continue
            url = urljoin(base_url, value)
            if PATH_TERMS.search(urlsplit(url).path or "") or ats_registry.detect_url(url):
                links.append({"url": url.split("#")[0], "text": "", "label": "embedded data", "region": "main"})
    return links


def looks_js_shell(html: str) -> bool:
    """A page whose visible text is tiny relative to its scripts (client-rendered)."""
    if not html:
        return False
    text = structured.visible_text(html, 4000)
    scripts = len(re.findall(r"<script\b", html, re.I))
    return len(text) < 600 or (scripts >= 8 and len(text) < 1500) or bool(re.search(
        r"id=[\"'](?:root|app|__next|__nuxt)[\"']\s*>\s*</div>", html))


def homepage_fingerprint(links: list[dict[str, Any]], base_url: str) -> str:
    same = sorted({l["url"].split("?")[0].rstrip("/") for l in links if structured.same_site(l["url"], base_url)})
    return hashlib.sha256("\n".join(same).encode()).hexdigest()[:16]


def next_retry(outcome: str, attempts: int, *, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    attempts = max(1, attempts)
    if outcome in {"career_verified", "ats_identified", "jobs_endpoint"}:
        delay = timedelta(days=7)
    elif outcome == "career_candidate":
        delay = timedelta(days=3)
    elif outcome in {"render_failed"}:
        delay = [timedelta(hours=6), timedelta(days=1), timedelta(days=3)][min(attempts, 3) - 1]
    elif outcome == "access_denied":
        delay = timedelta(days=14)
    elif outcome == "domain_unavailable":
        delay = [timedelta(days=2), timedelta(days=7), timedelta(days=30)][min(attempts, 3) - 1]
    else:  # not_found, search_exhausted
        delay = [timedelta(days=3), timedelta(days=7), timedelta(days=14), timedelta(days=30)][min(attempts, 4) - 1]
    return (now + delay).isoformat()


def due(record: dict[str, Any] | None, *, now: datetime | None = None) -> bool:
    """Whether a stored discovery result should be re-run now."""
    if not record or not record.get("next_retry_at"):
        return True
    now = now or datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(str(record["next_retry_at"])) <= now
    except ValueError:
        return True


class CareerDiscovery:
    def __init__(self, http: SafeFetcher, *, browser: Any | None = None, search: Any | None = None,
                 firecrawl: Any | None = None, max_sitemaps: int = 4, verify_candidates: int = 2) -> None:
        self.http = http
        self.browser = browser
        self.search = search  # async callable(queries:list[str]) -> list[result dict]
        self.firecrawl = firecrawl  # async callable(url) -> {state, html, links}
        self.max_sitemaps = max_sitemaps
        self.verify_candidates = verify_candidates

    async def run(self, name: str, website: str, *, previous: dict[str, Any] | None = None,
                  allow_browser: bool = True, allow_search: bool = True) -> dict[str, Any]:
        methods: list[dict[str, Any]] = []
        result: dict[str, Any] = {"company": name, "website": website, "outcome": None, "career_url": None,
                                  "candidates": [], "ats": None, "jobs_endpoint": None, "listings": [],
                                  "methods": methods, "checked_at": utc_now(), "homepage_status": None,
                                  "attempts": int((previous or {}).get("attempts") or 0) + 1}

        def record(stage: str, method: str, state: str, detail: str = "", **extra: Any) -> None:
            methods.append({"stage": stage, "method": method, "state": state, "detail": detail[:240], **extra})

        base = website if website.startswith(("http://", "https://")) else f"https://{website}"
        links: list[dict[str, Any]] = []
        parsed_blocks: dict[str, list[Any]] = {"jsonld": [], "next_data": [], "app_json": []}
        ats_found: list[dict[str, Any]] = []
        home_html = ""
        blocked_state: str | None = None
        unavailable = False

        # ---------------- Stage A: static inspection
        robots = await self.http.robots(base)
        home = await self.http.get(base)
        result["homepage_status"] = home.status
        if home.ok:
            home_html = home.text
            base = home.final_url or base
            links = structured.page_links(base, home_html)
            parsed_blocks = structured.script_json(home_html)
            ats_found = ats_registry.detect_in_text(home_html)
            meta = structured.page_meta(base, home_html)
            result["homepage_title"] = meta.get("title")
            result["homepage_text"] = structured.visible_text(home_html, 50000)
            record("A", "static homepage", SourceState.FETCH_OK, f"{len(links)} links, HTTP {home.status}"
                   + (" (cached)" if home.from_cache else ""))
        else:
            record("A", "static homepage", home.state, home.error or "")
            if home.state in {SourceState.ACCESS_DENIED, SourceState.BOT_CHALLENGE, SourceState.AUTH_REQUIRED,
                              SourceState.RATE_LIMITED, SourceState.ROBOTS_DISALLOWED}:
                blocked_state = home.state
            elif home.state in {SourceState.NOT_FOUND, SourceState.UNSUPPORTED} or home.status is None:
                unavailable = home.status is None or home.state == SourceState.NOT_FOUND
        candidates = career_candidates(links, base)
        record("A", "anchor scan", SourceState.EXTRACT_OK if candidates or ats_found else SourceState.NO_RESULTS,
               f"{len(candidates)} career link(s), {len(ats_found)} ATS reference(s)")

        # ---------------- Stage C (static part): embedded data in the raw HTML
        embedded = career_candidates(links_from_embedded(parsed_blocks, base), base)
        embedded_jobs = []
        for block in parsed_blocks["next_data"] + parsed_blocks["app_json"]:
            embedded_jobs += structured.jobs_from_json(block, base)
        embedded_jobs += structured.job_postings(home_html, base, parsed=parsed_blocks) if home_html else []
        if home_html:
            record("C", "embedded page data (static)",
                   SourceState.EXTRACT_OK if embedded or embedded_jobs else SourceState.NO_RESULTS,
                   f"{len(parsed_blocks['next_data'])} __NEXT_DATA__, {len(parsed_blocks['jsonld'])} JSON-LD, "
                   f"{len(parsed_blocks['app_json'])} JSON blob(s); {len(embedded)} link(s), {len(embedded_jobs)} job object(s)")
        candidates = career_candidates(candidates + embedded, base)

        # ---------------- Stage B: browser rendering, only if nothing yet
        rendered_failed = False
        captured_json: list[dict[str, Any]] = []
        browser_allowed = robots.allowed(base) if home.state != SourceState.ROBOTS_DISALLOWED else False
        if not candidates and not ats_found and not embedded_jobs and allow_browser and self.browser is not None \
                and not unavailable and blocked_state is None and browser_allowed:
            render = await self.browser.render(base)
            if render.state == SourceState.FETCH_OK:
                rendered_links = render.links
                candidates = career_candidates(rendered_links + links, base)
                if render.navigated_to and structured.same_site(render.navigated_to, base):
                    candidates = career_candidates([{"url": render.navigated_to, "text": "careers (after click)",
                                                     "label": "", "region": "nav"}] + candidates, base)
                rendered_blocks = structured.script_json(render.html)
                candidates = career_candidates(candidates + links_from_embedded(rendered_blocks, base), base)
                ats_found = ats_registry.detect_in_text(render.html) or ats_found
                for block in rendered_blocks["next_data"] + rendered_blocks["app_json"]:
                    embedded_jobs += structured.jobs_from_json(block, base)
                captured_json = render.json_responses
                record("B", "browser render", SourceState.FETCH_OK,
                       f"{len(rendered_links)} rendered links; clicks: {', '.join(render.clicked) or 'none'}; "
                       f"{len(captured_json)} JSON response(s)", elapsed_ms=render.elapsed_ms)
            else:
                rendered_failed = True
                record("B", "browser render", render.state, render.error or "", elapsed_ms=render.elapsed_ms)
                if render.state in {SourceState.ACCESS_DENIED, SourceState.BOT_CHALLENGE}:
                    blocked_state = render.state
                if self.firecrawl is not None:
                    scraped = await self.firecrawl(base)
                    record("B", "Firecrawl fallback", scraped["state"], scraped.get("error") or "")
                    if scraped["state"] == SourceState.FETCH_OK:
                        rendered_failed = False
                        candidates = career_candidates(scraped["links"] + structured.page_links(base, scraped["html"]), base)
                        ats_found = ats_registry.detect_in_text(scraped["html"]) or ats_found
        elif not candidates and not ats_found and not embedded_jobs and self.firecrawl is not None \
                and not unavailable and blocked_state is None and browser_allowed:
            # No local browser: Firecrawl (when its key is saved) renders the public career page instead.
            scraped = await self.firecrawl(base)
            record("B", "Firecrawl render", scraped["state"], scraped.get("error") or "")
            if scraped["state"] == SourceState.FETCH_OK:
                candidates = career_candidates(scraped["links"] + structured.page_links(base, scraped["html"]), base)
                ats_found = ats_registry.detect_in_text(scraped["html"]) or ats_found
        elif not candidates and not ats_found and not embedded_jobs:
            reason = ("not attempted: homepage unavailable" if unavailable else
                      f"not attempted: {SourceState.LABELS.get(blocked_state, blocked_state)}" if blocked_state else
                      "not attempted: robots.txt disallows" if not browser_allowed else
                      "browser rendering disabled or unavailable")
            record("B", "browser render", SourceState.NOT_TARGETED, reason)

        # ---------------- Stage D: sitemaps (always cheap; finds unlinked career pages)
        if not candidates and not ats_found and not unavailable:
            sitemap_links = await self._sitemaps(base, robots.sitemaps)
            found = career_candidates(sitemap_links, base)
            record("D", "sitemaps", SourceState.EXTRACT_OK if found else SourceState.NO_RESULTS,
                   f"{len(sitemap_links)} URL(s) scanned, {len(found)} career candidate(s)")
            candidates = found

        # Stage D2: common career paths, fetched politely (robots.txt), only when nothing else was found.
        if not candidates and not ats_found and not embedded_jobs and not unavailable and blocked_state is None:
            probed = await self._probe_paths(base, name, record)
            if probed:
                candidates = career_candidates([{"url": probed, "text": "careers (common path)", "label": "",
                                                 "region": "probe"}], base) or \
                    [{"url": probed, "text": "careers (common path)", "region": "probe", "score": 3}]

        # Public jobs endpoint: JSON the rendered page loaded that contains job objects.
        for response in captured_json:
            jobs = structured.jobs_from_json(response["data"], base)
            if jobs and (structured.same_site(response["url"], base) or ats_registry.detect_url(response["url"])):
                result["jobs_endpoint"] = response["url"]
                embedded_jobs += [{**job, "extraction_method": "public JSON loaded by the career page"} for job in jobs]
                record("C", "public JSON endpoint", SourceState.EXTRACT_OK, f"{len(jobs)} job object(s) from {response['url'][:120]}")
                break

        # ATS links inside candidate URLs themselves.
        for candidate in candidates:
            hit = ats_registry.detect_url(candidate["url"])
            if hit and not any(a["provider"] == hit[0].key for a in ats_found):
                ats_found.append({"provider": hit[0].key, "name": hit[0].name, "slug": hit[1], "url": candidate["url"],
                                  "readable": hit[0].readable})

        # ---------------- Verify candidates
        verified_url = None
        listings: list[dict[str, Any]] = [job for job in embedded_jobs if not job.get("url_is_synthetic")] or embedded_jobs
        for candidate in [c for c in candidates if not ats_registry.detect_url(c["url"])][: self.verify_candidates]:
            outcome = await self._verify(candidate["url"], name, record, allow_browser=allow_browser)
            if outcome["ats"]:
                for item in outcome["ats"]:
                    if not any(a["provider"] == item["provider"] for a in ats_found):
                        ats_found.append(item)
            listings += outcome["listings"]
            if outcome["verified"]:
                verified_url = outcome["url"]
                break
        result["candidates"] = [{k: c.get(k) for k in ("url", "text", "region", "score")} for c in candidates]
        ats_found.sort(key=lambda a: not a["readable"])
        result["ats"] = ats_found[0] if ats_found else None
        result["ats_all"] = ats_found
        result["listings"] = _dedup_listings(listings)
        result["career_url"] = verified_url or (candidates[0]["url"] if candidates else (ats_found[0]["url"] if ats_found else None))

        # ---------------- Stage F: search fallback
        if not verified_url and not ats_found and not result["jobs_endpoint"] and allow_search and self.search is not None:
            found = await self._search_fallback(name, base, record)
            if found.get("ats"):
                result["ats"], result["ats_all"] = found["ats"], [found["ats"]]
                result["career_url"] = result["career_url"] or found["ats"]["url"]
            if found.get("career"):
                outcome = await self._verify(found["career"], name, record, allow_browser=allow_browser)
                result["listings"] = _dedup_listings(result["listings"] + outcome["listings"])
                if outcome["ats"]:
                    result["ats"] = outcome["ats"][0]
                if outcome["verified"]:
                    verified_url = outcome["url"]
                result["career_url"] = verified_url or found["career"]
                result["candidates"].append({"url": found["career"], "text": "search result", "region": "search", "score": 3})
            searched = True
        else:
            searched = False

        # ---------------- Stage E: classify
        if verified_url:
            outcome = "career_verified"
        elif result["jobs_endpoint"]:
            outcome = "jobs_endpoint"
        elif result["ats"]:
            outcome = "ats_identified"
        elif result["career_url"]:
            outcome = "career_candidate"
        elif blocked_state:
            outcome = "access_denied"
        elif unavailable:
            outcome = "domain_unavailable"
        elif rendered_failed:
            outcome = "render_failed"
        elif searched:
            outcome = "search_exhausted"
        else:
            outcome = "not_found"
        result["outcome"] = outcome
        result["outcome_label"] = OUTCOMES[outcome]
        successful = [m for m in methods if m["state"] in SourceState.SUCCESS]
        result["last_method"] = (successful[-1]["method"] if successful and outcome in SUCCESS_OUTCOMES | {"career_candidate"}
                                 else None)
        result["last_success_at"] = result["checked_at"] if outcome in SUCCESS_OUTCOMES else (previous or {}).get("last_success_at")
        result["homepage_fingerprint"] = homepage_fingerprint(links, base) if links else None
        if previous and previous.get("homepage_fingerprint") and result["homepage_fingerprint"]:
            result["homepage_changed"] = previous["homepage_fingerprint"] != result["homepage_fingerprint"]
        attempts = 1 if outcome in SUCCESS_OUTCOMES else result["attempts"]
        result["next_retry_at"] = next_retry(outcome, attempts)
        return result

    # ------------------------------------------------------------ helpers
    async def _sitemaps(self, base: str, declared: list[str]) -> list[dict[str, Any]]:
        root = f"{urlsplit(base).scheme}://{urlsplit(base).netloc}"
        queue = list(dict.fromkeys([u for u in declared if structured.same_site(u, base)][:3]
                                   + [f"{root}/sitemap.xml", f"{root}/sitemap_index.xml"]))
        seen: set[str] = set()
        urls: list[str] = []
        fetched = 0
        while queue and fetched < self.max_sitemaps:
            sitemap = queue.pop(0)
            if sitemap in seen:
                continue
            seen.add(sitemap)
            response = await self.http.get(sitemap, accept_json=True)
            fetched += 1
            if not response.ok:
                continue
            pages, nested = structured.sitemap_locations(response.text)
            urls += pages
            # Prefer nested sitemaps whose name suggests careers/jobs/pages.
            nested.sort(key=lambda u: (not re.search(r"career|job|page|main", u, re.I), len(u)))
            queue = [u for u in nested if structured.same_site(u, base)][:3] + queue
        return [{"url": u, "text": "", "label": "sitemap", "region": "sitemap"} for u in urls[:5000]]

    async def _verify(self, url: str, company: str, record, *, allow_browser: bool) -> dict[str, Any]:
        output = {"url": url, "verified": False, "listings": [], "ats": []}
        page = await self.http.get(url)
        html = page.text if page.ok else ""
        if not page.ok:
            record("verify", "career page fetch", page.state, f"{url[:120]} — {page.error or ''}")
        else:
            output = self._analyse(page.final_url or url, html, company, None, record)
            if output["verified"]:
                return output
        # Escalate to the browser only when the static page gave no job evidence and looks client-rendered.
        if (not html or looks_js_shell(html)) and allow_browser and self.browser is not None and \
                page.state not in {SourceState.ROBOTS_DISALLOWED, SourceState.NOT_FOUND, SourceState.BOT_CHALLENGE,
                                   SourceState.ACCESS_DENIED, SourceState.AUTH_REQUIRED}:
            rendered = await self.browser.render(url, reveal=False)
            if rendered.state == SourceState.FETCH_OK:
                record("verify", "career page render", SourceState.FETCH_OK, url[:120], elapsed_ms=rendered.elapsed_ms)
                return self._analyse(rendered.final_url or url, rendered.html, company, rendered, record)
            record("verify", "career page render", rendered.state, rendered.error or "")
        return output

    def _analyse(self, final: str, html: str, company: str, rendered: Any, record) -> dict[str, Any]:
        from app.services.listing_links import harvest_career_page
        parsed = structured.script_json(html)
        jobs = structured.job_postings(html, final, parsed=parsed)
        for block in parsed["next_data"] + parsed["app_json"]:
            jobs += structured.jobs_from_json(block, final)
        if rendered is not None:
            for response in rendered.json_responses:
                if structured.same_site(response["url"], final) or ats_registry.detect_url(response["url"]):
                    jobs += [{**j, "extraction_method": "public JSON loaded by the career page"}
                             for j in structured.jobs_from_json(response["data"], final)]
        for link in harvest_career_page(final, html, company):
            jobs.append({"title": link["title"], "url": link["url"], "employer": company,
                         "extraction_method": "career page link (rendered DOM)" if rendered else "career page link"})
        ats = ats_registry.detect_in_text(html)
        meta = structured.page_meta(final, html)
        text = structured.visible_text(html, 30000)
        titled = bool(CAREER_TITLE.search(f"{meta.get('title') or ''} {meta.get('og_title') or ''}") or
                      PATH_TERMS.search(urlsplit(final).path or ""))
        wording = bool(CAREER_WORDING.search(text))
        verified = bool(jobs) or bool(ats) or (titled and wording)
        record("verify", "career page check" + (" (rendered)" if rendered else " (static)"),
               SourceState.EXTRACT_OK if verified else SourceState.NO_RESULTS,
               f"{final[:120]}: {len(jobs)} listing(s), ATS {', '.join(a['name'] for a in ats) or 'none'}, "
               f"careers title {'yes' if titled else 'no'}, careers wording {'yes' if wording else 'no'}")
        return {"url": final, "verified": verified, "ats": ats,
                "listings": [{**job, "employer": job.get("employer") or company} for job in jobs]}

    COMMON_PATHS = ("/careers", "/jobs", "/join-us", "/work-with-us", "/company/careers", "/open-positions",
                    "/careers/", "/about/careers")

    async def _probe_paths(self, base: str, company: str, record) -> str | None:
        """Try well-known career paths on the company's own origin. A page counts only if it is not a
        redirect back to the homepage, not a soft 404, and reads as a careers page."""
        origin = f"{urlsplit(base).scheme}://{urlsplit(base).netloc}"
        tried = 0
        for path in self.COMMON_PATHS[:6]:
            url = origin + path
            page = await self.http.get(url)
            tried += 1
            if not page.ok:
                continue
            final_path = urlsplit(page.final_url or url).path.rstrip("/")
            if not final_path or final_path == urlsplit(base).path.rstrip("/"):
                continue  # redirected to the homepage
            text = structured.visible_text(page.text, 6000)
            if re.search(r"\b(page not found|404|doesn'?t exist|could not be found)\b", text[:1500], re.I):
                continue
            outcome = self._analyse(page.final_url or url, page.text, company, None, lambda *a, **k: None)
            if outcome["verified"]:
                record("D2", "common career paths", SourceState.EXTRACT_OK, f"{path} is a careers page")
                return page.final_url or url
        record("D2", "common career paths", SourceState.NO_RESULTS, f"{tried} path(s) tried")
        return None

    read_career_page = _verify  # public name for re-reading a known career page

    async def _search_fallback(self, name: str, base: str, record) -> dict[str, Any]:
        queries = [f"{name} careers jobs", f"{name} jobs " + " OR ".join(f"site:{d}" for d in
                                                                        ("jobs.lever.co", "job-boards.greenhouse.io",
                                                                         "jobs.ashbyhq.com", "apply.workable.com"))]
        try:
            results = await self.search(queries)
        except Exception as exc:
            record("F", "search fallback", SourceState.UNAVAILABLE, f"{type(exc).__name__}: {str(exc)[:120]}")
            return {}
        first = re.escape((name.split() or [""])[0])
        found: dict[str, Any] = {}
        for item in results:
            url = str(item.get("url") or "")
            title = f"{item.get('title') or ''} {' '.join(map(str, item.get('excerpts') or []))[:300]}"
            hit = ats_registry.detect_url(url)
            if hit and first and re.search(first, f"{title} {url}", re.I) and not found.get("ats"):
                found["ats"] = {"provider": hit[0].key, "name": hit[0].name, "slug": hit[1], "url": url,
                                "readable": hit[0].readable, "via": "search"}
            elif structured.same_site(url, base) and PATH_TERMS.search(urlsplit(url).path or "") and \
                    not NEGATIVE_PATH.search(urlsplit(url).path or "") and not found.get("career"):
                found["career"] = url
        record("F", "search fallback", SourceState.SEARCH_OK if results else SourceState.NO_RESULTS,
               f"{len(results)} result(s); career {'found' if found.get('career') else 'none'}, "
               f"ATS {'found' if found.get('ats') else 'none'}")
        return found


def _dedup_listings(listings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen, output = set(), []
    for job in listings:
        key = (str(job.get("url") or "").rstrip("/").casefold(), str(job.get("title") or "").casefold())
        if key in seen:
            continue
        seen.add(key)
        output.append(job)
    return output[:200]


async def discover_many(companies: list[dict[str, Any]], discovery: CareerDiscovery, *, concurrency: int = 3,
                        cancel=None, progress=None) -> list[dict[str, Any]]:
    """Run discovery for several companies (static work in parallel; the browser has its own page limit)."""
    semaphore = asyncio.Semaphore(max(1, concurrency))
    results: list[dict[str, Any] | None] = [None] * len(companies)

    async def one(index: int, company: dict[str, Any]) -> None:
        async with semaphore:
            if cancel:
                cancel()
            if progress:
                progress(f"Career discovery: {company['name']} ({company['website']})")
            try:
                results[index] = await discovery.run(company["name"], company["website"],
                                                      previous=company.get("career_discovery"),
                                                      allow_browser=company.get("allow_browser", True),
                                                      allow_search=company.get("allow_search", True))
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # one company never fails the batch
                results[index] = {"company": company["name"], "website": company["website"], "outcome": "not_found",
                                  "outcome_label": OUTCOMES["not_found"], "methods": [
                                      {"stage": "-", "method": "discovery", "state": SourceState.EXTRACT_FAILED,
                                       "detail": f"{type(exc).__name__}: {str(exc)[:160]}"}],
                                  "listings": [], "candidates": [], "ats": None, "checked_at": utc_now(),
                                  "next_retry_at": next_retry("not_found", 1), "attempts": 1}

    await asyncio.gather(*(one(i, c) for i, c in enumerate(companies)))
    return [r for r in results if r is not None]
