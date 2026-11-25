"""HTTP routing for the loopback-only JSON API and static frontend (moved out of app/web.py).

``make_handler(app)`` builds the request handler class bound to one ``Application``.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import re
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

from app.memory.planning import normalize_task
from app.llm_runtime import discover_installed_models
from app.services.discovery import CATEGORIES
from app.services.exports import calendar_ics, jobs_csv
from app.web import ITEM_KINDS, STATIC_DIR, STATIC_SCRIPT, _redact_error

if TYPE_CHECKING:
    from app.web import Application

log = logging.getLogger("app.web")  # keep the request log under the same logger name as before


def make_handler(app: "Application") -> type[BaseHTTPRequestHandler]:

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

        def same_origin(self) -> bool:
            """Only this app's own page may use the API: blocks other websites (CSRF) and DNS rebinding."""
            port = self.server.server_address[1]
            allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
            if str(self.headers.get("Host") or "") not in allowed:
                return False
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).netloc not in allowed:
                return False
            if self.command in {"POST", "PUT"} and \
                    not str(self.headers.get("Content-Type") or "").startswith("application/json"):
                return False  # forces a CORS preflight for cross-site requests, which this server never approves
            return True

        def query(self):
            return parse_qs(urlparse(self.path).query)

        def do_GET(self):
            if not self.same_origin():
                return self.json(403, {"error": "Forbidden"})
            app.touch()
            path = urlparse(self.path).path
            params = self.query()
            if path == "/":
                return self.send(200, app.page(), "text/html; charset=utf-8")
            if path in {"/icon.svg", "/favicon.ico"}:
                icon = Path(__file__).resolve().parent.parent / "desktop" / "daily-intelligence.svg"
                try: return self.send(200, icon.read_bytes(), "image/svg+xml")
                except OSError: return self.send(404, "Not found", "text/plain; charset=utf-8")
            if path == "/app.css" or STATIC_SCRIPT.fullmatch(path):
                name = path[1:]
                typ = "text/css; charset=utf-8" if name.endswith(".css") else "text/javascript; charset=utf-8"
                try: return self.send(200, (STATIC_DIR / name).read_text(encoding="utf-8"), typ)
                except OSError: return self.send(404, "Not found", "text/plain; charset=utf-8")
            if path == "/api/health": return self.json(200, app.health())
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
            if path == "/api/resumes":
                return self.json(200, {"resumes": app.store.resumes()})
            if path == "/api/applications":
                return self.json(200, {"items": app.store.applications(),
                                       "statuses": app.store.APPLICATION_STATUSES})
            if path == "/api/employers":
                from app.services.employer_discovery import cluster_signals
                signals = app.store.signals(limit=500)
                return self.json(200, {"employers": app.store.employers(limit=1000), "signals": signals,
                                       "signal_events": cluster_signals(signals)})
            if path == "/api/keys":
                return self.json(200, app.api_keys())
            if path == "/api/eligibility":
                return self.json(200, app.eligibility_view())
            if path == "/api/coverage":
                return self.json(200, app.coverage_view())
            if path == "/api/companies":
                try:
                    limit = max(1, min(int(params.get("limit", ["2000"])[0] or 2000), 5000))
                except ValueError:
                    limit = 2000
                return self.json(200, app.company_registry_view(segment=params.get("segment", [""])[0], limit=limit))
            if path == "/api/gov/sources":
                return self.json(200, app.gov_sources_view())
            if path == "/api/monitoring":
                return self.json(200, {"status": app.monitor_status,
                                       "last": app.store.get_preference("last_source_monitoring") or {},
                                       "enabled": app.monitoring_enabled()})
            if path == "/api/missed":
                return self.json(200, app.missed_reports_view(status=params.get("status", [""])[0]))
            if path == "/api/feed":
                return self.json(200, app.feed(include_hidden=params.get("hidden", ["0"])[0] == "1"))
            if path == "/api/sources":
                return self.json(200, {"sources": app.sources_view()})
            if path == "/api/sources/health":
                from app.services.job_sources import ats_registry
                from app.services.job_sources.portals import policy_table
                return self.json(200, {"health": app.store.source_health(),
                                       "policies": policy_table(),
                                       "ats_providers": [{"key": p.key, "name": p.name, "readable": p.readable,
                                                          "interface": p.interface} for p in ats_registry.PROVIDERS]})
            if path == "/api/sources/exclusions":
                session = params.get("session", [""])[0]
                try:
                    offset = int(params.get("offset", ["0"])[0] or 0)
                    session_id = int(session) if session else None
                except ValueError:
                    return self.json(400, {"error": "session and offset must be integers"})
                return self.json(200, app.store.exclusions(session_id, reason=params.get("reason", [""])[0][:200],
                                                           query=params.get("q", [""])[0][:200], offset=offset,
                                                           limit=200))
            if path == "/api/sources/reports":
                session = params.get("session", [""])[0]
                if not session.isdigit():
                    return self.json(400, {"error": "session is required"})
                return self.json(200, {"reports": app.store.source_reports(int(session))})
            if path == "/api/tracker":
                return self.json(200, {"items": app.store.tracker()})
            if path == "/api/planning/today":
                return self.json(200, app.today_plan())
            if path == "/api/notes":
                return self.json(200, {"notes": app.list_notes(),
                                       "notes_dir": str(app.settings.notes_dir)})
            if path.startswith("/api/notes/"):
                try:
                    return self.json(200, app.read_note(path.split("/", 3)[3]))
                except ValueError as exc:
                    return self.json(400, {"error": str(exc)})
            if path == "/api/export/calendar.ics":
                body = calendar_ics(tasks=app.store.tasks(), jobs=app.store.jobs(limit=1000),
                                    exams=app.store.exams(limit=500), notices=app.store.notices(limit=500))
                self.send_response(200)
                raw = body.encode()
                self.send_header("Content-Type", "text/calendar; charset=utf-8")
                self.send_header("Content-Disposition", 'attachment; filename="daily-intelligence.ics"')
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return None
            if path == "/api/export/jobs.csv":
                fresh = params.get("fresh", ["0"])[0] == "1"
                body = jobs_csv(app.store.jobs(limit=2000, fresh_only=fresh),
                                app.store.item_states().get("job", {}))
                raw = body.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", 'attachment; filename="jobs.csv"')
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return None
            if path == "/api/saved":
                return self.json(200, {"items": app.store.saved_items(),
                                       "states": app.store.item_states()})
            if path == "/api/search/sessions":
                return self.json(200, {"sessions": app.store.search_sessions(30)})
            if path == "/api/export":
                return self.json(200, app.store.export_data())
            return self.send(404, "Not found", "text/plain; charset=utf-8")

        def do_POST(self):
            if not self.same_origin():
                return self.json(403, {"error": "Forbidden"})
            app.touch()
            path = urlparse(self.path).path
            try:
                if path.startswith("/api/keys"):
                    payload = self.body(max_bytes=8_192)
                    provider = str(payload.get("provider") or "")
                    if path == "/api/keys":
                        return self.json(200, app.save_api_keys(provider, payload.get("values") or {}))
                    if path == "/api/keys/remove":
                        return self.json(200, app.remove_api_keys(provider))
                    if path == "/api/keys/test":
                        return self.json(200, app.test_api_keys(provider))
                if path == "/api/resume":
                    payload = self.body(max_bytes=8_000_000)
                    encoded = str(payload.get("content_base64") or "")
                    try:
                        data = base64.b64decode(encoded, validate=True)
                    except (binascii.Error, ValueError) as exc:
                        raise ValueError("Resume upload is not valid base64") from exc
                    filename = str(payload.get("filename") or "resume.pdf")[:200]
                    replace_id = payload.get("replace_id")
                    result = asyncio.run(app.process_resume(
                        filename, data, label=str(payload.get("label") or "")[:60],
                        make_default=bool(payload.get("make_default")),
                        replace_id=int(replace_id) if replace_id else None))
                    return self.json(200, result)
                if path.startswith("/api/notes/") and self.command in {"POST", "PUT"}:
                    payload = self.body(max_bytes=220_000)
                    return self.json(200, app.write_note(path.split("/", 3)[3],
                                                         str(payload.get("content") or "")))

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
                                                    "topic": str(payload.get("topic") or "").strip(),
                                                    "pool_size": payload.get("pool_size"),
                                                    "scan": bool(payload.get("scan"))})
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
                if path in {"/api/search/universal", "/api/search/scan-all"}:
                    request = str(payload.get("request") or "").strip()
                    kind = "universal" if path.endswith("universal") else "scan_all"
                    if kind == "universal" and (not request or len(request) > 1000):
                        return self.json(400, {"error": "Enter a request of 1–1000 characters"})
                    job_id, active = app.start_job(kind, request, {"pool_size": payload.get("pool_size")})
                    if not job_id: return self.json(409, {"error": "A long-running request is already active", "active_job": active})
                    return self.json(202, {"id": job_id, "status": "queued", "kind": kind})
                if path == "/api/theme":
                    return self.json(200, {"theme": app.set_theme(str(payload.get("theme") or ""))})
                if path == "/api/heartbeat":
                    return self.json(200, {"ok": True})
                if path == "/api/shutdown":
                    if app._active_job and app.job_state().get("status") in {"queued", "running"} \
                            and not payload.get("force"):
                        return self.json(409, {"error": "A search is still running; cancel it or confirm quitting"})
                    app.shutdown_requested.set()
                    return self.json(202, {"ok": True, "message": "Daily Intelligence is shutting down"})
                if path.startswith("/api/resumes/") and path.endswith("/reprocess"):
                    return self.json(200, asyncio.run(app.reprocess_resume(int(path.split("/")[3]))))
                if path == "/api/jobs/reverify":
                    job_id, active = app.start_job("reverify", "", {"job_ids": payload.get("job_ids"),
                                                                    "limit": payload.get("limit")})
                    if not job_id: return self.json(409, {"error": "A long-running request is already active", "active_job": active})
                    return self.json(202, {"id": job_id, "status": "queued"})
                if path.startswith("/api/employers/") and path.endswith("/follow"):
                    try:
                        employer_id = int(path.split("/")[3])
                    except (ValueError, IndexError):
                        return self.json(400, {"error": "Invalid employer id"})
                    app.store.set_employer_followed(employer_id, bool(payload.get("followed", True)))
                    return self.json(200, {"ok": True, "id": employer_id, "followed": bool(payload.get("followed", True))})
                if path.startswith("/api/listings/") and path.endswith("/report"):
                    try:
                        listing_id = int(path.split("/")[3])
                    except (ValueError, IndexError):
                        return self.json(400, {"error": "Invalid listing id"})
                    if payload.get("undo"):
                        app.store.unreport_listing(listing_id)
                        return self.json(200, {"ok": True, "id": listing_id, "reported": False})
                    try:
                        app.store.report_listing(listing_id, str(payload.get("reason") or "other"), payload.get("note"))
                    except ValueError as exc:
                        return self.json(400, {"error": str(exc)})
                    return self.json(200, {"ok": True, "id": listing_id, "reported": True})
                if path == "/api/eligibility":
                    return self.json(200, app.save_eligibility(payload.get("profile") or payload))
                if path == "/api/eligibility/reevaluate":
                    return self.json(200, {"reevaluated": app.reevaluate_eligibility()})
                if path == "/api/missed":
                    try:
                        return self.json(200, app.add_missed_report(payload))
                    except ValueError as exc:
                        return self.json(400, {"error": str(exc)})
                if path.startswith("/api/companies/") and path.endswith("/update"):
                    try:
                        company_id = int(path.split("/")[3])
                    except (ValueError, IndexError):
                        return self.json(400, {"error": "Invalid company id"})
                    values = {key: payload[key] for key in ("enabled", "followed", "priority", "segment", "next_due_at")
                              if key in payload}
                    if "enabled" in values:
                        values["enabled"] = int(bool(values["enabled"]))
                    if "followed" in values:
                        values["followed"] = int(bool(values["followed"]))
                    app.store.update_company(company_id, **values)
                    return self.json(200, {"ok": True, "company": app.store.company(company_id)})
                if path == "/api/monitoring/run":
                    kind = str(payload.get("kind") or "auto")
                    if kind not in {"auto", "gov", "companies"}:
                        return self.json(400, {"error": "kind must be auto, gov or companies"})
                    if app._light_future is not None and not app._light_future.done():
                        return self.json(409, {"error": "A monitoring batch is already running"})
                    chosen = app.maybe_source_monitoring() if kind == "auto" else None
                    if chosen is None and kind != "auto":
                        batch = int((app.discovery_preferences.get("automation") or {}).get("monitor_batch") or 3)
                        app._light_future = app._light.submit(app._run_monitoring, kind, batch)
                        chosen = kind
                    return self.json(202, {"queued": bool(chosen), "kind": chosen})
                if path == "/api/alerts/read":
                    alerts = app.store.get_preference("alerts", []) or []
                    for alert in alerts:
                        alert["read"] = True
                    app.store.set_preference("alerts", alerts)
                    return self.json(200, {"ok": True})
                if path == "/api/followed/check":
                    job_id, active = app.start_job("followed_check", "", {})
                    if not job_id: return self.json(409, {"error": "A long-running request is already active", "active_job": active})
                    return self.json(202, {"id": job_id, "status": "queued"})
                if path == "/api/discover":
                    query = str(payload.get("query") or "").strip()
                    if len(query) > 500:
                        return self.json(400, {"error": "Query must be at most 500 characters"})
                    mode = payload.get("mode") if payload.get("mode") in {"full", "targeted"} else None
                    job_id, active = app.start_job("discover", query, {"query": query, "mode": mode})
                    if not job_id: return self.json(409, {"error": "A long-running request is already active", "active_job": active})
                    return self.json(202, {"id": job_id, "status": "queued"})
                if path.startswith("/api/sources/") and path.endswith("/enabled"):
                    from app.services.job_sources.registry import BY_ID
                    source_id = path[len("/api/sources/"):-len("/enabled")]
                    if source_id not in BY_ID:
                        return self.json(404, {"error": "Unknown source"})
                    enabled = payload.get("enabled")
                    app.store.set_source_enabled(source_id, None if enabled is None else bool(enabled))
                    return self.json(200, {"sources": app.sources_view()})
                if path == "/api/employers/rediscover":
                    ids = payload.get("employer_ids")
                    ids = [int(i) for i in ids if str(i).isdigit()][:50] if isinstance(ids, list) else None
                    job_id, active = app.start_job("career_rediscovery", "", {"employer_ids": ids,
                                                                             "limit": payload.get("limit")})
                    if not job_id: return self.json(409, {"error": "A long-running request is already active", "active_job": active})
                    return self.json(202, {"id": job_id, "status": "queued"})
                if path == "/api/employers/discover":
                    request = str(payload.get("request") or "Indian AI startups")[:300]
                    job_id, active = app.start_job("employer_discovery", request,
                                                   {"topic": payload.get("topic"), "search_calls": payload.get("search_calls")})
                    if not job_id: return self.json(409, {"error": "A long-running request is already active", "active_job": active})
                    return self.json(202, {"id": job_id, "status": "queued"})
                if path == "/api/applications":
                    app_id = payload.get("id")
                    item = app.store.save_application(payload, int(app_id) if app_id else None)
                    app.application_reminders()
                    return self.json(200, {"application": item, "items": app.store.applications()})
                if path.startswith("/api/applications/") and path.endswith("/delete"):
                    app.store.delete_application(int(path.split("/")[3]))
                    return self.json(200, {"items": app.store.applications()})
                if path == "/api/planning/interpret":
                    if app._active_job and app.job_state().get("status") in {"queued", "running"}:
                        return self.json(409, {"error": "Wait for the active request to finish (the local model is busy)"})
                    return self.json(200, asyncio.run(app.interpret_notes()))
                if path == "/api/visit":
                    return self.json(200, app.mark_visit())
                if path == "/api/jobs/rescore":
                    return self.json(200, {"rescored": app.rescore_jobs()})
                if path.startswith("/api/listings/") and path.endswith("/tailor"):
                    if app._active_job and app.job_state().get("status") in {"queued", "running"}:
                        return self.json(409, {"error": "Wait for the active request to finish (the local model is busy)"})
                    listing_id = int(path.split("/")[3])
                    resume_id = payload.get("resume_id")
                    return self.json(200, asyncio.run(app.tailor_listing(
                        listing_id, int(resume_id) if resume_id else None)))
                if path.startswith("/api/resumes/"):
                    parts = path.split("/")
                    if len(parts) != 5:
                        return self.json(404, {"error": "Unknown resume route"})
                    return self.json(200, app.resume_action(int(parts[3]), parts[4], payload))
                if path.startswith("/api/tasks/") and path.endswith("/delete"):
                    task_id = int(path.split("/")[3])
                    task = next((t for t in app.store.tasks(include_archived=True) if t["id"] == task_id), None)
                    if not task: return self.json(404, {"error": "Task not found"})
                    if str(task.get("source") or "user") not in {"user", "tracker"}:
                        return self.json(400, {"error": "This task comes from a note file; edit the note to remove it"})
                    app.store.delete_task(task_id)
                    return self.json(200, {"ok": True})
                if path.startswith("/api/jobs/") and path.endswith("/cancel"):
                    job_id = path.split("/")[3]
                    return self.json(202 if app.cancel_job(job_id) else 409,
                                     {"status": "cancellation_requested" if app.job_state(job_id) else "not_cancellable"})
                if path == "/api/tasks":
                    text = str(payload.get("text", "")).strip()
                    if not text or len(text) > 500: return self.json(400, {"error": "Task text must contain 1–500 characters"})
                    parsed = normalize_task(text)
                    clock = str(payload.get("due_time") or "") or parsed["due_time"]
                    if clock and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", clock):
                        clock = None
                    task_id = app.store.add_task(parsed["text"], payload.get("due_date") or parsed["due_date"],
                                                 due_time=clock, recurrence=payload.get("recurrence") or parsed["recurrence"],
                                                 category=payload.get("category") or parsed["category"])
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
                    if state == "none":
                        app.store.clear_item_state(kind, item_id)
                        return self.json(200, {"ok": True, "kind": kind, "id": item_id, "state": None})
                    resume_id = payload.get("resume_id")
                    app.store.set_item_state(kind, item_id, state,
                                             resume_id=int(resume_id) if resume_id else None,
                                             note=payload.get("note"))
                    if kind == "job" and state in {"saved", "applied", "interview", "offer", "rejected"}:
                        listing = next((item for item in app.store.jobs(limit=5000) if item["id"] == item_id), None)
                        if listing:
                            app.store.save_application({"job_id": item_id, "company": listing.get("employer"),
                                                        "role": listing.get("title"), "job_url": listing.get("original_url"),
                                                        "resume_id": resume_id or listing.get("best_resume_id"),
                                                        "status": state})
                    if kind == "job" and state == "applied":
                        listing = next((item for item in app.store.jobs(limit=5000) if item["id"] == item_id), None)
                        if listing:
                            follow = (date.today() + timedelta(days=7)).isoformat()
                            title = f"Follow up on application: {listing.get('title')}"
                            if listing.get("employer"):
                                title += f" at {listing['employer']}"
                            if not any(t["text"] == title for t in app.store.tasks(include_archived=True)):
                                app.store.add_task(title[:300], follow, source="tracker", category="career")
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

        def do_PUT(self):
            return self.do_POST()

    return Handler
