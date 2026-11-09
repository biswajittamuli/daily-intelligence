"""v3.3 acquisition: safe fetching, robots, structured extraction, ATS registry, portals, career discovery."""
from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import httpx

from app.services.job_sources import ats_registry, portals, structured
from app.services.job_sources.career_discovery import CareerDiscovery, career_candidates, due, next_retry
from app.services.job_sources.models import SourceState
from app.services.job_sources.robots import RobotsPolicy
from app.services.job_sources.safe_http import SafeFetcher
from tests.fixtures.career_sites import JOB_LD, serve_sites

LOCAL = frozenset({"127.0.0.1"})


def browser_available() -> bool:
    try:
        import playwright  # noqa: F401
    except ImportError:
        return False
    return bool(shutil.which("google-chrome") or shutil.which("chromium") or
                Path(os.path.expanduser("~/.cache/ms-playwright")).exists())


class RecordingBrowser:
    """Wraps the real renderer and records which URLs were rendered."""

    def __init__(self, inner):
        self.inner, self.rendered = inner, []

    async def render(self, url, **kwargs):
        self.rendered.append(url)
        return await self.inner.render(url, **kwargs)


async def discover(origin: str, name: str, *, browser=None, search=None, timeout_ms=6000):
    from app.services.job_sources.browser import BrowserRenderer
    async with SafeFetcher(allow_private_hosts=LOCAL, per_host_interval=0, timeout=5) as http:
        renderer = None
        if browser:
            renderer = BrowserRenderer(allow_private_hosts=LOCAL, timeout_ms=timeout_ms, settle_ms=800)
            recording = RecordingBrowser(renderer)
        try:
            result = await CareerDiscovery(http, browser=recording if browser else None, search=search).run(name, origin)
        finally:
            if renderer:
                await renderer.close()
        return result, (recording.rendered if browser else []), (renderer.summary() if renderer else None)


class RobotsTests(unittest.TestCase):
    def test_wildcards_longest_match_and_crawl_delay(self):
        policy = RobotsPolicy("User-agent: *\nDisallow: /jobs/*?ref=\nAllow: /jobs/\nDisallow: /private$\n"
                              "Crawl-delay: 3\nSitemap: https://x.test/s.xml", status=200)
        self.assertTrue(policy.allowed("https://x.test/jobs/123"))
        self.assertFalse(policy.allowed("https://x.test/jobs/123?ref=abc"))
        self.assertFalse(policy.allowed("https://x.test/private"))
        self.assertTrue(policy.allowed("https://x.test/private/page"))
        self.assertEqual(policy.crawl_delay(), 3.0)
        self.assertEqual(policy.sitemaps, ["https://x.test/s.xml"])

    def test_missing_robots_allows_and_server_error_disallows(self):
        self.assertTrue(RobotsPolicy("", status=404).allowed("https://x.test/a"))
        self.assertFalse(RobotsPolicy("", status=503).allowed("https://x.test/a"))


