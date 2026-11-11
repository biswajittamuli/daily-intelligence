"""Check that a saved API key actually works, with the cheapest call each provider offers.

- Jooble: one search (counts as one API call).
- Findwork: one search (counts as one API call).
- Firecrawl: team credit-usage, free; reports remaining credits.
- Parallel: connects to the MCP endpoint and lists its tools; no search is spent.

Returns {"ok": bool, "message": str, "detail": {...}}. Error text never contains a key.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

from app.secrets_store import BY_PROVIDER, redact

TIMEOUT = 20.0


def _result(ok: bool, message: str, *, rejected: bool = False, **detail: Any) -> dict[str, Any]:
    """``rejected`` means the provider definitively refused the key (not a network or quota problem)."""
    return {"ok": ok, "rejected": rejected, "message": redact(message), "detail": detail}


def _http_failure(provider: str, response: httpx.Response) -> dict[str, Any]:
    if response.status_code in {401, 403}:
        return _result(False, f"{provider} rejected the key (HTTP {response.status_code}). Check that you pasted it "
                              "completely and that it is activated.", rejected=True)
    if response.status_code == 429:
        return _result(False, f"{provider} says the rate limit or monthly quota is used up (HTTP 429). The key may be "
                              "valid; try again later.")
    return _result(False, f"{provider} answered HTTP {response.status_code}.")


async def check(provider_id: str, *, transport: httpx.AsyncBaseTransport | None = None) -> dict[str, Any]:
    provider = BY_PROVIDER.get(provider_id)
    if provider is None:
        return _result(False, "Unknown provider")
    missing = [name for name in provider["keys"] if not os.environ.get(name, "").strip()]
    if missing:
        return _result(False, "Not configured: paste " + " and ".join(missing) + " first.")
    try:
        if provider_id == "parallel":
            return await _check_parallel()
        async with httpx.AsyncClient(timeout=TIMEOUT, transport=transport, follow_redirects=False) as client:
            if provider_id == "jooble":
                response = await client.post("https://jooble.org/api/" + os.environ["JOOBLE_API_KEY"].strip(),
                                             json={"keywords": "software engineer", "location": "India"})
                if response.status_code != 200:
                    return _http_failure("Jooble", response)
                count = (response.json() or {}).get("totalCount")
                return _result(True, f"Jooble key works: {count:,} matching jobs in India right now." if isinstance(count, int)
                               else "Jooble key works.", count=count)
            if provider_id == "findwork":
                response = await client.get("https://findwork.dev/api/jobs/", params={"search": "python"},
                                            headers={"Authorization": "Token " + os.environ["FINDWORK_API_KEY"].strip()})
                if response.status_code != 200:
                    return _http_failure("Findwork", response)
                count = (response.json() or {}).get("count")
                return _result(True, f"Findwork key works: {count:,} Python jobs listed." if isinstance(count, int)
                               else "Findwork key works.", count=count)
            if provider_id == "firecrawl":
                headers = {"Authorization": f"Bearer {os.environ['FIRECRAWL_API_KEY']}"}
                response = await client.get("https://api.firecrawl.dev/v1/team/credit-usage", headers=headers)
                if response.status_code == 200:
                    credits = ((response.json() or {}).get("data") or {}).get("remaining_credits")
                    return _result(True, "Firecrawl key works" + (f" ({credits} credits left)." if credits is not None else "."),
                                   remaining_credits=credits)
                return _http_failure("Firecrawl", response)
    except httpx.TimeoutException:
        return _result(False, "The provider did not answer within 20 seconds; check your connection and try again.")
    except httpx.HTTPError as exc:
        return _result(False, f"Network error: {type(exc).__name__}")
    except ValueError:
        return _result(False, "The provider returned an unexpected response.")
    return _result(False, "No check available")


async def _check_parallel() -> dict[str, Any]:
    from dataclasses import replace

    from app.config import Settings
    from app.mcp.retrieval import ParallelWebRetriever, RetrievalError

    settings = Settings.from_env()
    retriever = ParallelWebRetriever(settings=replace(settings, mcp_timeout=max(settings.mcp_timeout, 30.0)))
    try:
        await asyncio.wait_for(retriever.__aenter__(), timeout=40)
        tools = await asyncio.wait_for(retriever.discover_tools(), timeout=30)
    except (RetrievalError, asyncio.TimeoutError, OSError) as exc:
        text = str(exc) or type(exc).__name__
        if "401" in text or "403" in text or "unauthor" in text.casefold():
            return _result(False, "Parallel rejected the token (unauthorised). Check the key.", rejected=True)
        return _result(False, f"Could not reach Parallel: {text[:160]}")
    except Exception as exc:  # the MCP client raises varied exception types for auth failures
        text = str(exc) or type(exc).__name__
        return _result(False, f"Parallel check failed: {text[:160]}")
    finally:
        try:
            await retriever.__aexit__(None, None, None)
        except Exception:
            pass
    return _result(True, f"Parallel token works ({len(tools)} tools available).", tools=sorted(tools))
