"""Bounded Ollama model discovery isolated from stuck local HTTP transports."""
from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

from app.config import Settings


def discover_installed_models(settings: Settings, *, timeout: float | None = None) -> list[str]:
    hard_timeout = max(2.0, min(30.0, timeout or settings.ollama_timeout))
    command = [sys.executable, "-m", "app.main", "models", "--json-worker"]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=hard_timeout,
                                   env=None, check=False)
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"Ollama model discovery exceeded {hard_timeout:g}s") from exc
    try:
        response: dict[str, Any] = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Ollama model discovery worker returned invalid JSON") from exc
    if completed.returncode != 0 or response.get("error"):
        raise RuntimeError(str(response.get("error") or "Ollama model discovery failed"))
    models = response.get("models", [])
    return [str(name) for name in models if isinstance(name, str)]