class SafeFetcherTests(unittest.TestCase):
    def test_blocks_private_and_loopback_destinations(self):
        async def run():
            async with SafeFetcher() as http:
                return [await http.get(url) for url in ("http://127.0.0.1/", "http://localhost:8080/",
                                                        "http://10.0.0.1/", "file:///etc/passwd", "http://[::1]/")]
        for result in asyncio.run(run()):
            self.assertEqual(result.state, SourceState.UNSUPPORTED)
            self.assertIn("unsafe", result.error)

    def test_redirect_to_private_address_is_refused(self):
        def handler(request):
            if request.url.path == "/robots.txt":
                return httpx.Response(404)
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data"})

        async def run():
            async with SafeFetcher(transport=httpx.MockTransport(handler), allow_private_hosts={"public.test"}) as http:
                return await http.get("http://public.test/start")
        result = asyncio.run(run())
        self.assertEqual(result.state, SourceState.UNSUPPORTED)
        self.assertIn("redirect", result.error)

    def test_status_classification_bot_challenge_size_cap_and_robots(self):
        def handler(request):
            path = request.url.path
            if path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nDisallow: /secret")
            if path == "/denied":
                return httpx.Response(403, text="<title>Forbidden</title>")
            if path == "/challenge":
                return httpx.Response(503, text="<title>Just a moment...</title><div id='cf-chl-widget'></div>")
            if path == "/limited":
                return httpx.Response(429, text="slow down")
            if path == "/big":
                return httpx.Response(200, text="x" * 50_000, headers={"content-type": "text/html"})
            if path == "/pdf":
                return httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"})
            return httpx.Response(404)

        async def run():
            async with SafeFetcher(transport=httpx.MockTransport(handler), allow_private_hosts={"site.test"},
                                   max_bytes=10_000, per_host_interval=0, retries=0) as http:
                return {p: await http.get(f"http://site.test{p}") for p in
                        ("/denied", "/challenge", "/limited", "/big", "/pdf", "/secret", "/gone")}
        r = asyncio.run(run())
        self.assertEqual(r["/denied"].state, SourceState.ACCESS_DENIED)
        self.assertEqual(r["/challenge"].state, SourceState.BOT_CHALLENGE)
        self.assertEqual(r["/limited"].state, SourceState.RATE_LIMITED)
        self.assertTrue(r["/big"].truncated)
        self.assertLessEqual(len(r["/big"].text), 10_000)
        self.assertEqual(r["/pdf"].state, SourceState.UNSUPPORTED)
        self.assertEqual(r["/secret"].state, SourceState.ROBOTS_DISALLOWED)
        self.assertEqual(r["/gone"].state, SourceState.NOT_FOUND)

    def test_disk_cache_revalidates_with_etag(self):
        calls = []

        def handler(request):
            if request.url.path == "/robots.txt":
                return httpx.Response(404)
            calls.append(request.headers.get("if-none-match"))
            if request.headers.get("if-none-match") == '"v1"':
                return httpx.Response(304)
            return httpx.Response(200, text="<p>hello</p>", headers={"etag": '"v1"', "content-type": "text/html"})

        with tempfile.TemporaryDirectory() as tmp:
            async def run():
                cache = Path(tmp) / "cache.sqlite3"
                async with SafeFetcher(transport=httpx.MockTransport(handler), allow_private_hosts={"c.test"},
                                       cache_path=cache, cache_ttl=0, per_host_interval=0) as http:
                    first = await http.get("http://c.test/page")
                    second = await http.get("http://c.test/page")
                return first, second
            first, second = asyncio.run(run())
        self.assertEqual(first.text, second.text)
        self.assertTrue(second.not_modified)
        self.assertEqual(calls, [None, '"v1"'])


