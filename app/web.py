"""Loopback-only JSON API and static frontend for Daily Intelligence."""
from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import os
import re
import threading
import time
import uuid
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.agent.briefing import BriefingService
from app.config import Settings
from app.llm import LocalModelError, OllamaProvider
from app.llm_runtime import discover_installed_models
from app.mcp.diagnostic_runner import run_mcp_diagnostic_process
from app.memory.planning import read_planning_notes
from app.memory.store import Store
from app.services.discovery import CATEGORIES, DiscoveryEngine
from app.services.insights import job_market
from app.services.preferences import (
    load_preferences,
    save_preferences,
    validate_preferences,
)
from app.services.resume import extract_profile, extract_text

log = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"

ITEM_KINDS = {"job", "notice", "exam", "news", "paper"}


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """Cap lightweight API/static request handlers independently of long jobs."""
    daemon_threads = True
    request_slots = 16

    def __init__(self, *args, **kwargs):
        self._request_semaphore = threading.BoundedSemaphore(self.request_slots)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self._request_semaphore.acquire(blocking=False):
            body = b'{"error":"Server request capacity reached; retry shortly"}'
            response = (b"HTTP/1.1 503 Service Unavailable\r\nContent-Type: application/json\r\n"
                        + f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body)
            try: request.sendall(response)
            except OSError: pass
            finally: self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._request_semaphore.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._request_semaphore.release()


def _redact_error(message: str, settings: Settings) -> str:
    value = str(message)
    for key in ("PARALLEL_MCP_AUTH_TOKEN", "OLLAMA_API_KEY"):
        secret = os.getenv(key)
        if secret:
            value = value.replace(secret, "[redacted]")
    value = value.replace(settings.parallel_mcp_url, urlparse(settings.parallel_mcp_url).scheme + "://" + (urlparse(settings.parallel_mcp_url).hostname or "mcp"))
    return re.sub(r"(?i)(authorization|bearer)\s*[:=]?\s*[^\s,;]+", r"\1 [redacted]", value)


