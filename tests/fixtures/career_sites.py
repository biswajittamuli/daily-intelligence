"""Local fixture websites for career-discovery tests (each site is its own origin on 127.0.0.1).

Every site is a dict of path -> (status, content type, body[, delay seconds]).
"""
from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HTML = "text/html; charset=utf-8"


def page(title: str, body: str, head: str = "") -> str:
    return f"<!doctype html><html><head><title>{title}</title>{head}</head><body>{body}</body></html>"


JOB_LD = json.dumps({"@context": "https://schema.org", "@type": "JobPosting", "title": "AI Engineer",
                     "hiringOrganization": {"@type": "Organization", "name": "JsNav Labs"},
                     "datePosted": "2026-11-01", "validThrough": "2026-12-31", "employmentType": "FULL_TIME",
                     "jobLocation": {"@type": "Place", "address": {"addressLocality": "Bengaluru", "addressCountry": "IN"}},
                     "baseSalary": {"@type": "MonetaryAmount", "currency": "INR",
                                    "value": {"@type": "QuantitativeValue", "minValue": 800000, "maxValue": 1200000, "unitText": "YEAR"}},
                     "educationRequirements": {"@type": "EducationalOccupationalCredential", "credentialCategory": "bachelor degree"},
                     "description": "<p>Build LLM agents with Python and PyTorch.</p>", "identifier": {"value": "JN-42"}})

