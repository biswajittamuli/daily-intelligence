"""Environment-backed application settings; secrets stay outside source control."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    ollama_host: str = "http://localhost:11434"
    ollama_model: str | None = None
    ollama_timeout: float = 120.0
    parallel_mcp_url: str = "https://mcp.parallel.ai/mcp"
    data_dir: Path = Path("data")
    notes_dir: Path = Path("notes")
    max_tool_calls: int = 12
    max_search_queries: int = 8
    max_fetch_urls: int = 8
    max_content_chars: int = 120_000
    mcp_timeout: float = 25.0
    max_agent_iterations: int = 2
    max_llm_calls: int = 3
    host: str = "127.0.0.1"
    port: int = 8765

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            ollama_host=os.getenv("OLLAMA_HOST", cls.ollama_host),
            ollama_model=os.getenv("OLLAMA_MODEL") or None,
            ollama_timeout=float(os.getenv("OLLAMA_TIMEOUT", cls.ollama_timeout)),
            parallel_mcp_url=os.getenv("PARALLEL_MCP_URL", cls.parallel_mcp_url),
            data_dir=Path(os.getenv("DAILY_INTELLIGENCE_DATA_DIR", "data")).expanduser(),
            notes_dir=Path(os.getenv("DAILY_INTELLIGENCE_NOTES_DIR", "notes")).expanduser(),
            max_tool_calls=int(os.getenv("AGENT_MAX_TOOL_CALLS", "12")),
            max_search_queries=int(os.getenv("AGENT_MAX_SEARCH_QUERIES", "8")),
            max_fetch_urls=int(os.getenv("AGENT_MAX_FETCH_URLS", "8")),
            max_content_chars=int(os.getenv("AGENT_MAX_CONTENT_CHARS", "120000")),
            mcp_timeout=float(os.getenv("MCP_TIMEOUT", "25")),
            max_agent_iterations=int(os.getenv("AGENT_MAX_ITERATIONS", "2")),
            max_llm_calls=int(os.getenv("AGENT_MAX_LLM_CALLS", "3")),
            # The interface intentionally binds only to loopback so personal
            # planning data cannot be exposed by an environment override.
            host="127.0.0.1",
            port=int(os.getenv("DAILY_INTELLIGENCE_PORT", "8765")),
        )
