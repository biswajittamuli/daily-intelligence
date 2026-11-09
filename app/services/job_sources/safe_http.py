"""Polite, bounded, SSRF-safe HTTP fetcher used by every direct-fetch adapter.

Guarantees
- Only public http(s) URLs: the URL is validated, *every* resolved address must be global, and each
  redirect hop is re-validated (at most ``max_redirects``).
- robots.txt is read once per origin and honoured (wildcards, longest match, crawl-delay).
- Per-host serialisation with a minimum interval (or the site's crawl-delay, capped), plus a global
  concurrency cap — conservative defaults suited to a 16 GB laptop.
- Response bodies are streamed and cut at ``max_bytes``; non-text types are refused.
- An on-disk cache (separate SQLite file) stores bodies with ETag / Last-Modified so unchanged
  pages are revalidated cheaply instead of re-downloaded.
- Outcomes are classified into ``SourceState`` values, including bot challenges, which are
  reported and never bypassed.

Nothing personal is ever sent: no cookies are kept between runs and the User-Agent is generic.
"""
from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import logging
import socket
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from app.mcp.url_safety import UnsafeURLError, validate_public_http_url
from app.services.job_sources.models import SourceState
from app.services.job_sources.robots import RobotsPolicy

log = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; DailyIntelligence/3.3; local personal job finder; respects robots.txt)"
TEXT_TYPES = ("text/html", "application/xhtml", "application/json", "application/ld+json", "text/plain",
              "application/xml", "text/xml", "application/rss", "application/atom")
CHALLENGE_MARKERS = ("cf-chl", "challenge-platform", "attention required! | cloudflare", "verify you are human",
                     "are you a robot", "px-captcha", "g-recaptcha", "h-captcha", "hcaptcha.com", "captcha-delivery",
                     "datadome", "perimeterx", "please enable cookies", "checking your browser",
                     "access denied</title>", "request unsuccessful. incapsula")


@dataclass
class FetchResult:
    url: str
    final_url: str | None = None
    status: int | None = None
    state: str = SourceState.UNAVAILABLE
    content_type: str = ""
    text: str = ""
    error: str | None = None
    from_cache: bool = False
    not_modified: bool = False
    elapsed_ms: int = 0
    redirects: list[str] = field(default_factory=list)
    truncated: bool = False

    @property
    def ok(self) -> bool:
        return self.state == SourceState.FETCH_OK and bool(self.text)


class PrivateAddressError(UnsafeURLError):
    pass


def _is_challenge(status: int | None, text: str) -> bool:
    head = text[:6000].casefold()
    if status in {403, 429, 503} or len(text) < 20000:
        return any(marker in head for marker in CHALLENGE_MARKERS)
    return False


