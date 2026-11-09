"""Bounded headless-browser rendering for JavaScript career pages (Playwright, system Chrome).

Used only when ordinary HTTP retrieval did not reveal what we need. Limits:
- one browser process and one reusable context per run; each render opens one page and closes it;
- at most ``max_pages`` pages at once (default 1), a hard per-page timeout, images/media/fonts blocked;
- every request the page makes is checked: non-http(s) schemes and private/loopback/link-local
  destinations are aborted (SSRF protection inside the browser);
- no cookies or storage persist between runs; no stealth plugins, no CAPTCHA solving, no login;
- clicks are limited to controls whose label says careers/jobs/hiring, or the site's navigation menu
  toggle when no careers link is otherwise visible ("permitted reveal click"), at most ``max_clicks``.

If Playwright or a Chromium-family browser is unavailable the renderer reports that state and the
caller falls back to static results.
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
import socket
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from app.services.job_sources.models import SourceState

log = logging.getLogger(__name__)

CAREER_LABEL = r"\b(careers?|jobs?|join (?:us|our team)|we(?:'|’)?re hiring|hiring|work with us|open (?:positions|roles)|vacanc(?:y|ies)|opportunit(?:y|ies)|recruitment|life at)\b"
MENU_LABEL = r"\b(menu|navigation|open nav|toggle nav|company|about)\b"

COLLECT_JS = r"""
() => {
  const region = el => { const r = el.closest('header,footer,nav,[role=navigation],[role=banner],[role=contentinfo]');
    if (!r) return 'main'; const t = r.tagName.toLowerCase(); const role = r.getAttribute('role');
    return role==='navigation'?'nav':role==='banner'?'header':role==='contentinfo'?'footer':t; };
  const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  const out = [];
  for (const a of document.querySelectorAll('a[href]')) {
    const href = a.href; if (!href || !/^https?:/.test(href)) continue;
    out.push({url: href.split('#')[0], text: (a.innerText||a.textContent||'').trim().slice(0,160),
              label: (a.getAttribute('aria-label')||a.getAttribute('title')||'').slice(0,160),
              region: region(a), visible: visible(a)});
    if (out.length > 1500) break;
  }
  return out;
}
"""

CLICKABLES_JS = r"""
([careerRe, menuRe, allowMenu]) => {
  const cr = new RegExp(careerRe, 'i'), mr = new RegExp(menuRe, 'i');
  const items = [];
  const nodes = document.querySelectorAll('button,[role=button],[aria-expanded],summary,a:not([href]),a[href="#"]');
  nodes.forEach((el, i) => {
    const label = ((el.innerText||'') + ' ' + (el.getAttribute('aria-label')||'') + ' ' + (el.getAttribute('title')||'')).trim();
    if (!label || label.length > 80) return;
    const inNav = !!el.closest('header,nav,[role=navigation],[role=banner]');
    const kind = cr.test(label) ? 'career' : (allowMenu && inNav && mr.test(label)) ? 'menu' : null;
    if (!kind) return;
    el.setAttribute('data-di-click', String(i));
    items.push({id: String(i), label: label.slice(0,80), kind});
  });
  return items.slice(0, 8);
}
"""


@dataclass
class RenderResult:
    url: str
    final_url: str | None = None
    state: str = SourceState.UNAVAILABLE
    html: str = ""
    links: list[dict[str, Any]] = field(default_factory=list)
    json_responses: list[dict[str, Any]] = field(default_factory=list)
    clicked: list[str] = field(default_factory=list)
    navigated_to: str | None = None
    error: str | None = None
    elapsed_ms: int = 0
    blocked_requests: int = 0


def _child_rss_mb() -> float | None:
    """Resident memory of this process's descendant processes (the browser), from /proc."""
    try:
        me = os.getpid()
        parents: dict[int, int] = {}
        rss: dict[int, int] = {}
        page = os.sysconf("SC_PAGE_SIZE")
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            try:
                with open(f"/proc/{entry}/stat") as handle:
                    fields = handle.read().rsplit(")", 1)[1].split()
                parents[int(entry)] = int(fields[1])
                rss[int(entry)] = int(fields[21]) * page
            except (OSError, IndexError, ValueError):
                continue
        total = 0
        for pid in parents:
            node, depth = pid, 0
            while node in parents and depth < 12:
                node = parents[node]
                depth += 1
                if node == me:
                    total += rss.get(pid, 0)
                    break
        return round(total / 1_048_576, 1)
    except OSError:
        return None