class StructuredTests(unittest.TestCase):
    def test_jobposting_jsonld_maps_to_canonical_fields(self):
        html = f"<html><head><script type='application/ld+json'>{JOB_LD}</script></head><body></body></html>"
        jobs = structured.job_postings(html, "https://jsnav.test/join-us")
        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(job["title"], "AI Engineer")
        self.assertEqual(job["employer"], "JsNav Labs")
        self.assertEqual(job["posted_date"], "2026-11-01")
        self.assertEqual(job["deadline"], "2026-12-31")
        self.assertEqual(job["salary_currency"], "INR")
        self.assertIn("800000", job["salary"])
        self.assertEqual(job["education"], "bachelor degree")
        self.assertEqual(job["requisition_id"], "JN-42")
        self.assertIn("Bengaluru", job["location"])
        self.assertIn("PyTorch", job["description"])

    def test_jobs_from_json_ignores_navigation_menus(self):
        nav = {"menu": [{"title": "Products", "url": "/products"}, {"title": "Careers", "url": "/careers"}]}
        self.assertEqual(structured.jobs_from_json(nav, "https://x.test"), [])
        jobs = structured.jobs_from_json({"jobs": [{"title": "Data Engineer", "location": "Pune", "department": "D",
                                                    "id": 7}]}, "https://x.test/careers")
        self.assertEqual(jobs[0]["title"], "Data Engineer")
        self.assertTrue(jobs[0]["url_is_synthetic"])

    def test_sitemap_parsing_is_safe(self):
        pages, nested = structured.sitemap_locations(
            "<?xml version='1.0'?><!DOCTYPE x [<!ENTITY e SYSTEM 'file:///etc/passwd'>]>"
            "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'><url><loc>https://a.test/careers</loc></url>"
            "<url><loc>&e;</loc></url></urlset>")
        self.assertEqual(pages, ["https://a.test/careers"])
        self.assertEqual(nested, [])

    def test_career_link_scoring_prefers_real_career_pages(self):
        links = [{"url": "https://co.test/blog/careers-advice", "text": "Careers advice", "region": "main"},
                 {"url": "https://co.test/careers", "text": "Careers", "region": "footer"},
                 {"url": "https://www.linkedin.com/company/co/jobs", "text": "Jobs", "region": "footer"},
                 {"url": "https://jobs.lever.co/co", "text": "Open roles", "region": "nav"},
                 {"url": "https://other.test/careers", "text": "Careers", "region": "footer"}]
        urls = [c["url"] for c in career_candidates(links, "https://co.test/")]
        self.assertEqual(urls[0], "https://jobs.lever.co/co")
        self.assertIn("https://co.test/careers", urls)
        self.assertNotIn("https://www.linkedin.com/company/co/jobs", urls)
        self.assertNotIn("https://other.test/careers", urls)
        self.assertNotIn("https://co.test/blog/careers-advice", urls)


class RegistryAndPolicyTests(unittest.TestCase):
    def test_ats_detection(self):
        cases = {"https://job-boards.greenhouse.io/acme/jobs/123": ("greenhouse", "acme"),
                 "https://boards.greenhouse.io/embed/job_board?for=acme": ("greenhouse", "acme"),
                 "https://jobs.lever.co/acme/1d2c3b4a-0000-1111-2222-333344445555": ("lever", "acme"),
                 "https://jobs.ashbyhq.com/acme": ("ashby", "acme"),
                 "https://apply.workable.com/acme/j/ABC123/": ("workable", "acme"),
                 "https://acme.recruitee.com/o/backend": ("recruitee", "acme"),
                 "https://acme.wd3.myworkdayjobs.com/en-US/External/job/Pune/SDE_R1": ("workday", "acme"),
                 "https://acme.zohorecruit.in/jobs/Careers": ("zoho_recruit", "acme"),
                 "https://acme.keka.com/careers/": ("keka", "acme")}
        for url, (provider, slug) in cases.items():
            hit = ats_registry.detect_url(url)
            self.assertIsNotNone(hit, url)
            self.assertEqual((hit[0].key, hit[1]), (provider, slug), url)
        self.assertIsNone(ats_registry.detect_url("https://acme.com/careers"))
        self.assertTrue(ats_registry.is_ats_listing("https://stripe.com/jobs/search?gh_jid=8172487"))
        boards = ats_registry.boards_from_urls(["https://jobs.lever.co/acme/x", "https://jobs.lever.co/ACME/y",
                                                "https://acme.zohorecruit.in/jobs/Careers"])
        self.assertEqual(boards, [{"ats": "lever", "slug": "acme", "url": "https://jobs.lever.co/acme/x"}])

    def test_portal_policies_block_linkedin_and_indeed_fetches(self):
        for url in ("https://www.linkedin.com/jobs/view/123", "https://in.indeed.com/viewjob?jk=1",
                    "https://www.naukri.com/job-listings-x-123", "https://wellfound.com/jobs/1"):
            allowed, reason = portals.may_fetch(url)
            self.assertFalse(allowed, url)
            self.assertIn("search results only", reason)
        self.assertTrue(portals.may_fetch("https://cutshort.io/job/x")[0])
        self.assertFalse(portals.may_fetch("https://cutshort.io/job/x", via="direct")[0])
        self.assertTrue(portals.may_fetch("https://careers.acme.com/jobs/1", via="direct")[0])

    def test_retry_schedule_is_bounded(self):
        from datetime import datetime, timedelta, timezone
        now = datetime(2026, 11, 9, tzinfo=timezone.utc)
        first = datetime.fromisoformat(next_retry("not_found", 1, now=now))
        many = datetime.fromisoformat(next_retry("not_found", 50, now=now))
        self.assertEqual(first - now, timedelta(days=3))
        self.assertEqual(many - now, timedelta(days=30))
        self.assertEqual(datetime.fromisoformat(next_retry("render_failed", 1, now=now)) - now, timedelta(hours=6))
        self.assertTrue(due(None))
        self.assertFalse(due({"next_retry_at": (now + timedelta(days=1)).isoformat()}, now=now))


