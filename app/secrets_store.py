"""Locally stored API keys (v4.3).

Keys pasted in Settings → API keys are written to ``<data dir>/secrets.json`` with owner-only permissions (0600).
They are never returned to the browser (only a masked hint), never logged and never committed (``data/`` is
git-ignored). At startup and whenever a key is saved or removed, saved keys are applied to this process's
environment, so every component that reads its key from the environment (job APIs, Firecrawl, the Parallel MCP
client and the MCP diagnostic child process) uses the new key immediately, without a restart.

Precedence: a key saved here overrides an environment variable of the same name. Removing a saved key restores
the environment value the app started with (if any).
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any

# name -> label shown in the UI
SECRET_NAMES = {
    "JOOBLE_API_KEY": "API key",
    "FINDWORK_API_KEY": "API key",
    "FIRECRAWL_API_KEY": "API key",
    "PARALLEL_MCP_AUTH_TOKEN": "API key / bearer token",
}

PROVIDERS: list[dict[str, Any]] = [
    {"id": "jooble", "name": "Jooble", "keys": ["JOOBLE_API_KEY"],
     "signup": "https://jooble.org/api/about",
     "purpose": "Job search engine that indexes Indian job portals and company sites, so it reaches listings "
                "that LinkedIn, Naukri and others also carry, without fetching those portals.",
     "cost": "Free key (request form, no card); this app makes at most 4 searches per discovery run",
     "sends": "Role titles and a location"},
    {"id": "findwork", "name": "Findwork", "keys": ["FINDWORK_API_KEY"],
     "signup": "https://findwork.dev/developers/",
     "purpose": "Developer job board with remote and on-site software roles.",
     "cost": "Free key (sign-up, no card); at most 3 searches per discovery run",
     "sends": "Role titles and a location"},
    {"id": "firecrawl", "name": "Firecrawl", "keys": ["FIRECRAWL_API_KEY"],
     "signup": "https://www.firecrawl.dev/signin/signup",
     "purpose": "Renders employer career pages that need JavaScript when the local browser cannot read them.",
     "cost": "Free credits on sign-up, then paid", "sends": "Public employer career-page URLs only"},
    {"id": "parallel", "name": "Parallel web search (MCP)", "keys": ["PARALLEL_MCP_AUTH_TOKEN"],
     "signup": "https://platform.parallel.ai",
     "purpose": "Optional: an API key raises the free search tier's rate limits. Search works without it.",
     "cost": "Free tier without a key; key plans per Parallel", "sends": "Search queries (role titles, locations)"},
]
BY_PROVIDER = {p["id"]: p for p in PROVIDERS}

_VALUE = re.compile(r"^[A-Za-z0-9._~+/=:\-]{4,300}$")
_lock = threading.Lock()
_original_env: dict[str, str | None] = {}
_applied: set[str] = set()


def _path(data_dir: Path | None = None) -> Path:
    if data_dir is None:
        from app.config import Settings
        data_dir = Settings.from_env().data_dir
    return Path(data_dir) / "secrets.json"


def _read(data_dir: Path | None = None) -> dict[str, str]:
    path = _path(data_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: str(v) for k, v in data.items() if k in SECRET_NAMES and isinstance(v, str) and v}


def _write(values: dict[str, str], data_dir: Path | None = None) -> None:
    path = _path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".secrets-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(values, handle)
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def validate_value(name: str, value: Any) -> str:
    if name not in SECRET_NAMES:
        raise ValueError(f"Unknown key name: {name}")
    text = str(value or "").strip()
    if not _VALUE.match(text):
        raise ValueError("That does not look like a key: paste it without spaces or line breaks (4–300 characters)")
    return text


def apply_to_environment(data_dir: Path | None = None) -> None:
    """Make saved keys visible to os.getenv (and child processes); restore env values for removed keys."""
    with _lock:
        saved = _read(data_dir)
        for name in SECRET_NAMES:
            if name not in _original_env:
                _original_env[name] = os.environ.get(name)
            if name in saved:
                os.environ[name] = saved[name]
                _applied.add(name)
            elif name in _applied:
                original = _original_env.get(name)
                if original is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = original
                _applied.discard(name)


def save(values: dict[str, Any], data_dir: Path | None = None) -> None:
    """Validate and store one or more keys (all or nothing), then apply them."""
    clean = {name: validate_value(name, value) for name, value in values.items()}
    with _lock:
        current = _read(data_dir)
        current.update(clean)
        _write(current, data_dir)
    apply_to_environment(data_dir)


def remove(names: list[str], data_dir: Path | None = None) -> None:
    with _lock:
        current = _read(data_dir)
        for name in names:
            current.pop(name, None)
        _write(current, data_dir)
    apply_to_environment(data_dir)


def mask(value: str | None) -> str | None:
    if not value:
        return None
    return ("•" * 6) + value[-4:] if len(value) > 8 else "•" * 6


def status(data_dir: Path | None = None) -> list[dict[str, Any]]:
    """Per provider: which keys are present and where from. Never includes a key itself."""
    saved = _read(data_dir)
    output = []
    for provider in PROVIDERS:
        keys = []
        for name in provider["keys"]:
            value = saved.get(name) or os.environ.get(name)
            source = "saved" if name in saved else ("environment" if os.environ.get(name) else None)
            keys.append({"name": name, "label": SECRET_NAMES[name], "set": bool(value), "source": source,
                         "hint": mask(value)})
        output.append({**{k: provider[k] for k in ("id", "name", "signup", "purpose", "cost", "sends")},
                       "keys": keys, "configured": all(k["set"] for k in keys)})
    return output


def redact(text: str) -> str:
    """Remove any saved or environment key value from a message."""
    value = str(text)
    for name in SECRET_NAMES:
        secret = os.environ.get(name)
        if secret and len(secret) >= 4:
            value = value.replace(secret, "[redacted]")
    return value
