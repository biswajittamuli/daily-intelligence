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


def _store():
    from app.memory.store import Store
    return Store(Settings.from_env().data_dir)


def run_discover(request: str, mode: str) -> int:
    """Run one full discovery (jobs, government, exams, re-verification) without the UI, then print the report."""
    from app.services.broad_search import rescore_stored
    from app.services.orchestrator import DiscoveryOrchestrator
    from app.services.preferences import load_preferences

    settings = Settings.from_env()
    store = _store()
    preferences = load_preferences(store)
    report = asyncio.run(DiscoveryOrchestrator(settings, store, preferences).discover(
        request, mode=mode, progress=lambda message: print(f"  · {message}", flush=True)))
    rescore_stored(store, preferences)
    print(json.dumps({"metrics": report.get("metrics"), "adapters": report.get("adapters"),
                      "reverify": report.get("reverify"), "session_id": report.get("session_id")}, indent=2))
    return 0


def run_careers(limit: int) -> int:
    """Seed the built-in employer lists, then run careers-page discovery for employers that are due."""
    from app.web import Application

    app = Application(Settings.from_env())
    try:
        app.seed_employers()
        result = asyncio.run(app.rediscover_careers(limit=limit, progress=lambda m: print(f"  · {m}", flush=True)))
    finally:
        app._executor.shutdown(wait=False)
    for row in result.get("details") or []:
        print(f"{row['employer'][:28]:28} {str(row.get('outcome'))[:30]:30} {str(row.get('ats') or '')[:16]:16} "
              f"{row.get('listings') or 0:4}  {row.get('career_url') or ''}")
    print(json.dumps({"employers": result.get("employers"), "outcomes": result.get("outcomes")}, indent=2))
    return 0


def sources_report(as_json: bool) -> int:
    """Source-by-source health of the most recent discovery run, joined with persisted reliability."""
    store = _store()
    session = next((s for s in store.search_sessions(60) if s.get("category") == "discovery" and s.get("summary")), None)
    if session is None:
        print("No discovery run recorded yet. Run: python -m app.main discover")
        return 1
    sources = session["summary"].get("sources") or []
    if as_json:
        print(json.dumps({"run_at": session.get("created_at"), "sources": sources}, indent=2))
        return 0
    print(f"Discovery run {session.get('created_at')}")
    print(f"{'source':30} {'method':36} {'state':34} {'results':>7} {'vacancies':>9} {'unique':>6} "
          f"{'stored':>6} {'verified':>8} {'rejected':>8}  last success / reason")
    for row in sources:
        tail = row.get("reason") or (str(row.get("last_success_at") or "")[:16] or "")
        print(f"{row['name'][:30]:30} {str(row.get('method') or '')[:36]:36} {row['state_label'][:34]:34} "
              f"{row.get('results', 0):>7} {row.get('listings', 0):>9} {row.get('unique', 0):>6} "
              f"{row.get('stored', 0):>6} {row.get('verified', 0):>8} {row.get('rejected', 0):>8}  {tail[:90]}")
    metrics = session["summary"].get("metrics") or {}
    print("\n" + ", ".join(f"{k}={v}" for k, v in metrics.items()))
    return 0


def main() -> int:
    from app import secrets_store
    secrets_store.apply_to_environment()  # keys saved in Settings → API keys apply to CLI runs too
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
    discover = commands.add_parser("discover", help="Run one full discovery without the UI and print the report")
    discover.add_argument("request", nargs="*", help="Optional request, e.g. 'AI engineer internships'")
    discover.add_argument("--mode", default="full")
    careers = commands.add_parser("careers", help="Find and verify careers pages for built-in and discovered employers")
    careers.add_argument("--limit", type=int, default=100, help="Employers to check in this run (default 100)")
    report = commands.add_parser("sources-report", help="Source-by-source health of the last discovery run")
    report.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.command == "discover":
        return run_discover(" ".join(args.request), args.mode)
    if args.command == "careers":
        return run_careers(max(1, min(500, args.limit)))
    if args.command == "sources-report":
        return sources_report(args.json)
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
