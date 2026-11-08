
import asyncio
import json

from pathlib import Path
from mcp import Client


PARALLEL_URL = "https://mcp.parallel.ai/mcp"

INPUT_FILE = "data/filtered_results.json"
OUTPUT_FILE = "data/job_source_results.json"


# These are the primary sources for our first extraction test.
TARGET_DOMAINS = {
    "iocl.com",
    "isro.gov.in",
    "recruitment.nic.in",
    "getfirsthire.com",
    "jobs.ametek.com",
    "rezifi.com",
}


FETCH_OBJECTIVE = """
Retrieve the recruitment information from the supplied sources.

For recruitment advertisements, extract the available information about:
- Recruiting organization
- Exact post or job title
- Number of vacancies
- Educational qualifications
- Eligible engineering disciplines
- Whether Computer Science or Information Technology is eligible
- Required work experience
- Age limit
- Job location
- Salary or pay scale
- Application opening date
- Application closing date
- Selection process
- Official application URL

For private job pages, extract:
- Employer
- Job title
- Required skills
- Educational qualifications
- Experience requirements
- Location or remote status
- Salary, if published
- Application link
- Current application status, if explicitly stated

Do not infer missing information.
Do not assume that CSE graduates are eligible unless the source explicitly says so.
Preserve exact dates and qualification wording.

If a source is a result notice, cutoff document, or general portal
rather than a vacancy advertisement, identify its document type.
"""


async def fetch_sources(client, records):

    urls = [
        record["url"]
        for record in records
    ]

    print(f"Fetching {len(urls)} primary sources...")

    result = await client.call_tool(
        "web_fetch",
        arguments={
            "urls": urls,
            "objective": FETCH_OBJECTIVE,
            "search_queries": [
                "IOCL 2026 recruitment detailed advertisement eligibility",
                "ISRO Scientist Engineer SC recruitment eligibility",
                "NIC Scientific Technical Assistant 2026 detailed advertisement",
                "Associate AI Engineer Staples India Chennai job",
                "AMETEK AI Engineer Developer Bangalore job",
                "Rezifi Junior AI Engineer India job",
            ],
            "full_content": True,
            "allow_live_fetch": True,
        },
    )

    if result.is_error:
        raise RuntimeError("Parallel MCP web_fetch returned an error")

    content = []

    for block in result.content:
        if hasattr(block, "text"):
            content.append(block.text)

    return content


def select_primary_sources(data):

    records = data.get("jobs", []) + data.get("job_sources", [])

    selected = []
    seen = set()

    for record in records:

        url = record.get("url", "")

        if not url:
            continue

        domain = (
            url.split("//")[-1]
            .split("/")[0]
            .lower()
            .removeprefix("www.")
        )

        if domain not in TARGET_DOMAINS:
            continue

        if url in seen:
            continue

        seen.add(url)
        selected.append(record)

    return selected


async def main():

    input_path = Path(INPUT_FILE)

    if not input_path.exists():
        raise FileNotFoundError(INPUT_FILE)

    with input_path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    records = select_primary_sources(data)

    if not records:
        print("No matching primary sources found.")
        return

    print("\nSELECTED SOURCES")

    for index, record in enumerate(records, 1):
        print(
            f"{index}. {record.get('title')} "
            f"| {record.get('url')}"
        )

    print("\nConnecting to Parallel MCP...")

    async with Client(PARALLEL_URL) as client:

        print("Connected.")

        content = await fetch_sources(client, records)

    output = {
        "generated_at": __import__("datetime").datetime.now().astimezone().isoformat(),
        "source_count": len(records),
        "sources": records,
        "fetch_content": content,
    }

    output_path = Path(OUTPUT_FILE)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        json.dump(
            output,
            file,
            indent=2,
            ensure_ascii=False,
        )

    print("\nJOB SOURCE FETCH COMPLETE")
    print(f"Sources selected: {len(records)}")
    print(f"Content blocks received: {len(content)}")
    print(f"Saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
