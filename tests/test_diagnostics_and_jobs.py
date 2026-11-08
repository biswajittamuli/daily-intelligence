import asyncio
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.agent.briefing import BriefingService
from app.agent.research import ResearchResult
from app.agent.search_planner import SearchPlan
from app.config import Settings
from app.llm import LocalModelError, OllamaProvider
from app.mcp.retrieval import ParallelWebRetriever
from app.mcp.diagnostic_runner import run_mcp_diagnostic_process
from app.web import Application, STATIC_DIR


def result(payload, error=False):
    return SimpleNamespace(is_error=error, content=[SimpleNamespace(type="text", text=json.dumps(payload))])


class DiagnosticClient:
    def __init__(self, *, connection_error=False, tools=None, search_error=False,
                 fetch_error=False, mismatch=False, empty=False, discovery_delay=0,
                 excerpt_only=False, first_empty=False):
        self.connection_error = connection_error
        self.list_tools = AsyncMock(side_effect=self._tools)
        self.call_tool = AsyncMock(side_effect=self._call)
        self.tools = tools or [SimpleNamespace(name="web_search"), SimpleNamespace(name="web_fetch")]
        self.search_error, self.fetch_error = search_error, fetch_error
        self.mismatch, self.empty, self.discovery_delay = mismatch, empty, discovery_delay
        self.excerpt_only, self.first_empty = excerpt_only, first_empty

    async def __aenter__(self):
        if self.connection_error:
            raise OSError("connection refused")
        return self

    async def __aexit__(self, *args):
        return None

    async def _tools(self):
        if self.discovery_delay:
            await asyncio.sleep(self.discovery_delay)
        return SimpleNamespace(tools=self.tools)

    async def _call(self, name, arguments):
        if name == "web_search":
            results = [{"title": "AI agents update", "url": "https://example.org/agents",
                        "excerpts": ["A current agent update."]}]
            if self.empty:
                results = []
            elif self.first_empty:
                results.insert(0, {"title": "Blocked page", "url": "https://example.org/blocked",
                                   "excerpts": ["Blocked result excerpt."]})
            return result({"results": results}, self.search_error)
        fetched = []
        for url in arguments.get("urls", ["https://example.org/agents"]):
            fetched_url = "https://other.example.org/page" if self.mismatch else url
            if self.first_empty and "blocked" in url:
                fetched.append({"url": fetched_url, "title": "Blocked page",
                                "full_content": "", "excerpts": []})
            elif self.excerpt_only:
                fetched.append({"url": fetched_url, "title": "Fetched AI agents page",
                                "full_content": "", "excerpts": ["Excerpt body about AI agents."]})
            else:
                fetched.append({"url": fetched_url, "title": "Fetched AI agents page",
                                "full_content": "Retrieved page body about AI agents."})
        return result({"results": fetched}, self.fetch_error)


class MCPDiagnosticTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_workflow_shape_search_fetch_and_url_correlation(self):
        client = DiagnosticClient()
        report = await ParallelWebRetriever(client, Settings(max_tool_calls=4)).diagnostics()
        self.assertTrue(report["ok"])
        self.assertEqual(report["search_result_count"], 1)
        self.assertEqual(report["page_title"], "Fetched AI agents page")
        self.assertTrue(report["url_match"])
        self.assertEqual(report["content_length"], len("Retrieved page body about AI agents."))
        self.assertEqual([x["status"] for x in report["stages"].values()], ["ok"] * 4)

    async def test_connection_failure_names_connection_stage(self):
        report = await ParallelWebRetriever(DiagnosticClient(connection_error=True)).diagnostics()
        self.assertFalse(report["ok"])
        self.assertEqual(report["failure_stage"], "connection")

    async def test_tool_discovery_failure_names_discovery_stage(self):
        tools = [SimpleNamespace(name="web_search")]
        report = await ParallelWebRetriever(DiagnosticClient(tools=tools)).diagnostics()
        self.assertFalse(report["ok"])
        self.assertEqual(report["failure_stage"], "tool_discovery")

    async def test_search_error_and_empty_search_name_the_search_stage(self):
        for client in (DiagnosticClient(search_error=True), DiagnosticClient(empty=True)):
            report = await ParallelWebRetriever(client).diagnostics()
            self.assertFalse(report["ok"])
            self.assertEqual(report["failure_stage"], "search")

    async def test_fetch_error_and_unrelated_url_name_the_fetch_stage(self):
        for client in (DiagnosticClient(fetch_error=True), DiagnosticClient(mismatch=True)):
            report = await ParallelWebRetriever(client).diagnostics()
            self.assertFalse(report["ok"])
            self.assertEqual(report["failure_stage"], "fetch")

    async def test_fetch_accepts_excerpts_when_full_content_is_empty(self):
        report = await ParallelWebRetriever(DiagnosticClient(excerpt_only=True)).diagnostics()
        self.assertTrue(report["ok"])
        self.assertEqual(report["content_source"], "excerpts")
        self.assertIn("Excerpt body", report["content_excerpt"])

    async def test_fetch_tries_other_results_when_first_page_is_empty(self):
        report = await ParallelWebRetriever(DiagnosticClient(first_empty=True)).diagnostics()
        self.assertTrue(report["ok"])
        self.assertEqual(report["requested_url"], "https://example.org/agents")
        self.assertEqual(len(report["fetch_attempted_urls"]), 2)

    async def test_discovery_timeout_is_reported(self):
        report = await ParallelWebRetriever(
            DiagnosticClient(discovery_delay=0.2), Settings(mcp_timeout=0.01)
        ).diagnostics()
        self.assertEqual(report["failure_stage"], "tool_discovery")
        self.assertIn("timed out", report["error"])

    def test_isolated_live_diagnostic_reports_real_endpoint_connectivity_failure(self):
        settings = Settings(parallel_mcp_url="https://mcp.example.test/mcp", mcp_timeout=5)
        with patch("app.mcp.diagnostic_runner.socket.create_connection", side_effect=PermissionError("blocked")):
            report = run_mcp_diagnostic_process(settings)
        self.assertEqual(report["failure_stage"], "connection")
        self.assertEqual(report["error_category"], "network")
        self.assertEqual(report["endpoint"], "https://mcp.example.test")