class StaticCareerDiscoveryTests(unittest.TestCase):
    """Sites that must be solved without a browser."""

    def test_static_ats_404_blocked_and_unlinked_sites(self):
        with serve_sites(["static", "ats", "notfound", "blocked", "unlinked"]) as sites:
            async def run():
                return {name: await discover(origin, name.capitalize() + "Co") for name, (origin, _) in sites.items()}
            results = asyncio.run(run())
        static = results["static"][0]
        self.assertEqual(static["outcome"], "career_verified")
        self.assertTrue(static["career_url"].endswith("/careers"))
        self.assertEqual({j["title"] for j in static["listings"]}, {"Machine Learning Engineer", "Backend Developer"})
        self.assertEqual(static["methods"][0]["stage"], "A")

        ats = results["ats"][0]
        self.assertEqual(ats["outcome"], "ats_identified")
        self.assertEqual((ats["ats"]["provider"], ats["ats"]["slug"]), ("lever", "atsco"))

        self.assertEqual(results["notfound"][0]["outcome"], "domain_unavailable")
        self.assertEqual(results["notfound"][0]["homepage_status"], 404)
        blocked = results["blocked"][0]
        self.assertEqual(blocked["outcome"], "access_denied")
        self.assertTrue(any(m["state"] == SourceState.BOT_CHALLENGE for m in blocked["methods"]))

        unlinked = results["unlinked"][0]
        self.assertEqual(unlinked["outcome"], "career_verified")
        self.assertTrue(any(m["stage"] == "D" for m in unlinked["methods"]))
        self.assertEqual([j["title"] for j in unlinked["listings"]], ["QA Engineer"])
        for result, _, _ in results.values():
            self.assertIsNotNone(result["next_retry_at"])

    def test_no_career_page_is_never_invented(self):
        with serve_sites(["none"]) as sites:
            result, _, _ = asyncio.run(discover(sites["none"][0], "NoneCo"))
        self.assertEqual(result["outcome"], "not_found")
        self.assertIsNone(result["career_url"])
        self.assertEqual(result["listings"], [])
        stages = [m["stage"] for m in result["methods"]]
        self.assertIn("A", stages)
        self.assertIn("D", stages)

    def test_search_fallback_finds_ats_board(self):
        async def search(queries):
            return [{"url": "https://jobs.ashbyhq.com/noneco", "title": "Jobs at NoneCo", "excerpts": ["NoneCo hiring"]}]
        with serve_sites(["none"]) as sites:
            result, _, _ = asyncio.run(discover(sites["none"][0], "NoneCo", search=search))
        self.assertEqual(result["outcome"], "ats_identified")
        self.assertEqual(result["ats"]["slug"], "noneco")
        self.assertTrue(any(m["stage"] == "F" for m in result["methods"]))

    def test_search_fallback_exhausted(self):
        async def search(queries):
            return [{"url": "https://news.test/noneco-raises", "title": "NoneCo raises funds"}]
        with serve_sites(["none"]) as sites:
            result, _, _ = asyncio.run(discover(sites["none"][0], "NoneCo", search=search))
        self.assertEqual(result["outcome"], "search_exhausted")