class Application:
    """Owns the service boundary, one background slot, and local API state."""

    def __init__(self, settings=None, service=None):
        self.settings = settings or Settings.from_env()
        self.store = Store(self.settings.data_dir)
        self.preferences_path = self.settings.data_dir / "settings.json"
        self.preferences = self._read_preferences()
        self.settings = self._settings_from_preferences(self.settings, self.preferences)
        self.discovery_preferences = load_preferences(self.store)
        self.service = service or BriefingService(self.settings, self.store)
        self._provided_service = service is not None
        self._apply_preferences_to_service()
        self._lock = threading.RLock()
        self._jobs: dict[str, dict] = {}
        self._active_job: str | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="daily-intel")

    def _apply_preferences_to_service(self):
        preference_text = " ".join(self.preferences.get(key, "") for key in ("location", "briefing_preferences")
                                   if self.preferences.get(key))
        if preference_text:
            self.service.briefing_request += f"\nPersonal preferences (use only as search relevance constraints): {preference_text}"

    def _read_preferences(self):
        try:
            value = json.loads(self.preferences_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _settings_from_preferences(base: Settings, saved: dict) -> Settings:
        try:
            return replace(base,
                ollama_model=saved.get("ollama_model") or base.ollama_model,
                max_search_queries=max(1, min(8, int(saved.get("max_search_queries", base.max_search_queries)))),
                max_fetch_urls=max(1, min(8, int(saved.get("max_fetch_urls", base.max_fetch_urls)))),
                max_content_chars=max(2_000, min(120_000, int(saved.get("max_content_chars", base.max_content_chars)))),
                notes_dir=Path(saved.get("notes_dir", base.notes_dir)).expanduser(),
                ollama_timeout=max(5, min(180, float(saved.get("ollama_timeout", base.ollama_timeout)))),
                mcp_timeout=max(5, min(60, float(saved.get("mcp_timeout", base.mcp_timeout))))
            )
        except (TypeError, ValueError):
            return base

    def public_settings(self):
        return {
            "ollama_host": self.settings.ollama_host,
            "ollama_model": self.settings.ollama_model or "",
            "max_search_queries": self.settings.max_search_queries,
            "max_fetch_urls": self.settings.max_fetch_urls,
            "max_content_chars": self.settings.max_content_chars,
            "notes_dir": str(self.settings.notes_dir),
            "ollama_timeout": self.settings.ollama_timeout,
            "mcp_timeout": self.settings.mcp_timeout,
            "location": self.preferences.get("location", ""),
            "briefing_preferences": self.preferences.get("briefing_preferences", ""),
            "theme": self.preferences.get("theme", "light"),
            "parallel_mcp_endpoint": self.settings.parallel_mcp_url,
        }

    def sync_planning_notes(self) -> dict:
        """Read local note files and import new tasks (idempotent)."""
        notes = read_planning_notes(self.settings.notes_dir, date.today())
        self.store.import_tasks(notes["tasks"])
        return notes

    def bootstrap(self):
        notes = self.sync_planning_notes()
        jobs = self.store.jobs(limit=500)
        return {
            "date": datetime.now().astimezone().date().isoformat(),
            "status": self.job_state(),
            "tasks": self.store.tasks(),
            "history": self.store.history(30),
            "briefings": self.store.briefings(10),
            "settings": self.public_settings(),
            "counts": self.store.counts(),
            "jobs": jobs[:40],
            "job_insights": job_market(jobs),
            "notices": self.store.notices(limit=40),
            "exams": self.store.exams(limit=60),
            "news": self.store.intel(category="news", limit=40),
            "papers": self.store.intel(category="papers", limit=40),
            "item_states": self.store.item_states(),
            "preferences": self.discovery_preferences,
            "watchlists": {
                "exam": self.store.watchlist("exam"),
                "organization": self.store.watchlist("organization"),
            },
            "profile": self.store.profile(),
            "planning": {
                "notes_dir": str(self.settings.notes_dir),
                "missing": notes["missing"],
                "files": notes["files"],
                "errors": notes["errors"],
                "tasks_found": len(notes["tasks"]),
            },
            "search_sessions": self.store.search_sessions(10),
        }

    def page(self):
        return (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    def job_state(self, job_id: str | None = None):
        with self._lock:
            if job_id:
                job = self._jobs.get(job_id)
                if not job: return None
                public = {k: v for k, v in job.items() if k not in {"cancel_event", "started_mono", "payload"}}
                if job.get("status") in {"queued", "running"} and job.get("started_mono"):
                    public["elapsed_seconds"] = round(time.monotonic()-job["started_mono"], 1)
                return public
            job = self._jobs.get(self._active_job) if self._active_job else None
            if not job: return {"status": "idle", "message": "Ready"}
            public = {k: v for k, v in job.items() if k not in {"cancel_event", "started_mono", "payload"}}
            if job.get("status") in {"queued", "running"} and job.get("started_mono"):
                public["elapsed_seconds"] = round(time.monotonic()-job["started_mono"], 1)
            return public

    def _progress(self, job_id: str, message: str):
        with self._lock:
            job = self._jobs.get(job_id)
            if job and job["status"] in {"queued", "running"}:
                job["message"] = message
                job["updated_at"] = datetime.now(timezone.utc).isoformat()
                job["elapsed_seconds"] = round(time.monotonic() - job["started_mono"], 1)
        log.info("job=%s progress=%s elapsed=%.1fs", job_id[:8], message,
                 time.monotonic() - self._jobs[job_id]["started_mono"])

    def start_job(self, kind: str, request: str = "", payload: dict | None = None):
        with self._lock:
            if self._active_job:
                active = self._jobs.get(self._active_job)
                if active and active["status"] in {"queued", "running"}:
                    return None, self.job_state(self._active_job)
            for old_id in list(self._jobs):
                if len(self._jobs) < 100:
                    break
                if self._jobs[old_id].get("status") not in {"queued", "running"}:
                    self._jobs.pop(old_id, None)
            job_id = uuid.uuid4().hex
            job = {"id": job_id, "kind": kind, "status": "queued", "message": "Queued",
                   "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat(),
                   "started_mono": time.monotonic(), "cancel_event": threading.Event(), "result": None, "error": None,
                   "payload": payload or {}}
            self._jobs[job_id] = job
            self._active_job = job_id
            log.info("job=%s accepted kind=%s", job_id[:8], kind)
            self._executor.submit(self._run_job, job_id, request)
            return job_id, None

    def _run_job(self, job_id: str, request: str):
        with self._lock:
            job = self._jobs[job_id]
            job["status"] = "running"
            job["message"] = "Starting"
        started = time.monotonic()
        try:
            if job["kind"] == "discovery":
                payload = job.get("payload") or {}
                category = str(payload.get("category") or "").strip()
                if category not in CATEGORIES:
                    raise ValueError(f"Unsupported discovery category: {category}")
                engine = DiscoveryEngine(self.settings, self.store,
                                         preferences=self.discovery_preferences)
                self._progress(job_id, f"Starting {category} discovery")
                result = asyncio.run(engine.run(
                    category, str(payload.get("query") or "").strip(),
                    progress=lambda message: self._progress(job_id, message),
                    cancel_event=job["cancel_event"],
                    freshness=payload.get("freshness"),
                    region=str(payload.get("region") or ""),
                    topic=str(payload.get("topic") or ""),
                ))
            else:
                service = self.service if self._provided_service else BriefingService(self.settings, self.store)
                preferences = " ".join(self.preferences.get(key, "") for key in ("location", "briefing_preferences")
                                        if self.preferences.get(key))
                if preferences:
                    service.briefing_request += f"\nPersonal preferences (search relevance only): {preferences}"
                if job["kind"] == "briefing":
                    result = asyncio.run(service.generate(
                        progress=lambda message: self._progress(job_id, message),
                        cancel_event=job["cancel_event"]))
                elif job["kind"] == "research":
                    self._progress(job_id, "Researching your request")
                    result = asyncio.run(service.ask(request, cancel_event=job["cancel_event"]))
                elif job["kind"] == "mcp_diagnostics":
                    self._progress(job_id, "Connecting to Parallel MCP")
                    result = run_mcp_diagnostic_process(self.settings, job["cancel_event"])
                else:
                    raise ValueError("Unknown job type")
            with self._lock:
                job["result"] = result
                job["status"] = "complete" if not job["cancel_event"].is_set() else "cancelled"
                job["message"] = "Complete" if job["status"] == "complete" else "Cancelled"
        except (asyncio.CancelledError, InterruptedError):
            with self._lock:
                job["status"] = "cancelled"
                job["message"] = "Cancelled"
        except Exception as exc:
            log.error("job=%s failed type=%s elapsed=%.1fs", job_id[:8], type(exc).__name__, time.monotonic()-started)
            with self._lock:
                job["status"] = "failed"
                job["message"] = "Operation failed"
                job["error"] = f"{type(exc).__name__}: {_redact_error(str(exc), self.settings)}"
        finally:
            with self._lock:
                job["elapsed_seconds"] = round(time.monotonic()-started, 1)
                job["updated_at"] = datetime.now(timezone.utc).isoformat()
                job.pop("cancel_event", None)
                job.pop("started_mono", None)
                job.pop("payload", None)
                if self._active_job == job_id:
                    self._active_job = None
            log.info("job=%s status=%s elapsed=%.1fs", job_id[:8], self._jobs[job_id]["status"], time.monotonic()-started)

    def cancel_job(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job["status"] not in {"queued", "running"}:
                return False
            event = job.get("cancel_event")
            if event:
                event.set()
            job["message"] = "Cancellation requested"
            return True

    async def update_settings(self, payload: dict):
        current = self.public_settings()
        model = str(payload.get("ollama_model", current["ollama_model"])).strip() or None
        if model and model != self.settings.ollama_model:
            models = discover_installed_models(self.settings, timeout=15)
            if model not in set(models):
                raise ValueError("Select a model from the currently installed Ollama models")
        def bounded_int(key, low, high):
            value = int(payload.get(key, current[key]))
            if not low <= value <= high:
                raise ValueError(f"{key} must be between {low} and {high}")
            return value
        ollama_timeout = float(payload.get("ollama_timeout", current["ollama_timeout"]))
        mcp_timeout = float(payload.get("mcp_timeout", current["mcp_timeout"]))
        if not 5 <= ollama_timeout <= 180 or not 5 <= mcp_timeout <= 60:
            raise ValueError("Timeouts must be Ollama 5–180s and MCP 5–60s")
        new_notes_dir = Path(str(payload.get("notes_dir", current["notes_dir"]))).expanduser().resolve()
        if len(str(new_notes_dir)) > 500:
            raise ValueError("Planning notes path is too long")
        prefs = {
            "location": str(payload.get("location", current["location"]))[:100],
            "briefing_preferences": str(payload.get("briefing_preferences", current["briefing_preferences"]))[:1000],
            "theme": "light" if payload.get("theme", current["theme"]) == "light" else "dark",
        }
        self.preferences_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings = replace(self.settings, ollama_model=model,
                                max_search_queries=bounded_int("max_search_queries", 1, 8),
                                max_fetch_urls=bounded_int("max_fetch_urls", 1, 8),
                                max_content_chars=bounded_int("max_content_chars", 2_000, 120_000),
                                notes_dir=new_notes_dir, ollama_timeout=ollama_timeout,
                                mcp_timeout=mcp_timeout)
        persisted = {**prefs,
                     "ollama_model": self.settings.ollama_model,
                     "max_search_queries": self.settings.max_search_queries,
                     "max_fetch_urls": self.settings.max_fetch_urls,
                     "max_content_chars": self.settings.max_content_chars,
                     "notes_dir": str(self.settings.notes_dir),
                     "ollama_timeout": self.settings.ollama_timeout,
                     "mcp_timeout": self.settings.mcp_timeout}
        self.preferences_path.write_text(json.dumps(persisted, indent=2), encoding="utf-8")
        self.preferences = persisted
        self.service = BriefingService(self.settings, self.store)
        self._apply_preferences_to_service()
        return self.public_settings()

    # --------------------------------------------------------------- discovery
    def intel(self, category: str, query: str = "", freshness: str = "",
              region: str = "", topic: str = "") -> dict:
        if category not in CATEGORIES:
            raise ValueError(f"Unsupported category: {category}")
        if category == "jobs":
            items = self.store.jobs(query=query, limit=500)
        elif category == "government":
            items = self.store.notices(query=query, limit=300)
        elif category == "exams":
            items = self.store.exams(query=query, limit=400)
        elif category in {"news", "papers"}:
            items = self.store.intel(category=category, query=query, freshness=freshness,
                                     region=region, topic=topic, limit=300)
        else:
            items = []
        return {"category": category, "query": query, "region": region, "topic": topic,
                "items": items, "counts": self.store.counts()}

    def insights(self) -> dict:
        jobs = self.store.jobs(limit=1000)
        return {"job_market": job_market(jobs), "counts": self.store.counts()}

    def save_discovery_preferences(self, payload: dict) -> dict:
        clean = save_preferences(self.store, payload)
        self.discovery_preferences = clean
        return clean

    def watchlist(self, kind: str) -> list[str]:
        if kind not in {"exam", "organization"}:
            raise ValueError("Watchlist kind must be exam or organization")
        return self.store.watchlist(kind)

    def add_watchlist(self, kind: str, name: str, *, remove: bool = False) -> list[str]:
        if kind not in {"exam", "organization"}:
            raise ValueError("Watchlist kind must be exam or organization")
        if remove:
            self.store.remove_watchlist(kind, " ".join(str(name).split())[:120])
        else:
            self.store.add_watchlist(kind, name)
        return self.store.watchlist(kind)

    async def process_resume(self, filename: str, data: bytes) -> dict:
        if not data:
            raise ValueError("Resume file is empty")
        if len(data) > 6_000_000:
            raise ValueError("Resume file exceeds 6 MB")
        text = extract_text(filename, data)
        if not text.strip():
            raise ValueError("No readable text was found in the resume. Scanned PDFs may need OCR.")
        provider = OllamaProvider(
            host=self.settings.ollama_host,
            preferred_model=self.settings.ollama_model,
            timeout=min(self.settings.ollama_timeout, 60.0),
        )
        try:
            profile = await extract_profile(text, provider)
        except LocalModelError:
            from app.services.resume import extract_profile_deterministic
            profile = extract_profile_deterministic(text)
        self.store.save_profile(profile, filename[:200])
        return {"profile": profile, "filename": filename, "extracted_at": datetime.now(timezone.utc).isoformat()}

    def save_profile(self, profile: dict) -> dict:
        if not isinstance(profile, dict):
            raise ValueError("Profile must be an object")
        clean = {}
        for key in ("education", "skills", "languages", "frameworks", "projects",
                    "certifications", "keywords"):
            value = profile.get(key)
            if isinstance(value, list):
                clean[key] = [" ".join(str(item).split())[:160] for item in value
                              if str(item).strip()][:40]
        for key, low, high in (("graduation_year", 1980, 2100),
                               ("experience_years", 0, 60)):
            try:
                clean[key] = max(low, min(high, int(profile.get(key))))
            except (TypeError, ValueError):
                pass
        clean["source"] = "user_edited"
        existing = self.store.profile()
        filename = existing.get("resume_filename") if existing else None
        self.store.save_profile(clean, filename)
        return {"profile": clean, "filename": filename}

    def handler(self):
        app = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                log.info("http client=%s %s", self.address_string(), fmt % args)

            def send(self, code, data, content_type="application/json; charset=utf-8"):
                raw = data.encode() if isinstance(data, str) else data
                self.send_response(code)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(raw)

            def json(self, code, value):
                return self.send(code, json.dumps(value, ensure_ascii=False, default=str))

            def body(self, max_bytes: int = 32_768):
                length = int(self.headers.get("Content-Length", "0"))
                if length > max_bytes:
                    raise ValueError(f"Request body exceeds {max_bytes // 1024} KB")
                data = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(data, dict):
                    raise ValueError("Expected a JSON object")
                return data

            def query(self):
                return parse_qs(urlparse(self.path).query)

            def do_GET(self):
                path = urlparse(self.path).path
                params = self.query()
                if path == "/":
                    return self.send(200, app.page(), "text/html; charset=utf-8")
                if path in {"/app.css", "/app.js"}:
                    name = path[1:]
                    typ = "text/css; charset=utf-8" if name.endswith(".css") else "text/javascript; charset=utf-8"
                    try: return self.send(200, (STATIC_DIR / name).read_text(encoding="utf-8"), typ)
                    except OSError: return self.send(404, "Not found", "text/plain; charset=utf-8")
                if path == "/api/bootstrap": return self.json(200, app.bootstrap())
                if path == "/api/state": return self.json(200, app.job_state())
                if path.startswith("/api/jobs/"):
                    job_id = path.rsplit("/", 1)[1]
                    item = app.job_state(job_id)
                    return self.json(200, item) if item else self.json(404, {"error": "Job not found"})
                if path == "/api/models":
                    try:
                        models = discover_installed_models(app.settings, timeout=15)
                        return self.json(200, {"models": models})
                    except Exception as exc:
                        return self.json(502, {"error": f"Ollama model discovery failed: {type(exc).__name__}: {exc}"})
                if path == "/api/briefings": return self.json(200, app.store.briefings(20))
                if path == "/api/intel":
                    try:
                        category = params.get("category", ["jobs"])[0]
                        return self.json(200, app.intel(
                            category,
                            params.get("query", [""])[0],
                            params.get("freshness", [""])[0],
                            params.get("region", [""])[0],
                            params.get("topic", [""])[0],
                        ))
                    except ValueError as exc:
                        return self.json(400, {"error": str(exc)})
                if path == "/api/insights/jobs":
                    return self.json(200, app.insights())
                if path == "/api/preferences":
                    return self.json(200, {"preferences": app.discovery_preferences,
                                           "settings": app.public_settings()})
                if path in {"/api/exams/watchlist", "/api/organizations/watchlist"}:
                    kind = "exam" if path.startswith("/api/exams") else "organization"
                    return self.json(200, {"kind": kind, "items": app.watchlist(kind)})
                if path == "/api/resume":
                    return self.json(200, {"profile": app.store.profile()})
                if path == "/api/saved":
                    return self.json(200, {"items": app.store.saved_items(),
                                           "states": app.store.item_states()})
                if path == "/api/search/sessions":
                    return self.json(200, {"sessions": app.store.search_sessions(30)})
                if path == "/api/export":
                    return self.json(200, app.store.export_data())
                return self.send(404, "Not found", "text/plain; charset=utf-8")

            def do_POST(self):
                path = urlparse(self.path).path
                try:
                    if path == "/api/resume":
                        payload = self.body(max_bytes=8_000_000)
                        encoded = str(payload.get("content_base64") or "")
                        try:
                            data = base64.b64decode(encoded, validate=True)
                        except (binascii.Error, ValueError) as exc:
                            raise ValueError("Resume upload is not valid base64") from exc
                        filename = str(payload.get("filename") or "resume.pdf")[:200]
                        result = asyncio.run(app.process_resume(filename, data))
                        return self.json(200, result)

                    payload = self.body()
                    if path == "/api/briefings":
                        job_id, active = app.start_job("briefing")
                        if not job_id: return self.json(409, {"error": "A long-running request is already active", "active_job": active})
                        return self.json(202, {"id": job_id, "status": "queued"})
                    if path == "/api/research":
                        request = str(payload.get("request", "")).strip()
                        if not request or len(request) > 3000: return self.json(400, {"error": "Request must contain 1–3000 characters"})
                        job_id, active = app.start_job("research", request)
                        if not job_id: return self.json(409, {"error": "A long-running request is already active", "active_job": active})
                        return self.json(202, {"id": job_id, "status": "queued"})
                    if path == "/api/intel/search":
                        category = str(payload.get("category") or "").strip()
                        if category not in CATEGORIES:
                            return self.json(400, {"error": f"category must be one of {sorted(CATEGORIES)}"})
                        request = str(payload.get("query") or payload.get("request") or "").strip()
                        if len(request) > 3000:
                            return self.json(400, {"error": "Query must be at most 3000 characters"})
                        freshness = payload.get("freshness")
                        job_id, active = app.start_job("discovery", request,
                                                       {"category": category, "query": request,
                                                        "freshness": freshness,
                                                        "region": str(payload.get("region") or "").strip(),
                                                        "topic": str(payload.get("topic") or "").strip()})
                        if not job_id: return self.json(409, {"error": "A long-running request is already active", "active_job": active})
                        return self.json(202, {"id": job_id, "status": "queued", "category": category})
                    if path == "/api/planning/refresh":
                        notes = app.sync_planning_notes()
                        return self.json(200, {
                            "tasks": app.store.tasks(),
                            "planning": {
                                "notes_dir": str(app.settings.notes_dir),
                                "missing": notes["missing"],
                                "files": notes["files"],
                                "errors": notes["errors"],
                                "tasks_found": len(notes["tasks"]),
                            },
                        })
                    if path == "/api/diagnostics/mcp":
                        job_id, active = app.start_job("mcp_diagnostics")
                        if not job_id: return self.json(409, {"error": "A long-running request is already active", "active_job": active})
                        return self.json(202, {"id": job_id, "status": "queued"})
                    if path.startswith("/api/jobs/") and path.endswith("/cancel"):
                        job_id = path.split("/")[3]
                        return self.json(202 if app.cancel_job(job_id) else 409,
                                         {"status": "cancellation_requested" if app.job_state(job_id) else "not_cancellable"})
                    if path == "/api/tasks":
                        text = str(payload.get("text", "")).strip()
                        if not text or len(text) > 500: return self.json(400, {"error": "Task text must contain 1–500 characters"})
                        task_id = app.store.add_task(text, payload.get("due_date") or None)
                        return self.json(201, {"id": task_id})
                    if path.startswith("/api/tasks/") and path.endswith("/toggle"):
                        task_id = int(path.split("/")[3])
                        task = next((t for t in app.store.tasks() if t["id"] == task_id), None)
                        if not task: return self.json(404, {"error": "Task not found"})
                        app.store.set_task_status(task_id, "pending" if task["status"] == "completed" else "completed")
                        return self.json(200, {"ok": True})
                    if path == "/api/preferences":
                        values = payload.get("preferences", payload)
                        return self.json(200, {"preferences": app.save_discovery_preferences(values)})
                    if path in {"/api/exams/watchlist", "/api/organizations/watchlist"}:
                        kind = "exam" if path.startswith("/api/exams") else "organization"
                        name = str(payload.get("name") or "").strip()
                        remove = bool(payload.get("remove")) or str(payload.get("action", "")) == "remove"
                        if not name:
                            return self.json(400, {"error": "A watchlist name is required"})
                        return self.json(200, {"kind": kind,
                                               "items": app.add_watchlist(kind, name, remove=remove)})
                    if path == "/api/resume/profile":
                        return self.json(200, app.save_profile(payload.get("profile") or payload))
                    if path == "/api/items/state":
                        kind = str(payload.get("kind") or "").strip()
                        if kind not in ITEM_KINDS:
                            return self.json(400, {"error": f"kind must be one of {sorted(ITEM_KINDS)}"})
                        state = str(payload.get("state") or "saved")
                        try:
                            item_id = int(payload.get("id"))
                        except (TypeError, ValueError):
                            return self.json(400, {"error": "A numeric item id is required"})
                        app.store.set_item_state(kind, item_id, state)
                        return self.json(200, {"ok": True, "kind": kind, "id": item_id, "state": state})
                    if path == "/api/settings":
                        if app._active_job and app.job_state().get("status") in {"queued", "running"}:
                            return self.json(409, {"error": "Wait for the active request to finish before changing settings"})
                        updated = asyncio.run(app.update_settings(payload))
                        return self.json(200, {"settings": updated})
                    if path == "/api/data/clear-intel":
                        removed = app.store.clear_intel()
                        return self.json(200, {"removed": removed, "counts": app.store.counts()})
                    return self.send(404, "Not found", "text/plain; charset=utf-8")
                except (ValueError, TypeError, json.JSONDecodeError) as exc:
                    return self.json(400, {"error": str(exc)})
                except Exception as exc:
                    log.exception("API error path=%s", path)
                    return self.json(500, {"error": f"{type(exc).__name__}: {_redact_error(str(exc), app.settings)}"})

        return Handler


def serve(open_browser=True):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = Settings.from_env()
    app = Application(settings)
    server = BoundedThreadingHTTPServer((settings.host, settings.port), app.handler())
    url = f"http://{settings.host}:{settings.port}/"
    print(f"Daily Intelligence listening at {url}; press Ctrl+C to stop.")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        log.info("shutdown requested")
    finally:
        active_id = app._active_job
        if active_id:
            app.cancel_job(active_id)
        server.server_close()
        app._executor.shutdown(wait=False, cancel_futures=True)
