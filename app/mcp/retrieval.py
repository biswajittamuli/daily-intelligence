"""Reusable, bounded Parallel MCP search and page retrieval interface."""

from __future__ import annotations

import json
import asyncio
import logging
import os
import socket
import sys
import time
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlsplit, urlunsplit

from mcp import Client
import httpx2
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client

from app.config import Settings
from app.mcp.normalizer import canonicalize_url
from app.mcp.url_safety import validate_public_http_url


class RetrievalError(RuntimeError):
    pass


log = logging.getLogger(__name__)


def _safe_endpoint(value: str) -> str:
    parts = urlsplit(value)
    host = parts.hostname or "unknown"
    if parts.port:
        host += f":{parts.port}"
    return f"{parts.scheme}://{host}"


def _safe_url(value: str) -> str:
    parts = urlsplit(str(value))
    sensitive = {"token", "api_key", "apikey", "key", "auth", "access_token", "signature", "sig", "session"}
    query = [(key, "[redacted]" if key.casefold() in sensitive else val)
             for key, val in parse_qsl(parts.query, keep_blank_values=True)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def _error_category(message: str) -> str:
    value = message.casefold()
    if any(word in value for word in ("401", "unauthorized", "invalid token", "authentication")):
        return "authentication"
    if any(word in value for word in ("403", "forbidden", "not authorized")):
        return "authorization"
    if "timeout" in value or "timed out" in value:
        return "timeout"
    if any(word in value for word in ("protocol", "json-rpc", "initialize")):
        return "protocol"
    if any(word in value for word in ("name resolution", "gaierror", "connect", "network")):
        return "network"
    if "empty page content" in value:
        return "content"
    return "tool_or_server"


@asynccontextmanager
async def _parallel_transport(settings: Settings):
    token = os.getenv("PARALLEL_MCP_AUTH_TOKEN", "").strip()
    headers = {"Authorization": f"Bearer {token}"} if token else None
    async with create_mcp_http_client(
        headers=headers,
        timeout=httpx2.Timeout(settings.mcp_timeout, read=settings.mcp_timeout),
    ) as http_client:
        async with streamable_http_client(settings.parallel_mcp_url, http_client=http_client) as streams:
            yield streams


def _new_client(settings: Settings):
    return Client(_parallel_transport(settings), read_timeout_seconds=settings.mcp_timeout)


def _tcp_probe(endpoint_url: str, timeout: float):
    parts = urlsplit(endpoint_url)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    with socket.create_connection((parts.hostname, port), timeout=timeout):
        return True


def _text_blocks(result: Any) -> list[str]:
    blocks = getattr(result, "content", [])
    return [block.text for block in blocks if getattr(block, "type", None) == "text"]


def _parse_result_objects(text_blocks: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for text in text_blocks:
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, dict):
            values = parsed.get("results", [])
            if isinstance(values, list):
                records.extend(item for item in values if isinstance(item, dict))
    return records


class ParallelWebRetriever:
    """Discover required MCP tools and perform generic search/fetch calls."""

    def __init__(self, client: Any | None = None,
                 settings: Settings | None = None) -> None:
        self.settings = settings or Settings.from_env()
        self._client = client
        self._owns_client = client is None
        self._available_tools: set[str] | None = None
        self._tool_calls = 0

    async def __aenter__(self) -> "ParallelWebRetriever":
        if self._client is None:
            try:
                await asyncio.wait_for(asyncio.to_thread(
                    _tcp_probe, self.settings.parallel_mcp_url,
                    min(3.0, self.settings.mcp_timeout)),
                    timeout=min(3.5, self.settings.mcp_timeout + 0.5))
            except Exception as exc:
                raise RetrievalError(f"MCP endpoint connection preflight failed: {type(exc).__name__}: {exc}") from exc
            self._client = _new_client(self.settings)
        await asyncio.wait_for(self._client.__aenter__(), timeout=self.settings.mcp_timeout)
        await self.discover_tools()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._owns_client and self._client is not None:
            await self._client.__aexit__(exc_type, exc, tb)

    async def discover_tools(self) -> set[str]:
        if self._client is None:
            raise RetrievalError("MCP client is not connected")
        try:
            response = await asyncio.wait_for(self._client.list_tools(), timeout=self.settings.mcp_timeout)
        except Exception as exc:
            if isinstance(exc, TimeoutError):
                raise RetrievalError(f"Tool discovery timed out after {self.settings.mcp_timeout:g}s") from exc
            raise RetrievalError(f"Could not discover MCP tools: {exc}") from exc
        self._available_tools = {tool.name for tool in response.tools}
        return set(self._available_tools)

    async def _call(self, name: str, arguments: dict[str, Any]) -> Any:
        if self._tool_calls >= self.settings.max_tool_calls:
            raise RetrievalError(f"Configured maximum tool calls ({self.settings.max_tool_calls}) reached")
        if self._available_tools is None:
            await self.discover_tools()
        if name not in (self._available_tools or set()):
            raise RetrievalError(f"MCP server does not provide required tool '{name}'")
        try:
            started = time.perf_counter()
            self._tool_calls += 1
            log.info("mcp tool=%s status=started", name)
            result = await asyncio.wait_for(self._client.call_tool(name, arguments=arguments),
                                            timeout=self.settings.mcp_timeout)
            log.info("mcp tool=%s status=complete elapsed=%.2fs", name, time.perf_counter()-started)
        except Exception as exc:
            log.warning("mcp tool=%s status=failed error_type=%s", name, type(exc).__name__)
            raise RetrievalError(f"MCP tool '{name}' failed: {exc}") from exc
        if getattr(result, "is_error", False):
            raise RetrievalError(f"MCP tool '{name}' returned an error")
        return result

    async def search(self, queries: list[str], objective: str,
                     *, source_guidance: str = "",
                     freshness_days: int | None = None) -> list[dict[str, Any]]:
        limit = max(1, min(self.settings.max_search_queries, 8))
        cleaned = list(dict.fromkeys(" ".join(q.split()) for q in queries if q.strip()))[:limit]
        if not cleaned:
            raise ValueError("At least one search query is required")
        composed_objective = objective.strip()
        if source_guidance.strip():
            composed_objective += f" Prioritize: {source_guidance.strip()}"
        if freshness_days:
            composed_objective += f" Prefer information published within {freshness_days} days."
        result = await self._call("web_search", {
            "search_queries": cleaned,
            "objective": composed_objective,
        })
        retrieved_at = datetime.now(timezone.utc).isoformat()
        normalized = []
        seen = set()
        for item in _parse_result_objects(_text_blocks(result)):
            raw_url = str(item.get("url", "")).strip()
            try:
                url = validate_public_http_url(raw_url)
            except ValueError:
                continue
            canonical = canonicalize_url(url)
            if canonical in seen:
                continue
            seen.add(canonical)
            excerpts = item.get("excerpts", [])
            if isinstance(excerpts, str):
                excerpts = [excerpts]
            if not isinstance(excerpts, list):
                excerpts = []
            parsed_url = urlparse(url)
            normalized.append({
                "title": str(item.get("title", "")).strip(),
                "url": url,
                "original_url": url,
                "canonical_url": canonical,
                "domain": parsed_url.hostname,
                "publish_date": item.get("publish_date"),
                "retrieved_at": item.get("acquired_at") or retrieved_at,
                "source_type": "unknown",
                "excerpts": excerpts,
                "evidence": [{"text": str(part), "source_url": url} for part in excerpts],
                "metadata": {k: v for k, v in item.items()
                             if k not in {"url", "title", "excerpts", "publish_date"}},
            })
        selected = normalized[:max(10, min(40, self.settings.max_fetch_urls * 5))]
        log.info("mcp search complete results=%d unique_public_results=%d", len(selected), len(normalized))
        return selected

    async def fetch(self, urls: list[str], objective: str,
                    *, search_queries: list[str] | None = None,
                    full_content: bool = True) -> list[dict[str, Any]]:
        limit = max(1, min(self.settings.max_fetch_urls, 20))
        safe_urls = list(dict.fromkeys(validate_public_http_url(url) for url in urls))[:limit]
        if not safe_urls:
            return []
        queries = (search_queries or [])[:max(1, min(self.settings.max_search_queries, 8))]
        result = await self._call("web_fetch", {
            "urls": safe_urls,
            "objective": objective,
            "search_queries": queries,
            "full_content": full_content,
            "allow_live_fetch": True,
        })
        records = _parse_result_objects(_text_blocks(result))
        budget = max(1000, self.settings.max_content_chars)
        bounded = []
        for item in records:
            copy = dict(item)
            key = "full_content" if isinstance(copy.get("full_content"), str) else "content"
            body = copy.get(key)
            if isinstance(body, str):
                copy[key] = body[:budget]
                budget -= len(copy[key])
            bounded.append(copy)
            if budget <= 0:
                break
        page_count = len(bounded)
        content_chars = sum(len(str(item.get("full_content") or item.get("content") or ""))
                            for item in bounded)
        log.info("web retrieval complete requested_urls=%d returned_pages=%d content_chars=%d",
                 len(safe_urls), page_count, content_chars)
        return bounded

    async def diagnostics(self, query: str = "latest developments in AI agents") -> dict[str, Any]:
        """Real connection, dynamic discovery, search and URL-correlated fetch diagnostic."""
        report: dict[str, Any] = {"endpoint": _safe_endpoint(self.settings.parallel_mcp_url), "stages": {}, "ok": False}
        started = time.perf_counter()
        stage = "connection"

        def mark_stage(name: str):
            if os.getenv("DAILY_INTELLIGENCE_MCP_WORKER") == "1":
                print(f"DAILY_INTEL_MCP_STAGE={name}|{time.perf_counter()-started:.3f}", file=sys.stderr, flush=True)

        try:
            mark_stage("connection")
            if self._client is None:
                self._client = _new_client(self.settings)
            await asyncio.wait_for(self._client.__aenter__(), timeout=self.settings.mcp_timeout)
            report["stages"][stage] = {"status": "ok", "duration_seconds": round(time.perf_counter()-started, 3)}
            stage = "tool_discovery"
            mark_stage(stage)
            mark = time.perf_counter()
            names = await self.discover_tools()
            report["tools"] = sorted(names)
            report["stages"][stage] = {"status": "ok", "duration_seconds": round(time.perf_counter()-mark, 3)}
            if "web_search" not in names:
                raise RetrievalError("Tool discovery succeeded but web_search is unavailable")
            if "web_fetch" not in names:
                raise RetrievalError("Tool discovery succeeded but web_fetch is unavailable")
            stage = "search"
            mark_stage(stage)
            mark = time.perf_counter()
            results = await self.search([query], "Find recent, relevant developments and original sources")
            report["search_result_count"] = len(results)
            report["search_results"] = [{"title": item.get("title"), "url": _safe_url(item.get("original_url") or item.get("url")),
                                         "publish_date": item.get("publish_date")} for item in results]
            report["stages"][stage] = {"status": "ok" if results else "failed",
                                      "duration_seconds": round(time.perf_counter()-mark, 3)}
            if not results:
                raise RetrievalError("web_search completed but returned no usable public URLs")
            stage = "fetch"
            mark_stage(stage)
            mark = time.perf_counter()
            # Search results can point at paywalled or bot-protected pages that
            # return an empty body. Try a few candidates before declaring the
            # MCP fetch tool itself broken.
            targets = results[:max(1, min(3, self.settings.max_fetch_urls))]
            fetched = await self.fetch(
                [target["url"] for target in targets],
                "Retrieve the selected search result page",
                search_queries=[query], full_content=True)
            report["fetch_result_count"] = len(fetched)
            report["fetch_attempted_urls"] = [_safe_url(target["url"]) for target in targets]
            wanted = {canonicalize_url(target["url"]): target for target in targets}
            correlated = []
            for item in fetched:
                item_url = str(item.get("url") or "")
                if not item_url or canonicalize_url(item_url) not in wanted:
                    continue
                full = str(item.get("full_content") or item.get("content") or "")
                excerpts = item.get("excerpts") or []
                if isinstance(excerpts, str):
                    excerpts = [excerpts]
                excerpt_text = "\n".join(str(part) for part in excerpts if part)
                correlated.append((item, full, excerpt_text))
            match = next((entry for entry in correlated if entry[1] or entry[2]), None)
            if not match:
                report["stages"][stage] = {"status": "failed",
                                          "duration_seconds": round(time.perf_counter()-mark, 3)}
                if not correlated:
                    raise RetrievalError("web_fetch returned no content correlated to the requested URL")
                raise RetrievalError(
                    f"web_fetch returned empty page content for all {len(correlated)} requested URLs")
            item, full_content, excerpt_text = match
            content = full_content or excerpt_text
            report["requested_url"] = _safe_url(wanted[canonicalize_url(str(item["url"]))]["url"])
            report["fetched_url"] = _safe_url(item.get("url"))
            report["url_match"] = True
            report["page_title"] = item.get("title") or wanted[canonicalize_url(str(item["url"]))].get("title") or "(no title returned)"
            report["content_length"] = len(content)
            report["content_source"] = "full_content" if full_content else "excerpts"
            report["content_excerpt"] = content[:1200]
            report["stages"][stage] = {"status": "ok",
                                      "duration_seconds": round(time.perf_counter()-mark, 3)}
            report["ok"] = True
        except Exception as exc:
            if os.getenv("DAILY_INTELLIGENCE_MCP_WORKER") == "1":
                print(f"DAILY_INTEL_MCP_STAGE_FAILED={stage}", file=sys.stderr, flush=True)
            report["failure_stage"] = stage
            safe_error = str(exc).replace(self.settings.parallel_mcp_url, _safe_endpoint(self.settings.parallel_mcp_url))
            report["error"] = f"{type(exc).__name__}: {safe_error}"
            report["error_category"] = _error_category(safe_error)
            report["stages"].setdefault(stage, {"status": "failed"})
        finally:
            report["total_duration_seconds"] = round(time.perf_counter()-started, 3)
            if self._client is not None and self._owns_client:
                try:
                    await asyncio.wait_for(self._client.__aexit__(None, None, None), timeout=3)
                except Exception:
                    pass
                self._client = None
                self._available_tools = None
        return report
