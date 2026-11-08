
from app.mcp.normalizer import normalize_fetch_results, save_results

import asyncio
import json
from mcp import Client

PARALLEL_URL = "https://mcp.parallel.ai/mcp"

FETCH_TASKS = [
    {
        "name": "GATE 2027 official updates",
        "urls": [
            "https://gate2027.iitm.ac.in/important_dates",
            "https://gate2027.iitm.ac.in/notifications",
        ],
        "objective": "Extract current GATE 2027 dates, notifications and upcoming deadlines.",
        "search_queries": [
            "GATE 2027 important dates",
            "GATE 2027 latest notifications",
        ],
    },
    {
        "name": "MCP ecosystem updates",
        "urls": [
            "https://blog.modelcontextprotocol.io/",
            "https://registry.modelcontextprotocol.io/",
        ],
        "objective": "Identify recent MCP specification, SDK and registry updates.",
        "search_queries": [
            "MCP latest specification updates",
            "MCP server registry releases",
        ],
    },
]


async def fetch_objective(client, task):
    print(f"\nFetching: {task['name']}")

    result = await client.call_tool(
        "web_fetch",
        arguments={
            "urls": task["urls"],
            "objective": task["objective"],
            "search_queries": task["search_queries"],
            "full_content": False,
            "allow_live_fetch": True,
        },
    )

    if result.is_error:
        return {
            "task": task["name"],
            "error": "Fetch failed",
        }

    output = []

    for block in result.content:
        if hasattr(block, "text"):
            output.append(block.text)

    return {
        "task": task["name"],
        "content": output,
    }


async def main():
    print("Connecting to Parallel MCP...")

    async with Client(PARALLEL_URL) as client:
        print("Connected successfully!")
        print("\nLaunching concurrent fetches...")

        results = await asyncio.gather(
            *[
                fetch_objective(client, task)
                for task in FETCH_TASKS
            ],
            return_exceptions=True,
        )

    # Remove failed tasks and exceptions
    valid_results = [
        result
        for result in results
        if isinstance(result, dict)
        and "content" in result
    ]

    print("\nNormalizing fetched results...")

    normalized = normalize_fetch_results(valid_results)

    print("\nNORMALIZED RESULTS:")
    print(json.dumps(
        normalized,
        indent=2,
        ensure_ascii=False,
    ))

    save_results(normalized)

    print("\nAll fetch and normalization tasks completed.")


if __name__ == "__main__":
    asyncio.run(main())
