"""Common adapter interface for the discovery orchestrator.

An adapter acquires one family of sources and returns an ``AdapterResult`` with the run-level
source reports it produced. Adapters wrap the existing engines (``BroadJobSearch`` for jobs,
``DiscoveryEngine`` for government/exams/news, ``verify_jobs`` for re-verification) so there is
one acquisition engine per kind of data, not parallel copies.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from app.config import Settings
from app.memory.store import Store


@dataclass
class AcquisitionContext:
    settings: Settings
    store: Store
    preferences: dict[str, Any]
    request: str = ""
    mode: str = "full"  # full | targeted | scheduled
    progress: Callable[[str], None] = lambda _message: None
    cancel_event: Any | None = None
    skip: dict[str, str] = field(default_factory=dict)  # source id -> reason (disabled / backing off)

    def cancelled(self) -> bool:
        return self.cancel_event is not None and getattr(self.cancel_event, "is_set", lambda: False)()


@dataclass
class AdapterResult:
    name: str
    status: str  # complete | partial | failed | skipped
    summary: dict[str, Any] = field(default_factory=dict)
    reports: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    seconds: float = 0.0


class SourceAdapter(Protocol):
    name: str
    source_ids: tuple[str, ...]

    def applies(self, ctx: AcquisitionContext) -> bool: ...

    async def acquire(self, ctx: AcquisitionContext) -> AdapterResult: ...


def skip_map(store: Store, *, now: datetime | None = None) -> dict[str, str]:
    """Sources the user disabled, or that are backing off after repeated failures."""
    from app.services.job_sources.registry import BY_ID
    now = now or datetime.now(timezone.utc)
    states = store.source_states()
    output: dict[str, str] = {}
    for sid, definition in BY_ID.items():
        state = states.get(sid) or {}
        enabled = state.get("enabled")
        if enabled == 0 or (enabled is None and not definition.default_enabled):
            output[sid] = "disabled"
            continue
        until = state.get("next_attempt_at")
        if until:
            try:
                if datetime.fromisoformat(until) > now:
                    output[sid] = f"backing off until {until[:16]} after {state.get('consecutive_failures')} failures"
            except ValueError:
                pass
    return output
