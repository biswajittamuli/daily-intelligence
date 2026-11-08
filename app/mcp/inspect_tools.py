\
import asyncio
import json
from mcp import Client

URL = "https://mcp.parallel.ai/mcp"

async def main():
    async with Client(URL) as client:
        tools = await client.list_tools()

        for tool in tools.tools:
            if tool.name in ("web_search", "web_fetch"):
                print("\n" + "=" * 60)
                print(tool.name)
                print("=" * 60)

                print(json.dumps(
                    tool.model_dump(),
                    indent=2,
                    default=str
                ))

if __name__ == "__main__":
    asyncio.run(main())

