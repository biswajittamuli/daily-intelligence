"""Tasks, history, briefings, source snapshots, preferences and watchlists."""
from __future__ import annotations

import hashlib
from typing import Any

from app.memory.store_parts.common import _json, _loads


class PersonalMixin:
    # ------------------------------------------------------------------ tasks
    def add_task(self, text: str, due_date: str | None = None, source: str = "user", *,
                 due_time: str | None = None, recurrence: str | None = None,
                 category: str | None = None) -> int:
        with self.connect() as db:
            cur = db.execute("""INSERT INTO tasks(text,due_date,status,source,updated_at,due_time,recurrence,category)
                                VALUES(?,?,'pending',?,?,?,?,?)""",
                             (text.strip(), due_date, source, self.now(), due_time, recurrence, category))
            return int(cur.lastrowid)

    def delete_task(self, task_id: int) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM tasks WHERE id=?", (task_id,))

    def set_task_status(self, task_id: int, status: str) -> None:
        if status not in {"pending", "completed"}:
            raise ValueError("Task status must be pending or completed")
        with self.connect() as db:
            db.execute("UPDATE tasks SET status=?, updated_at=? WHERE id=?", (status, self.now(), task_id))

    def tasks(self, *, include_archived: bool = False) -> list[dict[str, Any]]:
        where = "" if include_archived else "WHERE COALESCE(archived,0)=0"
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                f"SELECT * FROM tasks {where} ORDER BY COALESCE(due_date,'9999'), COALESCE(due_time,'99'), id")]

    def import_tasks(self, tasks: list[dict[str, Any]], *, sync_sources: list[str] | None = None) -> dict[str, int]:
        """Import note tasks. Notes are the source of truth for their own tasks:

        - a task already imported from the same file is updated (date, time, category);
        - a task whose line disappeared from a file listed in ``sync_sources`` is archived;
        - completion toggled in the app is kept unless the note itself marks it done.
        """
        stats = {"added": 0, "updated": 0, "archived": 0}
        now = self.now()
        with self.connect() as db:
            seen: dict[str, set[int]] = {}
            for task in tasks:
                row = db.execute("SELECT id,status FROM tasks WHERE text=? AND source=?",
                                 (task["text"], task["source"])).fetchone()
                if row:
                    status = "completed" if task["status"] == "completed" else row["status"]
                    db.execute("""UPDATE tasks SET due_date=?, due_time=?, recurrence=?, category=?,
                                  original_text=?, status=?, archived=0, updated_at=? WHERE id=?""",
                               (task.get("due_date"), task.get("due_time"), task.get("recurrence"),
                                task.get("category"), task.get("original_text"), status, now, row["id"]))
                    stats["updated"] += 1
                    task_id = int(row["id"])
                else:
                    cur = db.execute("""INSERT INTO tasks(text,due_date,status,source,updated_at,due_time,
                                        recurrence,category,original_text,archived) VALUES(?,?,?,?,?,?,?,?,?,0)""",
                                     (task["text"], task.get("due_date"), task["status"], task["source"], now,
                                      task.get("due_time"), task.get("recurrence"), task.get("category"),
                                      task.get("original_text")))
                    stats["added"] += 1
                    task_id = int(cur.lastrowid)
                seen.setdefault(task["source"], set()).add(task_id)
            for source in sync_sources or []:
                keep = seen.get(source, set())
                rows = db.execute("SELECT id FROM tasks WHERE source=? AND COALESCE(archived,0)=0",
                                  (source,)).fetchall()
                for row in rows:
                    if int(row["id"]) not in keep:
                        db.execute("UPDATE tasks SET archived=1, updated_at=? WHERE id=?", (now, row["id"]))
                        stats["archived"] += 1
        return stats

    # ---------------------------------------------------------------- history
    def start_history(self, kind: str, request: str) -> int:
        with self.connect() as db:
            cur = db.execute("INSERT INTO history(kind,request,status,created_at) VALUES(?,?,'running',?)",
                             (kind, request, self.now()))
            return int(cur.lastrowid)

    def finish_history(self, history_id: int, result: dict[str, Any] | None = None, error: str | None = None):
        with self.connect() as db:
            db.execute("UPDATE history SET status=?,result_json=?,error=? WHERE id=?",
                       ("failed" if error else "complete", _json(result) if result is not None else None,
                        error, history_id))

    def history(self, limit: int = 30) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM history ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            if item["result_json"]:
                item["result"] = _loads(item.pop("result_json"), {})
            else:
                item.pop("result_json")
            result.append(item)
        return result

    # --------------------------------------------------------------- briefings
    def save_briefing(self, content: dict[str, Any]) -> int:
        with self.connect() as db:
            cur = db.execute("INSERT INTO briefings(created_at,content_json) VALUES(?,?)",
                             (self.now(), _json(content)))
            return int(cur.lastrowid)

    def briefings(self, limit: int = 15) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT id,created_at,content_json FROM briefings ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"id": r["id"], "created_at": r["created_at"], "content": _loads(r["content_json"], {})} for r in rows]

    # --------------------------------------------------------------- snapshots
    def observe_sources(self, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Track URL metadata and text digests without persisting fetched documents."""
        changes = []
        now = self.now()
        with self.connect() as db:
            for source in sources:
                url = str(source.get("canonical_url") or source.get("url") or "").strip()
                if not url:
                    continue
                text = str(source.get("content", "")) or "\n".join(map(str, source.get("excerpts", [])))
                digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
                prior = db.execute("SELECT content_hash,change_count FROM source_snapshots WHERE canonical_url=?", (url,)).fetchone()
                changed = bool(prior and prior["content_hash"] != digest)
                count = (int(prior["change_count"]) + 1) if changed else int(prior["change_count"]) if prior else 0
                db.execute("""INSERT INTO source_snapshots(canonical_url,original_url,title,content_hash,first_seen,last_seen,change_count)
                    VALUES(?,?,?,?,?,?,?) ON CONFLICT(canonical_url) DO UPDATE SET
                    original_url=excluded.original_url,title=excluded.title,content_hash=excluded.content_hash,
                    last_seen=excluded.last_seen,change_count=excluded.change_count""",
                    (url, str(source.get("original_url") or source.get("url") or url),
                     str(source.get("title") or ""), digest, now, now, count))
                if changed:
                    changes.append({"url": str(source.get("original_url") or url),
                                    "title": str(source.get("title") or ""), "change_count": count})
        return changes

    # ------------------------------------------------------------- preferences
    def get_preference(self, key: str, default: Any = None) -> Any:
        with self.connect() as db:
            row = db.execute("SELECT value_json FROM preferences WHERE key=?", (key,)).fetchone()
        return _loads(row["value_json"], default) if row else default

    def set_preference(self, key: str, value: Any) -> None:
        with self.connect() as db:
            db.execute("""INSERT INTO preferences(key,value_json,updated_at) VALUES(?,?,?)
                          ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,
                          updated_at=excluded.updated_at""",
                       (key, _json(value), self.now()))

    def preferences(self) -> dict[str, Any]:
        with self.connect() as db:
            rows = db.execute("SELECT key,value_json FROM preferences").fetchall()
        return {row["key"]: _loads(row["value_json"], None) for row in rows}

    # ------------------------------------------------------------- watchlists
    def watchlist(self, kind: str) -> list[str]:
        table = "exam_watchlist" if kind == "exam" else "organization_watchlist"
        with self.connect() as db:
            return [row["name"] for row in db.execute(f"SELECT name FROM {table} ORDER BY name")]

    def add_watchlist(self, kind: str, name: str) -> None:
        table = "exam_watchlist" if kind == "exam" else "organization_watchlist"
        clean = " ".join(name.split())[:120]
        if not clean:
            raise ValueError("Watchlist name must not be empty")
        with self.connect() as db:
            db.execute(f"INSERT OR IGNORE INTO {table}(name,created_at) VALUES(?,?)", (clean, self.now()))

    def remove_watchlist(self, kind: str, name: str) -> None:
        table = "exam_watchlist" if kind == "exam" else "organization_watchlist"
        with self.connect() as db:
            db.execute(f"DELETE FROM {table} WHERE name=?", (name,))