class LLMTimeoutTests(unittest.IsolatedAsyncioTestCase):
    async def test_generation_timeout_is_a_clear_local_model_error(self):
        provider = OllamaProvider(preferred_model=None, timeout=0.01)
        provider._client.list = AsyncMock(return_value={"models": [{"model": "local:test"}]})

        async def slow_chat(**kwargs):
            await asyncio.sleep(1)
        provider._client.chat = AsyncMock(side_effect=slow_chat)
        with self.assertRaisesRegex(LocalModelError, "timed out"):
            await provider.generate_text("brief prompt")

    async def test_thinking_is_disabled_for_thinking_models(self):
        provider = OllamaProvider(preferred_model=None, timeout=5)
        provider._client.list = AsyncMock(return_value={"models": [{"model": "qwen3:4b"}]})
        provider._client.show = AsyncMock(return_value={"capabilities": ["completion", "thinking"]})
        provider._client.chat = AsyncMock(return_value={"message": {"content": "ok"}})

        await provider.generate_text("brief prompt")

        self.assertIs(provider._client.chat.await_args.kwargs["think"], False)

    async def test_think_flag_is_omitted_for_non_thinking_models(self):
        provider = OllamaProvider(preferred_model=None, timeout=5)
        provider._client.list = AsyncMock(return_value={"models": [{"model": "llama3:8b"}]})
        provider._client.show = AsyncMock(return_value={"capabilities": ["completion"]})
        provider._client.chat = AsyncMock(return_value={"message": {"content": "ok"}})

        await provider.generate_text("brief prompt")

        self.assertNotIn("think", provider._client.chat.await_args.kwargs)


class StubAgent:
    def __init__(self, block=False):
        self.block = block
        self.calls = []

    async def research(self, request, **kwargs):
        self.calls.append((request, kwargs))
        if self.block:
            await asyncio.sleep(5)
        return ResearchResult(request, SearchPlan(search_queries=["one query"]), [], "Visible summary", [])


class BriefingJobTests(unittest.IsolatedAsyncioTestCase):
    async def test_briefing_reports_progress_and_uses_resource_caps(self):
        with tempfile.TemporaryDirectory() as tmp:
            notes = Path(tmp) / "notes"
            notes.mkdir()
            (notes / "today.md").write_text("- [ ] Finish report\n", encoding="utf-8")
            agent = StubAgent()
            service = BriefingService(Settings(data_dir=Path(tmp) / "data", notes_dir=notes), agent=agent)
            progress = []
            content = await service.generate(progress=progress.append)
            self.assertEqual(len(agent.calls), 1)
            self.assertEqual(agent.calls[0][1]["fetch_limit"], 2)
            self.assertFalse(agent.calls[0][1]["include_domain"])
            self.assertTrue(any("Planning" in p for p in progress))
            self.assertEqual(content["execution"]["llm_calls_max"], 2)
            self.assertEqual(content["priorities"][0]["text"], "Finish report")

    async def test_briefing_cancellation_stops_the_workflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = StubAgent(block=True)
            service = BriefingService(Settings(data_dir=Path(tmp), notes_dir=Path(tmp) / "notes"), agent=agent)
            event = threading.Event()
            task = asyncio.create_task(service.generate(cancel_event=event))
            await asyncio.sleep(0.05)
            event.set()
            with self.assertRaises(asyncio.CancelledError):
                await task

    async def test_duplicate_job_submission_is_rejected_and_cancel_works(self):
        class WaitingService:
            async def generate(self, *, progress, cancel_event):
                progress("Waiting for cancellation")
                while not cancel_event.is_set():
                    await asyncio.sleep(0.01)
                raise asyncio.CancelledError
        with tempfile.TemporaryDirectory() as tmp:
            app = Application(Settings(data_dir=Path(tmp), notes_dir=Path(tmp) / "notes"), service=WaitingService())
            job_id, _ = app.start_job("briefing")
            duplicate, active = app.start_job("briefing")
            self.assertIsNone(duplicate)
            self.assertEqual(active["id"], job_id)
            self.assertTrue(app.cancel_job(job_id))
            for _ in range(50):
                status = app.job_state(job_id)
                if status["status"] == "cancelled": break
                await asyncio.sleep(0.01)
            self.assertEqual(app.job_state(job_id)["status"], "cancelled")
            app._executor.shutdown(wait=True)

    def test_frontend_handles_api_errors_and_has_real_navigation(self):
        source = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
        self.assertIn("if(!res.ok)throw Error", source)
        self.assertIn("const NAV=", source)
        self.assertIn("pollJob", source)
        self.assertIn("cancelJob", source)


if __name__ == "__main__":
    unittest.main()
