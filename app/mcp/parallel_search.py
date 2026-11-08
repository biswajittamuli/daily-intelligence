
import asyncio
import json
from mcp import Client

PARALLEL_URL = "https://mcp.parallel.ai/mcp"

SEARCH_TASKS = [
    {
        "name": "EXAM UPDATES",
        "queries": [
            "GATE 2027 official notifications and important dates",
            "GATE 2027 latest announcements IIT Madras"
        ],
        "objective": "Find recent official examination updates."
    },
    {
        "name": "AI JOBS",
        "queries": [
            "Entry level AI Engineer jobs India",
            "AI Agent Engineer fresher jobs India"
        ],
        "objective": "Find relevant recent job openings."
    },
    {
        "name": "AI NEWS",
        "queries": [
            "Latest artificial intelligence news",
            "Major AI model releases and research developments"
        ],
        "objective": "Identify important recent AI developments."
    },
    {
        "name": "AI AGENT TECHNOLOGY",
        "queries": [
            "Latest MCP developments and releases",
            "Open source AI agent frameworks developments"
        ],
        "objective": "Find important AI agent ecosystem developments."
    }
]


async def search_one(client, task):
    name = task["name"]

    try:
        result = await client.call_tool(
            "web_search",
            {
                "search_queries": task["queries"],
                "objective": task["objective"]
            }
        )

        if result.is_error:
            return {
                "name": name,
                "error": "MCP tool returned an error"
            }

        content = [
            item.text
            for item in result.content
            if item.type == "text"
        ]

        return {
            "name": name,
            "results": content
        }

    except Exception as exc:
        return {
            "name": name,
            "error": str(exc)
        }


async def main():

    print("Connecting to Parallel MCP...")

    async with Client(PARALLEL_URL) as client:

        print("Connected.")
        print("Launching parallel searches...\n")

        results = await asyncio.gather(
            *[
                search_one(client, task)
                for task in SEARCH_TASKS
            ]
        )

        for result in results:

            print("=" * 65)
            print(result["name"])
            print("=" * 65)

            if "error" in result:
                print("ERROR:", result["error"])
            else:
                for content in result["results"]:
                    print(content)

            print()


if __name__ == "__main__":
    asyncio.run(main())
