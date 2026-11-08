
import asyncio
import json
from urllib.parse import urlparse

from mcp import Client

from app.mcp.normalizer import normalize_fetch_results, save_results

PARALLEL_URL = "https://mcp.parallel.ai/mcp"
MAX_URLS_PER_TASK = 8


SEARCH_TASKS = [
    {
        "name": "GATE AND EXAM UPDATES",
        "queries": [
            "GATE 2027 official notifications IIT Madras",
            "GATE 2027 application rectification dates",
            "GATE 2027 exam announcements official",
        ],
        "objective": "Find recent official examination announcements, deadlines and changes.",
    },
    {
        "name": "PRIVATE AI JOBS",
        "queries": [
            "Entry level AI Engineer jobs India",
            "AI Agent Engineer fresher jobs India",
            "Junior LLM Engineer jobs India",
        ],
        "objective": "Find recent entry-level AI and software engineering jobs in India.",
    },
    {
        "name": "PSU RECRUITMENT - OIL AND GAS",
        "queries": [
            "IOCL recruitment 2026 2027 computer science IT engineer",
            "ONGC recruitment 2026 2027 computer science IT",
            "Oil India recruitment 2026 computer science IT engineer",
            "NRL recruitment 2026 computer science IT engineer",
            "GAIL HPCL BPCL recruitment 2026 IT computer science",
        ],
        "objective": "Find official active and upcoming recruitment advertisements from IOCL, ONGC, Oil India, NRL, GAIL, HPCL and BPCL. Prioritize BTech CSE and IT graduates. Extract eligibility, vacancies, deadlines, selection method and official application links.",
    },
    {
        "name": "PSU RECRUITMENT - OTHER ORGANIZATIONS",
        "queries": [
            "NTPC Power Grid recruitment 2026 computer science IT",
            "BEL ECIL recruitment 2026 computer science engineer",
            "DRDO ISRO BARC CSE recruitment 2026",
            "C DAC BSNL SAIL BHEL CSE recruitment 2026",
        ],
        "objective": "Find official government and PSU opportunities for BTech CSE and IT graduates, including technical, software, cybersecurity and scientific posts.",
    },
    {
        "name": "GOVERNMENT TECH JOBS",
        "queries": [
            "NIC scientist B recruitment computer science 2026",
            "NIELIT scientific assistant computer science recruitment",
            "government software engineer recruitment India 2026",
            "central government IT officer CSE recruitment 2026",
        ],
        "objective": "Find relevant central government technical and scientific recruitment for CSE graduates.",
    },
    {
        "name": "AI NEWS",
        "queries": [
            "Latest major AI developments November 2026",
            "New AI model releases November 2026",
            "Important AI research industry announcements 2026",
        ],
        "objective": "Identify significant recent AI developments and announcements.",
    },
    {
        "name": "AI AGENT TECHNOLOGY",
        "queries": [
            "Latest MCP specification SDK releases 2026",
            "Open source AI agent framework releases 2026",
            "Computer use browser agents research developments",
        ],
        "objective": "Find important AI agent ecosystem developments, tools, standards and releases.",
    },
    {
        "name": "RESEARCH PAPERS - AI AGENTS AND LLM",
        "queries": [
            "2026 LLM agents planning tool use research papers",
            "2026 multi agent systems research papers",
            "2026 LLM memory context retrieval research",
        ],
        "objective": "Find significant recent research papers on AI agents, LLM systems, memory, planning, tool use and multi-agent systems. Prioritize peer-reviewed conference papers and strong preprints.",
    },
    {
        "name": "RESEARCH PAPERS - COMPUTER SCIENCE",
        "queries": [
            "2026 distributed systems database research papers",
            "2026 cybersecurity computer science research papers",
            "2026 efficient inference small language models research",
        ],
        "objective": "Find important new computer science research relevant to software engineering, systems, databases, security and efficient AI.",
    },
    {
        "name": "RESEARCH RESOURCES AND BENCHMARKS",
        "queries": [
            "New AI benchmarks datasets 2026",
            "New open source AI models datasets November 2026",
            "Important AI technical reports November 2026",
        ],
        "objective": "Discover valuable datasets, benchmarks, open-source models, technical reports, reproducible implementations and research resources.",
    },
]

def extract_search_results(search_result):
    """Parse JSON returned by Parallel's web_search tool."""
    extracted = []

    for content in search_result.get("results", []):
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            continue

        if isinstance(data, dict):
            extracted.extend(data.get("results", []))

    return extracted


def select_urls(search_result):
    """Select unique, valid URLs from a search category."""
    candidates = extract_search_results(search_result)

    selected = []
    seen = set()

    for item in candidates:
        url = item.get("url", "").strip()

        if not url:
            continue

        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            continue

        if url in seen:
            continue

        seen.add(url)
        selected.append(url)

        if len(selected) >= MAX_URLS_PER_TASK:
            break

    return selected


async def search_one(client, task):
    print(f"Searching: {task['name']}")

    try:
        result = await client.call_tool(
            "web_search",
            arguments={
                "search_queries": task["queries"],
                "objective": task["objective"],
            },
        )

        if result.is_error:
            return {"name": task["name"], "error": "Search failed"}

        content = [
            block.text
            for block in result.content
            if hasattr(block, "text")
        ]

        return {"name": task["name"], "results": content}

    except Exception as exc:
        return {"name": task["name"], "error": str(exc)}


async def fetch_one(client, task, search_result):
    urls = select_urls(search_result)

    if not urls:
        print(f"No usable URLs found for {task['name']}")
        return {"task": task["name"], "error": "No URLs found"}

    print(f"Fetching {len(urls)} pages: {task['name']}")

    try:
        result = await client.call_tool(
            "web_fetch",
            arguments={
                "urls": urls,
                "objective": task["objective"],
                "search_queries": task["queries"],
                "full_content": False,
                "allow_live_fetch": True,
            },
        )

        if result.is_error:
            return {"task": task["name"], "error": "Fetch failed"}

        content = [
            block.text
            for block in result.content
            if hasattr(block, "text")
        ]

        return {"task": task["name"], "content": content}

    except Exception as exc:
        return {"task": task["name"], "error": str(exc)}


async def main():
    print("Connecting to Parallel MCP...")

    async with Client(PARALLEL_URL) as client:
        print("Connected.")

        # Stage 1: Search all categories concurrently.
        print("\nSTAGE 1: SEARCH")
        search_results = await asyncio.gather(
            *[search_one(client, task) for task in SEARCH_TASKS]
        )

        # Stage 2: Fetch pages discovered by each search.
        print("\nSTAGE 2: FETCH")
        fetch_results = await asyncio.gather(
            *[
                fetch_one(client, task, search_result)
                for task, search_result in zip(SEARCH_TASKS, search_results)
                if "error" not in search_result
            ]
        )

    # Stage 3: Normalize fetched content.
    print("\nSTAGE 3: NORMALIZE")

    valid_results = [
        result for result in fetch_results
        if "content" in result
    ]

    normalized = normalize_fetch_results(valid_results)

    # Stage 4: Save the output.
    save_results(normalized, "data/normalized_results.json")

    print(f"\nPipeline completed. Saved {len(normalized)} records.")


if __name__ == "__main__":
    asyncio.run(main())
