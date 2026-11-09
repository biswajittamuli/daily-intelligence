"""Search sessions, the source registry and per-run coverage diagnostics."""
from __future__ import annotations

from typing import Any

from app.memory.store_parts.common import _json, _loads


class SourcesMixin:
    # ---------------------------------------------------------- search sessions
    def start_search_session(self, category: str, request: str) -> int:
        with self.connect() as db:
            cur = db.execute("INSERT INTO search_sessions(category,request,status,created_at,updated_at) VALUES(?,?,'running',?,?)",
                             (category, request, self.now(), self.now()))
            return int(cur.lastrowid)

    def update_search_session(self, session_id: int, *, status: str | None = None,
                              plan: Any = None, progress: Any = None,
                              summary: Any = None, error: str | None = None) -> None:
        fields, values = [], []
        for name, value in (("status", status), ("plan_json", _json(plan)),
                            ("progress_json", _json(progress)), ("summary_json", _json(summary)),
                            ("error", error)):
            if value is not None:
                fields.append(f"{name}=?")
                values.append(value)
        if not fields:
            return
        fields.append("updated_at=?")
        values.extend([self.now(), session_id])
        with self.connect() as db:
            db.execute(f"UPDATE search_sessions SET {', '.join(fields)} WHERE id=?", values)

    def search_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM search_sessions ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        output = []
        for row in rows:
            item = dict(row)
            for key in ("plan_json", "progress_json", "summary_json"):
                item[key.removesuffix("_json")] = _loads(item.pop(key), None)
            output.append(item)
        return output

    # ---------------------------------------------------------- source registry (v7)
    def source_states(self) -> dict[str, dict[str, Any]]:
        with self.connect() as db:
            return {row["source_id"]: dict(row) for row in db.execute("SELECT * FROM source_state")}

    def set_source_enabled(self, source_id: str, enabled: bool | None) -> None:
        with self.connect() as db:
            db.execute("""INSERT INTO source_state(source_id, enabled, updated_at) VALUES(?,?,?)
                          ON CONFLICT(source_id) DO UPDATE SET enabled=excluded.enabled, updated_at=excluded.updated_at""",
                       (source_id, None if enabled is None else int(enabled), self.now()))

    def record_source_runs(self, runs: dict[str, dict[str, Any]]) -> None:
        """Fold one run's per-source outcome into the persistent state (with backoff after repeated failures)."""
        from app.services.job_sources.registry import backoff_until
        now = self.now()
        with self.connect() as db:
            for sid, run in runs.items():
                row = db.execute("SELECT * FROM source_state WHERE source_id=?", (sid,)).fetchone()
                state = run["state"]
                if state == "not_attempted":
                    continue
                failed = state in {"failed", "access_restricted"}
                consecutive = ((row["consecutive_failures"] if row else 0) + 1) if failed else 0
                values = {
                    "last_attempt_at": now, "last_state": state,
                    "last_success_at": now if state in {"successful", "partial", "no_results"} else (row["last_success_at"] if row else None),
                    "last_result_at": now if run.get("results") or run.get("listings") else (row["last_result_at"] if row else None),
                    "last_failure_reason": (run.get("failure") or (row["last_failure_reason"] if row else None)) if failed
                    else (row["last_failure_reason"] if row else None),
                    "attempts": (row["attempts"] if row else 0) + 1,
                    "successes": (row["successes"] if row else 0) + int(state == "successful"),
                    "partials": (row["partials"] if row else 0) + int(state == "partial"),
                    "failures": (row["failures"] if row else 0) + int(failed),
                    "consecutive_failures": consecutive,
                    "results_total": (row["results_total"] if row else 0) + int(run.get("results") or 0) + int(run.get("listings") or 0),
                    "last_results": int(run.get("results") or 0) + int(run.get("listings") or 0),
                    "last_unique": int(run.get("unique") or 0),
                    "extraction_ok": (row["extraction_ok"] if row else 0) + int(run.get("extraction_ok") or 0),
                    "extraction_total": (row["extraction_total"] if row else 0) + int(run.get("extraction_total") or 0),
                    "next_attempt_at": backoff_until(consecutive), "updated_at": now,
                }
                if row is None:
                    db.execute(f"INSERT INTO source_state(source_id, {', '.join(values)}) VALUES(?{', ?' * len(values)})",
                               (sid, *values.values()))
                else:
                    db.execute(f"UPDATE source_state SET {', '.join(k + '=?' for k in values)} WHERE source_id=?",
                               (*values.values(), sid))

    def record_source_verification(self, source_id: str, ok: int, total: int) -> None:
        if total <= 0:
            return
        with self.connect() as db:
            db.execute("""INSERT INTO source_state(source_id, verification_ok, verification_total, updated_at) VALUES(?,?,?,?)
                          ON CONFLICT(source_id) DO UPDATE SET verification_ok=source_state.verification_ok+excluded.verification_ok,
                          verification_total=source_state.verification_total+excluded.verification_total,
                          updated_at=excluded.updated_at""", (source_id, ok, total, self.now()))

    # -------------------------------------------------------- diagnostics (v6)
    def save_coverage(self, session_id: int, reports: list[dict[str, Any]], exclusions: list[dict[str, Any]]) -> None:
        """Persist one session's source reports and exclusions, and roll source health forward."""
        from app.services.job_sources.models import SourceState
        now = self.now()
        with self.connect() as db:
            db.execute("DELETE FROM source_reports WHERE session_id=?", (session_id,))
            for r in reports:
                db.execute("""INSERT INTO source_reports(session_id,source_key,name,category,domain,method,state,started_at,
                              completed_at,http_status,queries,search_results,fetched,parsed,listings,unique_count,duplicates,
                              rejected,stored,verified,retries,duration_ms,failure_reason,detail)
                              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                           (session_id, r["key"], r["name"], r.get("category"), r.get("domain"), r.get("method"), r["state"],
                            r.get("started_at"), r.get("completed_at"), r.get("http_status"), r.get("queries"),
                            r.get("search_results"), r.get("fetched"), r.get("parsed"), r.get("listings"), r.get("unique"),
                            r.get("duplicates"), r.get("rejected"), r.get("stored"), r.get("verified"), r.get("retries"),
                            r.get("duration_ms"), r.get("failure_reason"), r.get("detail")))
                success = r["state"] in SourceState.SUCCESS
                failure = not success and r["state"] not in {SourceState.NO_RESULTS, SourceState.TARGETED,
                                                             SourceState.NOT_TARGETED, SourceState.POLICY_SKIPPED}
                db.execute("""INSERT INTO source_health(source_key,name,category,domain,method,last_state,last_success_at,
                              last_failure_at,last_failure_reason,success_count,failure_count,last_listings,updated_at)
                              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                              ON CONFLICT(source_key) DO UPDATE SET last_state=excluded.last_state,
                              last_success_at=COALESCE(excluded.last_success_at, source_health.last_success_at),
                              last_failure_at=COALESCE(excluded.last_failure_at, source_health.last_failure_at),
                              last_failure_reason=COALESCE(excluded.last_failure_reason, source_health.last_failure_reason),
                              success_count=source_health.success_count+excluded.success_count,
                              failure_count=source_health.failure_count+excluded.failure_count,
                              last_listings=excluded.last_listings, updated_at=excluded.updated_at""",
                           (r["key"], r["name"], r.get("category"), r.get("domain"), r.get("method"), r["state"],
                            now if success else None, now if failure else None,
                            r.get("failure_reason") if failure else None, int(success), int(failure),
                            r.get("listings"), now))
            db.execute("DELETE FROM job_exclusions WHERE session_id=?", (session_id,))
            db.executemany("""INSERT INTO job_exclusions(session_id,url,title,employer,source,reason,stage,detail,created_at)
                              VALUES(?,?,?,?,?,?,?,?,?)""",
                           [(session_id, e.get("url"), e.get("title"), e.get("employer"), e.get("source"), e["reason"],
                             e.get("stage"), e.get("detail"), now) for e in exclusions])
            # Keep diagnostics for the 15 most recent job sessions only.
            keep = [row["id"] for row in db.execute(
                "SELECT id FROM search_sessions WHERE category='jobs' ORDER BY id DESC LIMIT 15")]
            if keep:
                marks = ",".join("?" * len(keep))
                db.execute(f"DELETE FROM job_exclusions WHERE session_id NOT IN ({marks})", keep)
                db.execute(f"DELETE FROM source_reports WHERE session_id NOT IN ({marks})", keep)

    def source_reports(self, session_id: int) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM source_reports WHERE session_id=? ORDER BY id",
                                                    (session_id,))]

    def source_health(self, limit: int = 500) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM source_health ORDER BY updated_at DESC LIMIT ?",
                                                    (limit,))]

    def exclusions(self, session_id: int | None = None, *, reason: str = "", query: str = "",
                   limit: int = 200, offset: int = 0) -> dict[str, Any]:
        with self.connect() as db:
            if session_id is None:
                row = db.execute("SELECT MAX(session_id) AS s FROM job_exclusions").fetchone()
                session_id = row["s"] if row else None
            if session_id is None:
                return {"session_id": None, "total": 0, "reasons": {}, "items": []}
            reasons = {row["reason"]: row["n"] for row in db.execute(
                "SELECT reason, COUNT(*) AS n FROM job_exclusions WHERE session_id=? GROUP BY reason ORDER BY n DESC",
                (session_id,))}
            where, args = "session_id=?", [session_id]
            if reason:
                where += " AND reason=?"
                args.append(reason)
            if query:
                where += " AND (title LIKE ? OR employer LIKE ? OR url LIKE ?)"
                args += [f"%{query}%"] * 3
            total = db.execute(f"SELECT COUNT(*) AS n FROM job_exclusions WHERE {where}", args).fetchone()["n"]
            items = [dict(row) for row in db.execute(
                f"SELECT * FROM job_exclusions WHERE {where} ORDER BY id LIMIT ? OFFSET ?",
                (*args, max(1, min(limit, 1000)), max(0, offset)))]
        return {"session_id": session_id, "total": total, "reasons": reasons, "items": items}