@unittest.skipUnless(browser_available(), "Playwright + Chromium-family browser not available")
class BrowserCareerDiscoveryTests(unittest.TestCase):
    def test_javascript_sites(self):
        names = ["static", "jsnav", "menu", "react", "nextjs", "sitemap", "slow", "blocked"]
        with serve_sites(names) as sites:
            async def run():
                out = {}
                for name in names:
                    out[name] = await discover(sites[name][0], name.capitalize(), browser=True,
                                               timeout_ms=2500 if name == "slow" else 8000)
                return out
            results = asyncio.run(run())
            hits = {name: list(sites[name][1]) for name in names}

        # Static site: browser never used.
        self.assertEqual(results["static"][1], [])
        self.assertEqual(results["static"][0]["outcome"], "career_verified")
        # Test A: JS-rendered nav link discovered and verified (JSON-LD JobPosting on the careers page).
        jsnav = results["jsnav"][0]
        self.assertEqual(jsnav["outcome"], "career_verified")
        self.assertTrue(jsnav["career_url"].endswith("/join-us"))
        self.assertEqual(jsnav["listings"][0]["title"], "AI Engineer")
        self.assertEqual(jsnav["listings"][0]["extraction_method"], "schema.org JobPosting (JSON-LD)")
        self.assertTrue(results["jsnav"][1])
        # Menu: careers link revealed by the permitted menu click.
        menu = results["menu"][0]
        self.assertEqual(menu["outcome"], "career_verified")
        self.assertTrue(any("menu" in m.get("detail", "") for m in menu["methods"] if m["stage"] == "B"))
        # React: careers link in rendered DOM; career page is a JS shell reading a public JSON API.
        react = results["react"][0]
        self.assertEqual(react["outcome"], "career_verified")
        self.assertEqual({j["title"] for j in react["listings"]}, {"Frontend Engineer", "SDE Intern"})
        # Next.js: navigation found in __NEXT_DATA__ without rendering; jobs from the careers page data.
        nextjs = results["nextjs"][0]
        self.assertEqual(nextjs["outcome"], "career_verified")
        self.assertTrue(nextjs["career_url"].endswith("/company/careers"))
        self.assertEqual(nextjs["listings"][0]["title"], "Backend Engineer")
        self.assertNotIn("/", [u for u in results["nextjs"][1]])  # homepage not rendered
        # Sitemap index declared in robots.txt.
        self.assertEqual(results["sitemap"][0]["outcome"], "career_verified")
        self.assertIn("/sitemap-pages.xml", hits["sitemap"])
        # Rendering timeout reported as such.
        slow = results["slow"][0]
        self.assertEqual(slow["outcome"], "render_failed")
        self.assertTrue(any(m["state"] == SourceState.TIMEOUT for m in slow["methods"]))
        # Blocked site: no browser attempt against a bot challenge.
        self.assertEqual(results["blocked"][0]["outcome"], "access_denied")
        self.assertEqual(results["blocked"][1], [])
        # Clean shutdown, bounded concurrency.
        for name in names:
            summary = results[name][2]
            if summary and summary["launched"]:
                self.assertTrue(summary["closed_cleanly"], name)
                self.assertLessEqual(summary["peak_concurrent"], 1)

    def test_browser_blocks_private_subrequests(self):
        from app.services.job_sources.browser import BrowserRenderer
        with serve_sites(["static"]) as sites:
            origin = sites["static"][0]

            async def run():
                async with BrowserRenderer(allow_private_hosts=frozenset()) as renderer:
                    return await renderer.render(origin)
            result = asyncio.run(run())
        self.assertEqual(result.state, SourceState.UNSUPPORTED)


if __name__ == "__main__":
    unittest.main()
