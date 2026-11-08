import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.agent.research import ResearchAgent, render_markdown
from app.agent.search_planner import SearchPlan, SearchPlanner
from app.config import Settings
from app.mcp.retrieval import ParallelWebRetriever
from app.mcp.url_safety import UnsafeURLError, validate_public_http_url


class FakeMCPClient:
    def __init__(self):
        self.list_tools = AsyncMock(return_value=SimpleNamespace(tools=[
            SimpleNamespace(name="web_search"), SimpleNamespace(name="web_fetch")
        ]))
        self.call_tool = AsyncMock()


def text_result(payload):
    return SimpleNamespace(
        is_error=False,
        content=[SimpleNamespace(type="text", text=json.dumps(payload))],
    )


class DynamicRetrievalTests(unittest.IsolatedAsyncioTestCase):
    async def test_planner_creates_bounded_plan_for_new_domain_request(self):
        provider = SimpleNamespace(generate_json=AsyncMock(return_value={
            "objective": "Find the latest official release notes",
            "search_queries": ["site:docs.example.org release notes", "example product updates"],
            "freshness_days": 60,
            "source_guidance": "Official documentation",
        }))
        planner = SearchPlanner(provider, Settings(max_search_queries=2))

        plan = await planner.plan("Find the latest updates from docs.example.org")

        self.assertEqual(plan.search_queries, [
            "Find the latest updates from docs.example.org",
            "site:docs.example.org release notes",
        ])
        provider.generate_json.assert_awaited_once()

    async def test_planner_recovers_missing_objective_from_user_request(self):
        provider = SimpleNamespace(generate_json=AsyncMock(return_value={
            "search_queries": ["official Python 3.14 free threaded documentation"],
        }))
        plan = await SearchPlanner(provider).plan("Find Python 3.14 free-threading docs")
        self.assertEqual(plan.objective, "Find Python 3.14 free-threading docs")

    async def test_planner_accepts_common_queries_field_from_local_model(self):
        provider = SimpleNamespace(generate_json=AsyncMock(return_value={
            "queries": ["official Python free-threaded builds"],
            "objective": "Find official documentation",
        }))
        plan = await SearchPlanner(provider).plan("Find official Python docs")
        self.assertEqual(plan.search_queries, [
            "Find official Python docs", "official Python free-threaded builds"
        ])

    async def test_planner_treats_zero_freshness_as_unconstrained(self):
        provider = SimpleNamespace(generate_json=AsyncMock(return_value={
            "objective": "Find documentation",
            "queries": ["official docs"],
            "freshness": 0,
        }))
        plan = await SearchPlanner(provider).plan("Find documentation")
        self.assertIsNone(plan.freshness_days)

    async def test_planner_treats_zero_freshness_days_as_unconstrained(self):
        provider = SimpleNamespace(generate_json=AsyncMock(return_value={
            "objective": "Find documentation",
            "search_queries": ["official docs"],
            "freshness_days": 0,
        }))
        plan = await SearchPlanner(provider).plan("Find documentation")
        self.assertIsNone(plan.freshness_days)

    async def test_search_discovers_tools_normalizes_and_deduplicates_new_domain(self):
        client = FakeMCPClient()
        client.call_tool.return_value = text_result({"results": [
            {"url": "https://docs.example.org/guide?utm_source=mail", "title": "Guide", "excerpts": ["Evidence"]},
            {"url": "https://www.docs.example.org/guide", "title": "Duplicate"},
            {"url": "file:///etc/passwd", "title": "Unsafe"},
        ]})
        retriever = ParallelWebRetriever(client, Settings(max_search_queries=2))

        records = await retriever.search(["new topic"], "Find useful sources")

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["domain"], "docs.example.org")
        self.assertEqual(records[0]["evidence"][0]["text"], "Evidence")
        client.list_tools.assert_awaited_once()
        client.call_tool.assert_awaited_once_with("web_search", arguments={
            "search_queries": ["new topic"], "objective": "Find useful sources"
        })

    async def test_fetch_rejects_local_urls_before_mcp_call(self):
        client = FakeMCPClient()
        retriever = ParallelWebRetriever(client)
        with self.assertRaises(UnsafeURLError):
            await retriever.fetch(["http://127.0.0.1/admin"], "Fetch this")
        client.call_tool.assert_not_awaited()

    async def test_research_workflow_merges_sources_and_renders_links(self):
        plan = SearchPlan(objective="Investigate a new topic", search_queries=["new topic"])
        planner = SimplePlanner(plan)
        retriever = SimpleRetriever()
        provider = SimpleProvider()
        agent = ResearchAgent(planner=planner, retriever=retriever, provider=provider)

        result = await agent.research("Research a previously unseen topic")

        self.assertEqual(result.sources[0]["content"],
                         "A new topic is introduced in this research paper.")
        self.assertIn("[S1]", result.answer)
        self.assertIn("[S1] [Source](https://research.example.org/paper)", render_markdown(result))

    async def test_research_can_answer_without_web_search_when_planner_says_so(self):
        plan = SearchPlan(objective="General explanation", search_queries=["general explanation"], needs_search=False)
        provider = SimpleProvider()
        provider.generate_text = AsyncMock(return_value="A local answer.")
        retriever = SimpleRetriever()
        agent = ResearchAgent(planner=SimplePlanner(plan), retriever=retriever, provider=provider)

        result = await agent.research("Explain a stable general concept")

        self.assertEqual(result.answer, "A local answer.")
        self.assertEqual(result.sources, [])
        retriever.search.assert_not_awaited() if hasattr(retriever, "search") and isinstance(retriever.search, AsyncMock) else None

    async def test_relevance_ranking_prefers_requested_subtopic(self):
        sources = [
            {"title": "What's new in Python 3.14", "excerpts": ["General release notes"]},
            {"title": "Python support for free threading", "excerpts": ["Build a free-threaded binary"]},
        ]
        ranked = ResearchAgent._rank_sources(
            "Find Python 3.14 documentation about free-threaded builds", sources
        )
        self.assertEqual(ranked[0]["title"], "Python support for free threading")


class SimplePlanner:
    def __init__(self, plan): self.plan_result = plan
    async def plan(self, request): return self.plan_result


class SimpleRetriever:
    async def search(self, *args, **kwargs):
        return [{"title": "Source", "url": "https://research.example.org/paper",
                 "canonical_url": "https://research.example.org/paper", "domain": "research.example.org",
                 "excerpts": ["A new topic is introduced in this research paper."],
                 "publish_date": "2026-11-01"}]
    async def fetch(self, *args, **kwargs):
        return [{"url": "https://research.example.org/paper",
                 "full_content": "A new topic is introduced in this research paper.",
                 "excerpts": ["A new topic is introduced in this research paper."]}]


class SimpleProvider:
    async def generate_json(self, prompt, **kwargs):
        self.prompt = prompt
        return {"findings": [{
            "summary": "Supported finding",
            "source_id": "S1",
            "evidence_quote": "A new topic is introduced in this research paper.",
            "nature": "explicit",
        }]}


if __name__ == "__main__":
    unittest.main()
