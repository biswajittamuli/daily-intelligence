"""Check that a saved API key actually works, with the cheapest call each provider offers.

- Adzuna: one search for 1 result (counts as one API call).
- SerpApi: account.json, free; does not use a search. Reports searches left this month.
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
            if provider_id == "adzuna":
                response = await client.get("https://api.adzuna.com/v1/api/jobs/in/search/1", params={
                    "app_id": os.environ["ADZUNA_APP_ID"], "app_key": os.environ["ADZUNA_APP_KEY"],
                    "results_per_page": 1, "what": "software engineer", "content-type": "application/json"})
                if response.status_code != 200:
                    return _http_failure("Adzuna", response)
                count = (response.json() or {}).get("count")
                return _result(True, f"Adzuna key works: {count:,} matching jobs in India right now." if isinstance(count, int)
                               else "Adzuna key works.", count=count)
            if provider_id == "serpapi":
                response = await client.get("https://serpapi.com/account.json",
                                            params={"api_key": os.environ["SERPAPI_API_KEY"]})
                data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                if response.status_code != 200 or data.get("error"):
                    if data.get("error") and response.status_code == 200:
                        return _result(False, f"SerpApi: {data['error']}",
                                       rejected="invalid" in str(data["error"]).casefold())
                    return _http_failure("SerpApi", response)
                left = data.get("total_searches_left", data.get("plan_searches_left"))
                return _result(True, f"SerpApi key works ({data.get('plan_name') or 'plan'}"
                                     + (f", {left} searches left this month" if left is not None else "") + ").",
                               searches_left=left, plan=data.get("plan_name"))
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
