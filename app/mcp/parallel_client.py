
import asyncio
from mcp import Client

PARALLEL_URL = "https://mcp.parallel.ai/mcp"


async def main():
    print("Connecting to Parallel MCP...")

    async with Client(PARALLEL_URL) as client:

        print("\nConnected successfully!")

        result = await client.list_tools()

        print("\nAvailable Parallel MCP tools:")
        for tool in result.tools:
            print(f"  - {tool.name}: {tool.description}")

        print("\nTesting web search...")

        search_result = await client.call_tool(
            "web_search",
            {
                "search_queries": [
                    "Official GATE 2027 examination notifications"
                    "Tesla rocket car"
                ],
                "objective": (
                    "Find official GATE 2027 examination "
                    "announcements and important dates."
                    "to know about Tesla's rocket car project."
                )
            }
        )

        print("\nSearch results:")

        for item in search_result.content:
            if item.type == "text":
                print(item.text)

        if search_result.is_error:
            raise RuntimeError("Parallel search returned an error")

        print("\nParallel MCP test completed.")


if __name__ == "__main__":
    asyncio.run(main())