class BrowserRenderer:
    def __init__(self, *, max_pages: int = 1, timeout_ms: int = 15000, settle_ms: int = 2500, max_clicks: int = 2,
                 max_json_responses: int = 12, max_json_bytes: int = 1_000_000,
                 allow_private_hosts: frozenset[str] | set[str] = frozenset(), channel: str | None = None,
                 enabled: bool = True) -> None:
        self.max_pages = max(1, min(max_pages, 3))
        self.timeout_ms = timeout_ms
        self.settle_ms = settle_ms
        self.max_clicks = max_clicks
        self.max_json_responses = max_json_responses
        self.max_json_bytes = max_json_bytes
        self.allow_private_hosts = frozenset(h.casefold() for h in allow_private_hosts)
        self.channel = channel
        self.enabled = enabled
        self._pw = None
        self._browser = None
        self._context = None
        self._launch_lock = asyncio.Lock()
        self._slots = asyncio.Semaphore(self.max_pages)
        self._active = 0
        self._host_ok: dict[str, bool] = {}
        self.unavailable_reason: str | None = None
        self.stats: dict[str, Any] = {"launched": False, "pages_opened": 0, "pages_closed": 0, "peak_concurrent": 0,
                                      "render_ms": [], "peak_browser_rss_mb": None, "closed_cleanly": None,
                                      "blocked_requests": 0, "engine": None}

    async def __aenter__(self) -> "BrowserRenderer":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    # ---------------------------------------------------------- lifecycle
    async def _ensure(self) -> bool:
        if not self.enabled:
            self.unavailable_reason = "browser rendering disabled in settings"
            return False
        if self._context is not None:
            return True
        if self.unavailable_reason:
            return False
        async with self._launch_lock:
            if self._context is not None:
                return True
            try:
                from playwright.async_api import async_playwright
            except ImportError:
                self.unavailable_reason = "Playwright is not installed"
                return False
            try:
                self._pw = await async_playwright().start()
                args = ["--disable-dev-shm-usage", "--disable-extensions", "--no-first-run", "--disable-gpu",
                        "--renderer-process-limit=2", "--js-flags=--max-old-space-size=256"]
                errors = []
                for channel in ([self.channel] if self.channel else ["chrome", None]):
                    try:
                        self._browser = await self._pw.chromium.launch(channel=channel, headless=True, args=args)
                        self.stats["engine"] = channel or "playwright chromium"
                        break
                    except Exception as exc:  # channel missing -> try the next one
                        errors.append(f"{channel or 'chromium'}: {str(exc).splitlines()[0][:120]}")
                if self._browser is None:
                    self.unavailable_reason = "no Chromium-family browser available (" + "; ".join(errors) + ")"
                    await self._pw.stop()
                    self._pw = None
                    return False
                self._context = await self._browser.new_context(
                    java_script_enabled=True, accept_downloads=False, service_workers="block",
                    viewport={"width": 1280, "height": 900}, locale="en-IN",
                    user_agent=None)
                await self._context.route("**/*", self._route)
                self.stats["launched"] = True
                return True
            except Exception as exc:
                self.unavailable_reason = f"browser launch failed: {type(exc).__name__}: {str(exc)[:160]}"
                await self.close()
                return False

    async def close(self) -> None:
        clean = True
        for closer in (self._context, self._browser):
            if closer is not None:
                try:
                    await closer.close()
                except Exception:
                    clean = False
        if self._pw is not None:
            try:
                await self._pw.stop()
            except Exception:
                clean = False
        if self.stats["launched"]:
            self.stats["closed_cleanly"] = clean and self.stats["pages_opened"] == self.stats["pages_closed"]
        self._context = self._browser = self._pw = None

    # ----------------------------------------------------------- safety
    async def _host_allowed(self, host: str) -> bool:
        host = host.casefold().rstrip(".")
        if host in self.allow_private_hosts:
            return True
        if host in self._host_ok:
            return self._host_ok[host]
        try:
            address = ipaddress.ip_address(host.strip("[]"))
            ok = address.is_global
        except ValueError:
            if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
                ok = False
            else:
                try:
                    infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
                    ok = bool(infos) and all(ipaddress.ip_address(i[4][0].split("%")[0]).is_global for i in infos)
                except (socket.gaierror, ValueError):
                    ok = False
        self._host_ok[host] = ok
        return ok

    async def _route(self, route) -> None:
        request = route.request
        parts = urlsplit(request.url)
        if parts.scheme in {"data", "blob", "about"}:
            await route.continue_()
            return
        if parts.scheme not in {"http", "https"} or not parts.hostname or \
                request.resource_type in {"image", "media", "font"} or not await self._host_allowed(parts.hostname):
            if request.resource_type not in {"image", "media", "font"}:
                self.stats["blocked_requests"] += 1
            await route.abort()
            return
        await route.continue_()

    # ------------------------------------------------------------ render
    async def render(self, url: str, *, reveal: bool = True, capture_json: bool = True,
                     career_pattern: str = CAREER_LABEL) -> RenderResult:
        result = RenderResult(url=url)
        started = time.perf_counter()
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.hostname or not await self._host_allowed(parts.hostname):
            result.state, result.error = SourceState.UNSUPPORTED, "unsafe URL"
            return result
        if not await self._ensure():
            result.state, result.error = SourceState.UNAVAILABLE, self.unavailable_reason
            return result
        async with self._slots:
            self._active += 1
            self.stats["peak_concurrent"] = max(self.stats["peak_concurrent"], self._active)
            page = None
            try:
                page = await self._context.new_page()
                self.stats["pages_opened"] += 1
                captured: list[dict[str, Any]] = []
                pending: list[asyncio.Task] = []

                async def grab(response) -> None:
                    try:
                        if len(captured) >= self.max_json_responses:
                            return
                        if response.request.resource_type not in {"xhr", "fetch"}:
                            return
                        if "json" not in (response.headers.get("content-type") or ""):
                            return
                        body = await response.body()
                        if len(body) > self.max_json_bytes:
                            return
                        captured.append({"url": response.url, "status": response.status,
                                         "data": json.loads(body.decode("utf-8", "replace"))})
                    except Exception:
                        return

                if capture_json:
                    page.on("response", lambda response: pending.append(asyncio.ensure_future(grab(response))))
                response = await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
                status = response.status if response else None
                result.final_url = page.url
                if status and status >= 400:
                    result.state = SourceState.from_http(status)
                    result.error = f"HTTP {status}"
                    result.html = (await page.content())[:2_000_000]
                    return result
                try:
                    await page.wait_for_load_state("networkidle", timeout=self.settle_ms)
                except Exception:
                    pass  # long-polling sites never go idle; the DOM is usable anyway
                links = await page.evaluate(COLLECT_JS)
                if reveal and self.max_clicks:
                    import re as _re
                    has_career = any(_re.search(career_pattern, f"{l['text']} {l['label']} {l['url']}", _re.I)
                                     and l.get("visible") for l in links)
                    targets = await page.evaluate(CLICKABLES_JS, [career_pattern, MENU_LABEL, not has_career])
                    for target in targets[: self.max_clicks]:
                        if target["kind"] == "menu" and has_career:
                            continue
                        before = page.url
                        try:
                            await page.click(f"[data-di-click='{target['id']}']", timeout=2500)
                            await page.wait_for_timeout(600)
                        except Exception:
                            continue
                        result.clicked.append(f"{target['kind']}: {target['label']}")
                        if page.url != before:
                            result.navigated_to = page.url
                            try:
                                await page.wait_for_load_state("domcontentloaded", timeout=self.settle_ms)
                            except Exception:
                                pass
                        links = await page.evaluate(COLLECT_JS)
                        if result.navigated_to:
                            break
                result.links = links
                result.html = (await page.content())[:2_000_000]
                if pending:
                    await asyncio.wait(pending, timeout=2)
                result.json_responses = captured
                result.state = SourceState.FETCH_OK
                result.final_url = page.url
            except Exception as exc:
                name = type(exc).__name__
                result.state = SourceState.TIMEOUT if "Timeout" in name else SourceState.EXTRACT_FAILED
                result.error = f"{name}: {str(exc).splitlines()[0][:160]}"
            finally:
                if page is not None:
                    try:
                        await page.close()
                        self.stats["pages_closed"] += 1
                    except Exception:
                        pass
                self._active -= 1
                rss = _child_rss_mb()
                if rss is not None:
                    self.stats["peak_browser_rss_mb"] = max(self.stats["peak_browser_rss_mb"] or 0, rss)
                result.elapsed_ms = int((time.perf_counter() - started) * 1000)
                self.stats["render_ms"].append(result.elapsed_ms)
        return result

    def summary(self) -> dict[str, Any]:
        renders = self.stats["render_ms"]
        return {**{k: v for k, v in self.stats.items() if k != "render_ms"}, "renders": len(renders),
                "median_render_ms": sorted(renders)[len(renders) // 2] if renders else None,
                "unavailable_reason": self.unavailable_reason}
