"""Small local CLI entry point for runtime and Ollama inspection."""

from __future__ import annotations

import argparse
from pathlib import Path
import asyncio
import json

from app.config import Settings
from app.llm import LocalModelError, ModelInfo, OllamaProvider
from app.agent.research import ResearchAgent, render_markdown
from app.mcp.retrieval import RetrievalError
from app.mcp.retrieval import ParallelWebRetriever
from app.mcp.diagnostic_runner import run_mcp_diagnostic_process
from app.llm_runtime import discover_installed_models
from app.web import serve


async def show_models(*, json_worker: bool = False) -> int:
    settings = Settings.from_env()
    try:
        if json_worker:
            provider = OllamaProvider(host=settings.ollama_host, timeout=settings.ollama_timeout)
            models = await provider.list_models()
            print(json.dumps({"models": [model.name for model in models]}))
            return 0
        model_names = discover_installed_models(settings)
        models = [ModelInfo(name=name) for name in model_names]
        if not models:
            print("Ollama is reachable, but no local models are installed.")
            return 1
        print("Installed local Ollama models:")
        for model in models:
            size = f" ({model.size / 1_000_000_000:.1f} GB)" if model.size else ""
            preferred = " [configured]" if model.name == settings.ollama_model else ""
            print(f"- {model.name}{size}{preferred}")
        if settings.ollama_model:
            if settings.ollama_model not in model_names:
                print(f"Configured model '{settings.ollama_model}' is not installed locally.")
                return 1
            print(f"Configured model is available: {settings.ollama_model}")
        else:
            print(f"Default selection: {models[0].name} (set OLLAMA_MODEL to choose another)")
        return 0
    except (LocalModelError, RuntimeError, TimeoutError) as exc:
        if json_worker:
            print(json.dumps({"error": str(exc)}))
            return 1
        print(f"Local LLM unavailable: {exc}")
        return 1


async def run_research(request: str, fetch_limit: int) -> int:
    if not request.strip():
        print("A research request is required.")
        return 2
    try:
        result = await ResearchAgent().research(request, fetch_limit=fetch_limit)
        print(render_markdown(result))
        return 0
    except (LocalModelError, RetrievalError, ValueError) as exc:
        print(f"Research failed: {exc}")
        return 1


def run_mcp_diagnostics(*, worker: bool = False) -> int:
    settings = Settings.from_env()
    report = (asyncio.run(ParallelWebRetriever(settings=settings).diagnostics("latest developments in AI agents"))
              if worker else run_mcp_diagnostic_process(settings))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("ok") else 1


def main() -> int:
    parser = argparse.ArgumentParser(prog="daily-intelligence")
    commands = parser.add_subparsers(dest="command", required=True)
    models = commands.add_parser("models", help="Inspect local Ollama models")
    models.add_argument("--json-worker", action="store_true", help=argparse.SUPPRESS)
    serve_parser = commands.add_parser("serve", help="Start the local desktop interface")
    serve_parser.add_argument("--no-browser", action="store_true", help="Do not open a browser window")
    serve_parser.add_argument("--idle-timeout", type=float, default=None,
                              help="Stop after this many seconds without UI activity (launcher mode)")
    serve_parser.add_argument("--pid-file", type=Path, default=None)
    diagnostics = commands.add_parser("diagnostics", help="Check external service integrations")
    diagnostic_commands = diagnostics.add_subparsers(dest="diagnostic", required=True)
    mcp_diagnostic = diagnostic_commands.add_parser("mcp", help="Run live Parallel MCP discovery, search and fetch")
    mcp_diagnostic.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    research = commands.add_parser("research", help="Research an arbitrary question using local Ollama and Parallel MCP")
    research.add_argument("request", nargs="+", help="Question or research request")
    research.add_argument("--fetch-limit", type=int, default=5)
    args = parser.parse_args()
    if args.command == "models":
        return asyncio.run(show_models(json_worker=args.json_worker))
    if args.command == "serve":
        try:
            return int(serve(open_browser=not args.no_browser, idle_timeout=args.idle_timeout,
                             pid_file=args.pid_file) or 0)
        except OSError as exc:
            print(f"Local interface could not start on 127.0.0.1:{Settings.from_env().port}: {type(exc).__name__}: {exc}")
            return 1
    if args.command == "diagnostics" and args.diagnostic == "mcp":
        return run_mcp_diagnostics(worker=args.worker)
    if args.command == "research":
        return asyncio.run(run_research(" ".join(args.request), args.fetch_limit))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