SITES: dict[str, dict[str, tuple]] = {
    # 1. static homepage with a footer careers link
    "static": {
        "/": (200, HTML, page("StaticCo — data tools", "<header><a href='/about'>About</a></header><main>Hello</main>"
                                                        "<footer><a href='/careers'>Careers</a></footer>")),
        "/careers": (200, HTML, page("Careers at StaticCo", "<h1>Open positions</h1>"
                                     "<a href='/careers/jobs/ml-engineer-1234'>Machine Learning Engineer</a>"
                                     "<a href='/careers/jobs/backend-developer-5678'>Backend Developer</a>")),
    },
    # 2. JavaScript-rendered navigation; careers page has JSON-LD JobPosting
    "jsnav": {
        "/": (200, HTML, page("JsNav Labs", "<div id='root'></div><script>document.getElementById('root').innerHTML="
                              "\"<nav><a href='/'>Home</a><a href='/join-us'>Join us</a></nav><p>We build things.</p>\";</script>")),
        "/join-us": (200, HTML, page("Join us — JsNav Labs", "<h1>Join our team</h1><p>Apply now.</p>",
                                     f"<script type='application/ld+json'>{JOB_LD}</script>")),
    },
    # 3. careers link only appears after opening the navigation menu
    "menu": {
        "/": (200, HTML, page("MenuCo", "<header><button aria-expanded='false' aria-label='Open menu' id='m'>☰ Menu</button>"
                              "<div id='drawer'></div></header><main>Products</main><script>"
                              "document.getElementById('m').addEventListener('click',()=>{document.getElementById('drawer')"
                              ".innerHTML=\"<a href='/about'>About</a><a href='/careers'>Careers</a>\";});</script>")),
        "/careers": (200, HTML, page("Careers | MenuCo", "<h1>Careers</h1><p>Current openings</p>"
                                     "<a href='/careers/data-scientist'>Data Scientist</a>")),
    },
    # 4. React app: careers link in rendered DOM; careers page is a JS shell that loads a public JSON API
    "react": {
        "/": (200, HTML, page("ReactCo", "<div id='root'></div><script>setTimeout(()=>{document.getElementById('root')"
                              ".innerHTML=\"<header><a href='/products'>Products</a></header><footer><a href='/careers'>We're hiring</a></footer>\";},150);</script>")),
        "/careers": (200, HTML, page("Careers — ReactCo", "<div id='root'></div><script>fetch('/api/jobs.json').then(r=>r.json())"
                                     ".then(d=>{document.getElementById('root').innerHTML='<h1>Careers</h1>'+d.jobs.map(j=>"
                                     "'<div>'+j.title+'</div>').join('');});</script>")),
        "/api/jobs.json": (200, "application/json", json.dumps({"jobs": [
            {"id": "r-1", "title": "Frontend Engineer", "location": "Pune", "department": "Web", "url": "/careers/r-1"},
            {"id": "r-2", "title": "SDE Intern", "location": "Remote", "department": "Eng", "url": "/careers/r-2"}]})),
    },
    # 5. Next.js: nav lives in __NEXT_DATA__, careers page lists jobs in __NEXT_DATA__
    "nextjs": {
        "/": (200, HTML, page("NextCo", "<div id='__next'></div><script id='__NEXT_DATA__' type='application/json'>"
                              + json.dumps({"props": {"pageProps": {"nav": [{"label": "Company", "href": "/company"},
                                                                             {"label": "Careers", "href": "/company/careers"}]}}})
                              + "</script>")),
        "/company/careers": (200, HTML, page("Careers at NextCo", "<div id='__next'></div><script id='__NEXT_DATA__' type='application/json'>"
                                             + json.dumps({"props": {"pageProps": {"jobs": [
                                                 {"id": "be-1", "title": "Backend Engineer", "location": "Bengaluru",
                                                  "department": "Platform", "url": "/company/careers/be-1"}]}}}) + "</script>")),
    },
    # 6. careers page only discoverable through a sitemap index declared in robots.txt
    "sitemap": {
        "/": (200, HTML, page("SiteMapCo", "<main>Nothing linked here</main>")),
        "/robots.txt": (200, "text/plain", "User-agent: *\nDisallow: /private/\nSitemap: {origin}/sitemap_index.xml\n"),
        "/sitemap_index.xml": (200, "application/xml", "<sitemapindex xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
                                                       "<sitemap><loc>{origin}/sitemap-pages.xml</loc></sitemap></sitemapindex>"),
        "/sitemap-pages.xml": (200, "application/xml", "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
                                                       "<url><loc>{origin}/about</loc></url><url><loc>{origin}/work-with-us</loc></url></urlset>"),
        "/work-with-us": (200, HTML, page("Work with us — SiteMapCo", "<h1>Work with us</h1><p>Join our team. We are hiring engineers.</p>")),
    },
    # 7. homepage links straight to a public ATS board
    "ats": {
        "/": (200, HTML, page("AtsCo", "<nav><a href='https://jobs.lever.co/atsco'>Careers</a></nav>")),
    },
    # 8. no career page anywhere
    "none": {
        "/": (200, HTML, page("NoneCo", "<nav><a href='/about'>About</a><a href='/blog'>Blog</a></nav><p>"
                              + "We sell hardware. " * 60 + "</p>")),
    },
    # 9. homepage 404
    "notfound": {},
    # 10. homepage whose parser-blocking script never arrives in time (browser timeout)
    "slow": {
        "/": (200, HTML, page("SlowCo", "<div id='root'></div><script src='/app.js'></script>")),
        "/app.js": (200, "application/javascript", "document.body.innerHTML='<a href=/careers>Careers</a>';", 8),
    },
    # 11. bot challenge
    "blocked": {
        "/": (403, HTML, page("Attention Required! | Cloudflare", "<div class='cf-chl-widget'>Verify you are human</div>")),
    },
    # 12. public careers page with no homepage link, listed in the default /sitemap.xml
    "unlinked": {
        "/": (200, HTML, page("UnlinkedCo", "<nav><a href='/about'>About</a></nav><p>" + "Enterprise software. " * 60 + "</p>")),
        "/sitemap.xml": (200, "application/xml", "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
                                                 "<url><loc>{origin}/about</loc></url><url><loc>{origin}/careers</loc></url></urlset>"),
        "/careers": (200, HTML, page("Careers - UnlinkedCo", "<h1>Careers</h1><a href='/careers/jobs/qa-engineer-2001'>QA Engineer</a>")),
    },
}


class _Handler(BaseHTTPRequestHandler):
    routes: dict[str, tuple] = {}
    hits: list[str] = []

    def log_message(self, *args):  # silence
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        self.hits.append(path)
        route = self.routes.get(path)
        if route is None:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"not found")
            return
        status, ctype, body, *rest = route
        if rest:
            time.sleep(rest[0])
        origin = f"http://{self.headers.get('Host')}"
        data = body.replace("{origin}", origin).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except BrokenPipeError:
            pass


@contextmanager
def serve_sites(names: list[str] | None = None):
    """Start one loopback server per site; yields {name: (origin, hits list)}."""
    servers, output = [], {}
    for name in names or list(SITES):
        handler = type(f"H_{name}", (_Handler,), {"routes": SITES[name], "hits": []})
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        output[name] = (f"http://127.0.0.1:{server.server_address[1]}", handler.hits)
    try:
        yield output
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
