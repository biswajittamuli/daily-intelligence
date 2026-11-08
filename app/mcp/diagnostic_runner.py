"""Hard-deadline process wrapper for transports that resist asyncio cancellation."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from typing import Any
from urllib.parse import urlsplit

from app.config import Settings


def run_mcp_diagnostic_process(settings: Settings, cancel_event: threading.Event | None = None) -> dict[str, Any]:
    timeout = max(5.0, min(180.0, settings.mcp_timeout * 4 + 5))
    endpoint_start = time.monotonic()
    endpoint = urlsplit(settings.parallel_mcp_url)
    try:
        port = endpoint.port or (443 if endpoint.scheme == "https" else 80)
        with socket.create_connection((endpoint.hostname, port), timeout=min(3.0, settings.mcp_timeout)):
            pass
    except Exception as exc:
        message = str(exc)
        category = "network" if isinstance(exc, (OSError, TimeoutError)) else "endpoint"
        return {"ok": False, "endpoint": _origin(settings.parallel_mcp_url),
                "failure_stage": "connection",
                "error_category": category,
                "error": f"Endpoint TCP connectivity failed: {type(exc).__name__}: {message}",
                "stages": {"connection": {"status": "failed",
                            "duration_seconds": round(time.monotonic()-endpoint_start, 3)}},
                "total_duration_seconds": round(time.monotonic()-endpoint_start, 3)}
    env = os.environ.copy()
    env["DAILY_INTELLIGENCE_MCP_WORKER"] = "1"
    command = [sys.executable, "-m", "app.main", "diagnostics", "mcp", "--worker"]
    started = time.monotonic()
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, env=env)
    while process.poll() is None:
        if cancel_event and cancel_event.is_set():
            process.terminate()
            try: process.wait(timeout=2)
            except subprocess.TimeoutExpired: process.kill()
            process.communicate()
            raise InterruptedError("MCP diagnostic cancelled")
        if time.monotonic() - started >= timeout:
            process.kill()
            stdout, stderr = process.communicate()
            stages = [line.split("=", 1)[1].strip().split("|", 1)[0] for line in stderr.splitlines()
                      if line.startswith("DAILY_INTEL_MCP_STAGE=")]
            failed = [line.split("=", 1)[1].strip() for line in stderr.splitlines()
                      if line.startswith("DAILY_INTEL_MCP_STAGE_FAILED=")]
            last_stage = failed[-1] if failed else stages[-1] if stages else "unknown"
            return {"ok": False, "endpoint": _origin(settings.parallel_mcp_url),
                    "failure_stage": last_stage,
                    "deadline_exceeded": True,
                    "error": f"MCP diagnostic exceeded the {timeout:.0f}s hard deadline; transport did not return",
                    "stages": {name: {"status": "timed_out" if name == last_stage else "started",
                                      "duration_seconds": round(float(line.split("|",1)[1]), 2) if "|" in line else None}
                               for line in stderr.splitlines() if line.startswith("DAILY_INTEL_MCP_STAGE=")
                               for name in [line.split("=",1)[1].split("|",1)[0]]},
                    "total_duration_seconds": round(time.monotonic() - started, 2),
                    "worker_stderr": _safe_stderr("\n".join(line for line in stderr.splitlines()
                        if "DAILY_INTEL_MCP_STAGE" not in line), settings)}
        time.sleep(0.1)
    stdout, stderr = process.communicate(timeout=2)
    try:
        report = json.loads(stdout)
    except json.JSONDecodeError:
        return {"ok": False, "endpoint": _origin(settings.parallel_mcp_url),
                "failure_stage": "diagnostic_worker", "error": "MCP diagnostic worker returned invalid output",
                "worker_exit_code": process.returncode, "worker_stderr": _safe_stderr(stderr, settings),
                "total_duration_seconds": round(time.monotonic() - started, 2)}
    report["total_duration_seconds"] = round(time.monotonic() - started, 2)
    return report


def _origin(endpoint: str) -> str:
    from urllib.parse import urlsplit
    parts = urlsplit(endpoint)
    host = parts.hostname or "unknown"
    if parts.port: host += f":{parts.port}"
    return f"{parts.scheme}://{host}"


def _safe_stderr(stderr: str, settings: Settings) -> str:
    value = stderr[-1200:]
    value = value.replace(settings.parallel_mcp_url, _origin(settings.parallel_mcp_url))
    token = os.getenv("PARALLEL_MCP_AUTH_TOKEN")
    if token: value = value.replace(token, "[redacted]")
    return value