class SafeFetcher:
    """Async fetcher; create one per acquisition run (``async with SafeFetcher(...) as http``)."""

    def __init__(self, *, concurrency: int = 6, per_host_interval: float = 1.0, timeout: float = 15.0,
                 max_bytes: int = 1_500_000, max_redirects: int = 5, respect_robots: bool = True,
                 cache_path: Path | None = None, cache_ttl: float = 6 * 3600, max_crawl_delay: float = 10.0,
                 allow_private_hosts: set[str] | frozenset[str] = frozenset(),
                 transport: httpx.AsyncBaseTransport | None = None, retries: int = 1,
                 client: httpx.AsyncClient | None = None, resolve_dns: bool = True) -> None:
        self.concurrency = max(1, concurrency)
        self.per_host_interval = max(0.0, per_host_interval)
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects
        self.respect_robots = respect_robots
        self.cache_path = cache_path
        self.cache_ttl = cache_ttl
        self.max_crawl_delay = max_crawl_delay
        # Only tests set this (local fixture server); it is never derived from user or page input.
        self.allow_private_hosts = frozenset(h.casefold() for h in allow_private_hosts)
        self.retries = max(0, min(retries, 3))
        self._transport = transport
        self._client: httpx.AsyncClient | None = client
        self._owns_client = client is None
        # resolve_dns=False is only for an injected mock client (tests); real clients always resolve and check.
        self.resolve_dns = resolve_dns or client is None
        self._global = asyncio.Semaphore(self.concurrency)
        self._host_locks: dict[str, asyncio.Lock] = {}
        self._host_last: dict[str, float] = {}
        self._robots: dict[str, RobotsPolicy] = {}
        self._resolved: dict[str, bool] = {}
        self.stats: dict[str, Any] = {"requests": 0, "cache_hits": 0, "revalidated": 0, "bytes": 0,
                                      "robots_blocked": 0, "challenges": 0, "errors": 0, "durations_ms": []}

    async def __aenter__(self) -> "SafeFetcher":
        if self._client is not None and not self._owns_client:
            if self.cache_path:
                self._init_cache()
            return self
        self._client = httpx.AsyncClient(timeout=self.timeout, follow_redirects=False, transport=self._transport,
                                         headers={"User-Agent": USER_AGENT, "Accept-Language": "en-IN,en;q=0.8",
                                                  "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.5"})
        if self.cache_path:
            self._init_cache()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------ safety
    async def check_url(self, url: str) -> str:
        try:
            parts = urlsplit(str(url).strip())
        except ValueError as exc:
            raise UnsafeURLError("Malformed URL") from exc
        if parts.scheme in {"http", "https"} and (parts.hostname or "").casefold() in self.allow_private_hosts:
            return str(url).strip()
        url = validate_public_http_url(url)
        host = (urlsplit(url).hostname or "").casefold().rstrip(".")
        if not self.resolve_dns:
            return url
        if host in self._resolved:
            if not self._resolved[host]:
                raise PrivateAddressError("Host resolves to a private or reserved address")
            return url
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise UnsafeURLError(f"DNS resolution failed for {host}") from exc
        addresses = {info[4][0] for info in infos}
        safe = bool(addresses) and all(ipaddress.ip_address(a.split("%")[0]).is_global for a in addresses)
        self._resolved[host] = safe
        if not safe:
            raise PrivateAddressError("Host resolves to a private or reserved address")
        return url

    # ------------------------------------------------------------ robots
    async def robots(self, url: str) -> RobotsPolicy:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}".casefold()
        if origin in self._robots:
            return self._robots[origin]
        cached = self._cache_get(origin + "/robots.txt", max_age=24 * 3600)
        if cached is not None:
            policy = RobotsPolicy(cached["body"], status=cached["status"])
        else:
            result = await self._request(origin + "/robots.txt", use_cache=False, check_robots=False,
                                         accept_any_type=True)
            status = result.status
            if result.error and status is None:
                # Robots unreachable because the host is unreachable: the page fetch will fail on its own.
                policy = RobotsPolicy("", status=404)
            else:
                policy = RobotsPolicy(result.text if status and status < 300 else "", status=status)
                self._cache_put(origin + "/robots.txt", status or 0, result.text[:200_000] if status and status < 300 else "",
                                {}, "text/plain")
        self._robots[origin] = policy
        return policy

    # ------------------------------------------------------------- fetch
    async def get(self, url: str, *, use_cache: bool = True, accept_json: bool = False) -> FetchResult:
        return await self._request(url, use_cache=use_cache, check_robots=self.respect_robots,
                                   accept_any_type=accept_json)

    async def get_many(self, urls: list[str], **kwargs: Any) -> list[FetchResult]:
        return list(await asyncio.gather(*(self.get(url, **kwargs) for url in urls)))

    async def _request(self, url: str, *, use_cache: bool, check_robots: bool, accept_any_type: bool) -> FetchResult:
        assert self._client is not None, "use 'async with SafeFetcher()'"
        started = time.perf_counter()
        result = FetchResult(url=url)
        try:
            current = await self.check_url(url)
        except UnsafeURLError as exc:
            result.state, result.error = SourceState.UNSUPPORTED, f"unsafe URL: {exc}"
            return result
        if check_robots:
            policy = await self.robots(current)
            if not policy.allowed(current):
                self.stats["robots_blocked"] += 1
                result.state, result.error = SourceState.ROBOTS_DISALLOWED, "robots.txt disallows this path"
                return result
        cached = self._cache_get(current) if use_cache else None
        if cached is not None and time.time() - cached["fetched_at"] < self.cache_ttl:
            self.stats["cache_hits"] += 1
            return FetchResult(url=url, final_url=cached["final_url"] or current, status=cached["status"],
                               state=SourceState.FETCH_OK if 200 <= cached["status"] < 300 else SourceState.from_http(cached["status"]),
                               content_type=cached["content_type"], text=cached["body"], from_cache=True)
        host = (urlsplit(current).hostname or "").casefold()
        attempt = 0
        while True:
            try:
                async with self._global:
                    await self._wait_host(host, current)
                    response_info = await self._follow(current, cached if use_cache else None)
                break
            except (httpx.TimeoutException, asyncio.TimeoutError):
                result.state, result.error = SourceState.TIMEOUT, "request timed out"
            except UnsafeURLError as exc:
                result.state, result.error = SourceState.UNSUPPORTED, f"unsafe redirect: {exc}"
                return result
            except httpx.HTTPError as exc:
                result.state, result.error = SourceState.UNAVAILABLE, f"{type(exc).__name__}: {str(exc)[:120]}"
            attempt += 1
            if attempt > self.retries:
                self.stats["errors"] += 1
                result.elapsed_ms = int((time.perf_counter() - started) * 1000)
                return result
            await asyncio.sleep(1.5 * attempt)
        status, final_url, content_type, text, headers, redirects, truncated = response_info
        result.status, result.final_url, result.content_type, result.redirects = status, final_url, content_type, redirects
        result.truncated = truncated
        result.elapsed_ms = int((time.perf_counter() - started) * 1000)
        self.stats["durations_ms"].append(result.elapsed_ms)
        if status == 304 and cached is not None:
            self.stats["revalidated"] += 1
            self._cache_touch(current)
            result.status, result.text, result.content_type = cached["status"], cached["body"], cached["content_type"]
            result.state, result.from_cache, result.not_modified = SourceState.FETCH_OK, True, True
            return result
        if _is_challenge(status, text):
            self.stats["challenges"] += 1
            result.state, result.error = SourceState.BOT_CHALLENGE, f"bot challenge page (HTTP {status})"
            return result
        result.state = SourceState.from_http(status)
        if result.state == SourceState.FETCH_OK:
            if not accept_any_type and content_type and not content_type.startswith(TEXT_TYPES):
                result.state, result.error = SourceState.UNSUPPORTED, f"content type {content_type}"
                return result
            result.text = text
            if use_cache:
                self._cache_put(current, status, text, headers, content_type, final_url)
        else:
            result.text = text if accept_any_type else ""
            result.error = f"HTTP {status}"
        return result

    async def _wait_host(self, host: str, url: str) -> None:
        lock = self._host_locks.setdefault(host, asyncio.Lock())
        async with lock:
            interval = self.per_host_interval
            policy = self._robots.get(f"{urlsplit(url).scheme}://{urlsplit(url).netloc}".casefold())
            delay = policy.crawl_delay() if policy else None
            if delay:
                interval = max(interval, min(delay, self.max_crawl_delay))
            wait = self._host_last.get(host, 0.0) + interval - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._host_last[host] = time.monotonic()

    async def _follow(self, url: str, cached: dict[str, Any] | None):
        assert self._client is not None
        redirects: list[str] = []
        current = url
        for _ in range(self.max_redirects + 1):
            headers = {}
            if cached and current == url:
                if cached.get("etag"):
                    headers["If-None-Match"] = cached["etag"]
                if cached.get("last_modified"):
                    headers["If-Modified-Since"] = cached["last_modified"]
            self.stats["requests"] += 1
            async with self._client.stream("GET", current, headers=headers) as response:
                if response.status_code in {301, 302, 303, 307, 308} and response.headers.get("location"):
                    target = urljoin(current, response.headers["location"])
                    current = await self.check_url(target)
                    redirects.append(current)
                    continue
                content_type = response.headers.get("content-type", "").split(";")[0].strip().casefold()
                chunks, size, truncated = [], 0, False
                if response.status_code != 304:
                    async for chunk in response.aiter_bytes():
                        chunks.append(chunk)
                        size += len(chunk)
                        if size >= self.max_bytes:
                            truncated = True
                            break
                body = b"".join(chunks)[: self.max_bytes]
                self.stats["bytes"] += len(body)
                encoding = response.encoding or "utf-8"
                try:
                    text = body.decode(encoding, errors="replace")
                except LookupError:
                    text = body.decode("utf-8", errors="replace")
                return (response.status_code, current, content_type, text, dict(response.headers), redirects, truncated)
        raise UnsafeURLError("too many redirects")

    # ------------------------------------------------------------- cache
    def _init_cache(self) -> None:
        assert self.cache_path is not None
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.cache_path, timeout=5)) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS http_cache (url_hash TEXT PRIMARY KEY, url TEXT, final_url TEXT,
                          status INTEGER, content_type TEXT, etag TEXT, last_modified TEXT, body TEXT,
                          fetched_at REAL)""")
            db.execute("DELETE FROM http_cache WHERE fetched_at < ?", (time.time() - 7 * 86400,))
            db.commit()

    @staticmethod
    def _hash(url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()

    def _cache_get(self, url: str, *, max_age: float | None = None) -> dict[str, Any] | None:
        if not self.cache_path:
            return None
        try:
            with closing(sqlite3.connect(self.cache_path, timeout=5)) as db:
                db.row_factory = sqlite3.Row
                row = db.execute("SELECT * FROM http_cache WHERE url_hash=?", (self._hash(url),)).fetchone()
        except sqlite3.Error:
            return None
        if row is None:
            return None
        if max_age is not None and time.time() - row["fetched_at"] > max_age:
            return None
        return dict(row)

    def _cache_put(self, url: str, status: int, body: str, headers: dict[str, Any], content_type: str,
                   final_url: str | None = None) -> None:
        if not self.cache_path:
            return
        lowered = {k.casefold(): v for k, v in headers.items()}
        if "no-store" in str(lowered.get("cache-control", "")):
            return
        try:
            with closing(sqlite3.connect(self.cache_path, timeout=5)) as db:
                db.execute("INSERT OR REPLACE INTO http_cache VALUES(?,?,?,?,?,?,?,?,?)",
                           (self._hash(url), url, final_url, status, content_type, lowered.get("etag"),
                            lowered.get("last-modified"), body[: self.max_bytes], time.time()))
                db.commit()
        except sqlite3.Error as exc:
            log.debug("cache write failed: %s", exc)

    def _cache_touch(self, url: str) -> None:
        if not self.cache_path:
            return
        try:
            with closing(sqlite3.connect(self.cache_path, timeout=5)) as db:
                db.execute("UPDATE http_cache SET fetched_at=? WHERE url_hash=?", (time.time(), self._hash(url)))
                db.commit()
        except sqlite3.Error:
            pass

    def summary(self) -> dict[str, Any]:
        durations = self.stats["durations_ms"]
        return {**{k: v for k, v in self.stats.items() if k != "durations_ms"},
                "median_ms": sorted(durations)[len(durations) // 2] if durations else None,
                "max_ms": max(durations) if durations else None}
