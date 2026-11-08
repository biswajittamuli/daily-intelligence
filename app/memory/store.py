"""Local SQLite store: tasks, history, briefings, preferences and intelligence records.

Schema changes are additive (CREATE TABLE IF NOT EXISTS) so existing tasks, history,
briefings and source snapshots are preserved across upgrades.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY, text TEXT NOT NULL, due_date TEXT,
    status TEXT NOT NULL DEFAULT 'pending', source TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY, kind TEXT NOT NULL, request TEXT NOT NULL,
    status TEXT NOT NULL, created_at TEXT NOT NULL,
    result_json TEXT, error TEXT
);
CREATE TABLE IF NOT EXISTS briefings (
    id INTEGER PRIMARY KEY, created_at TEXT NOT NULL,
    content_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS source_snapshots (
    canonical_url TEXT PRIMARY KEY, original_url TEXT NOT NULL,
    title TEXT NOT NULL, content_hash TEXT NOT NULL,
    first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
    change_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS preferences (
    key TEXT PRIMARY KEY, value_json TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS job_listings (
    id INTEGER PRIMARY KEY,
    canonical_url TEXT NOT NULL UNIQUE, original_url TEXT NOT NULL,
    employer TEXT, title TEXT NOT NULL, location TEXT, remote TEXT,
    employment_type TEXT, experience TEXT, skills_json TEXT,
    salary TEXT, posted_date TEXT, deadline TEXT,
    status TEXT NOT NULL DEFAULT 'unverified', source_platform TEXT,
    match_score INTEGER, match_reason TEXT, evidence_json TEXT, raw_json TEXT,
    first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, last_verified TEXT
);
CREATE TABLE IF NOT EXISTS recruitment_notices (
    id INTEGER PRIMARY KEY,
    canonical_url TEXT NOT NULL UNIQUE, original_url TEXT NOT NULL,
    organization TEXT, advertisement_number TEXT, post_name TEXT, discipline TEXT,
    vacancies TEXT, qualifications TEXT, cse_eligibility TEXT DEFAULT 'not_verified',
    gate_paper TEXT, age_limit TEXT, salary TEXT, location TEXT,
    opening_date TEXT, closing_date TEXT, exam_date TEXT, selection_process TEXT,
    document_type TEXT, notification_url TEXT, application_url TEXT,
    status TEXT DEFAULT 'unverified', evidence_json TEXT, raw_json TEXT,
    first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, last_verified TEXT
);
CREATE TABLE IF NOT EXISTS exam_events (
    id INTEGER PRIMARY KEY,
    canonical_url TEXT NOT NULL UNIQUE, original_url TEXT NOT NULL,
    exam_name TEXT NOT NULL, organization TEXT, event_type TEXT, event_date TEXT,
    date_status TEXT DEFAULT 'unverified', notification_url TEXT, application_url TEXT,
    evidence_json TEXT, raw_json TEXT,
    first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, last_verified TEXT
);
CREATE TABLE IF NOT EXISTS intel_items (
    id INTEGER PRIMARY KEY,
    canonical_url TEXT NOT NULL UNIQUE, original_url TEXT NOT NULL,
    category TEXT NOT NULL, title TEXT NOT NULL, publisher TEXT,
    published_date TEXT, summary TEXT, why_it_matters TEXT,
    authors TEXT, code_url TEXT, dataset_url TEXT,
    region TEXT, topic TEXT,
    peer_reviewed TEXT DEFAULT 'not_verified', freshness TEXT DEFAULT 'unverified',
    evidence_json TEXT, raw_json TEXT,
    first_seen TEXT NOT NULL, last_seen TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS exam_watchlist (
    name TEXT PRIMARY KEY, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS organization_watchlist (
    name TEXT PRIMARY KEY, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS saved_items (
    kind TEXT NOT NULL, item_id INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'saved',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    PRIMARY KEY (kind, item_id)
);
CREATE TABLE IF NOT EXISTS search_sessions (
    id INTEGER PRIMARY KEY, category TEXT NOT NULL, request TEXT NOT NULL,
    status TEXT NOT NULL, plan_json TEXT, progress_json TEXT, summary_json TEXT,
    error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS candidate_profile (
    id INTEGER PRIMARY KEY CHECK (id = 1), profile_json TEXT NOT NULL,
    resume_filename TEXT, extracted_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS resumes (
    id INTEGER PRIMARY KEY, label TEXT NOT NULL, filename TEXT,
    profile_json TEXT NOT NULL, is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_last_seen ON job_listings(last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_notices_last_seen ON recruitment_notices(last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_exam_events_date ON exam_events(event_date);
CREATE INDEX IF NOT EXISTS idx_intel_category ON intel_items(category, last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_created ON search_sessions(created_at DESC);
"""

JSON_COLUMNS = {
    "job_listings": ("skills_json", "evidence_json", "raw_json", "resume_scores_json",
                     "sources_json", "eligibility_json"),
    "recruitment_notices": ("evidence_json", "raw_json"),
    "exam_events": ("evidence_json", "raw_json"),
    "intel_items": ("evidence_json", "raw_json"),
}


def _resume_label(filename: str | None) -> str:
    stem = Path(str(filename or "Resume")).stem
    clean = " ".join(stem.replace("_", " ").replace("-", " ").split())
    return clean[:60] or "Resume"


def _json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


SCHEMA_VERSION = 4  # bump whenever _migrate adds tables/columns


class Store:
    def __init__(self, data_dir: Path):
        data_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir = data_dir
        self.path = data_dir / "daily-intelligence.sqlite3"
        self.backup_path: Path | None = None
        self._backup_before_migration()
        with self.connect() as db:
            db.executescript(SCHEMA)
            self._migrate(db)
            db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _backup_before_migration(self) -> None:
        """Copy an existing database before any schema upgrade (sqlite online backup)."""
        if not self.path.exists() or self.path.stat().st_size == 0:
            return
        source = sqlite3.connect(self.path, timeout=10)
        try:
            version = int(source.execute("PRAGMA user_version").fetchone()[0])
            if version >= SCHEMA_VERSION:
                return
            backups = self.data_dir / "backups"
            backups.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            target_path = backups / f"daily-intelligence-{stamp}-schema{version}.sqlite3"
            target = sqlite3.connect(target_path)
            try:
                source.backup(target)
            finally:
                target.close()
            self.backup_path = target_path
        finally:
            source.close()

    @staticmethod
    def _migrate(db: sqlite3.Connection) -> None:
        """Add columns introduced after a database was first created."""
        additions = {
            "intel_items": {"region": "TEXT", "topic": "TEXT"},
            "tasks": {"due_time": "TEXT", "recurrence": "TEXT", "category": "TEXT",
                      "archived": "INTEGER NOT NULL DEFAULT 0", "original_text": "TEXT"},
            "saved_items": {"applied_at": "TEXT", "resume_id": "INTEGER", "note": "TEXT"},
            "resumes": {"stored_path": "TEXT", "status": "TEXT NOT NULL DEFAULT 'processed'",
                        "error": "TEXT", "file_size": "INTEGER", "processed_at": "TEXT"},
            "job_listings": {"best_resume_id": "INTEGER", "best_resume_label": "TEXT",
                             "resume_scores_json": "TEXT", "sources_json": "TEXT",
                             "eligibility_json": "TEXT", "discovered_via": "TEXT"},
        }
        for table, columns in additions.items():
            existing = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
            for name, kind in columns.items():
                if name not in existing:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")
        # Move the legacy single-row profile into the multi-resume table once.
        has_resumes = db.execute("SELECT COUNT(*) AS n FROM resumes").fetchone()["n"]
        legacy = db.execute("SELECT * FROM candidate_profile WHERE id=1").fetchone()
        if not has_resumes and legacy:
            label = _resume_label(legacy["resume_filename"])
            db.execute("""INSERT INTO resumes(label,filename,profile_json,is_default,created_at,updated_at)
                          VALUES(?,?,?,1,?,?)""",
                       (label, legacy["resume_filename"], legacy["profile_json"],
                        legacy["extracted_at"], legacy["updated_at"]))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()

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

    # ---------------------------------------------------------------- profile
    @staticmethod
    def _resume_row(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["profile"] = _loads(item.pop("profile_json"), {})
        item["is_default"] = bool(item.get("is_default"))
        item["is_active"] = item["is_default"]
        if isinstance(item["profile"], dict) and item["profile"] and not item["profile"].get("job_titles"):
            from app.services.job_matching import infer_job_titles
            item["profile"]["job_titles"] = infer_job_titles(item["profile"])
        # Compatibility with the single-profile API.
        item["resume_filename"] = item.get("filename")
        item["extracted_at"] = item.get("created_at")
        return item

    def resumes(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM resumes ORDER BY is_default DESC, id").fetchall()
        return [self._resume_row(row) for row in rows]

    def resume(self, resume_id: int) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM resumes WHERE id=?", (resume_id,)).fetchone()
        return self._resume_row(row) if row else None

    def add_resume(self, profile: dict[str, Any], filename: str | None = None,
                   label: str | None = None, *, make_default: bool = False,
                   stored_path: str | None = None, status: str = "processed",
                   error: str | None = None, file_size: int | None = None) -> int:
        now = self.now()
        clean_label = " ".join(str(label or "").split())[:60] or _resume_label(filename)
        with self.connect() as db:
            first = db.execute("SELECT COUNT(*) AS n FROM resumes WHERE status='processed'").fetchone()["n"] == 0
            make_default = (make_default or first) and status == "processed"
            if make_default:
                db.execute("UPDATE resumes SET is_default=0")
            cur = db.execute("""INSERT INTO resumes(label,filename,profile_json,is_default,created_at,updated_at,
                                stored_path,status,error,file_size,processed_at)
                                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                             (clean_label, filename, _json(profile), 1 if make_default else 0, now, now,
                              stored_path, status, error, file_size, now))
            first = make_default
            resume_id = int(cur.lastrowid)
            if make_default or first:
                self._sync_legacy_profile(db, profile, filename, now)
            return resume_id

    def update_resume(self, resume_id: int, *, profile: dict[str, Any] | None = None,
                      label: str | None = None, status: str | None = None,
                      error: str | None = "__keep__", stored_path: str | None = None,
                      file_size: int | None = None, filename: str | None = None) -> None:
        now = self.now()
        with self.connect() as db:
            if status is not None:
                db.execute("UPDATE resumes SET status=?, processed_at=?, updated_at=? WHERE id=?",
                           (status, now, now, resume_id))
            if error != "__keep__":
                db.execute("UPDATE resumes SET error=? WHERE id=?", (error, resume_id))
            if stored_path is not None:
                db.execute("UPDATE resumes SET stored_path=?, file_size=?, filename=COALESCE(?, filename) WHERE id=?",
                           (stored_path, file_size, filename, resume_id))
            if profile is not None:
                db.execute("UPDATE resumes SET profile_json=?, updated_at=? WHERE id=?",
                           (_json(profile), now, resume_id))
            if label is not None and " ".join(label.split()):
                db.execute("UPDATE resumes SET label=?, updated_at=? WHERE id=?",
                           (" ".join(label.split())[:60], now, resume_id))
            row = db.execute("SELECT * FROM resumes WHERE id=?", (resume_id,)).fetchone()
            if row and row["is_default"]:
                self._sync_legacy_profile(db, _loads(row["profile_json"], {}), row["filename"], now)

    def set_default_resume(self, resume_id: int) -> None:
        now = self.now()
        with self.connect() as db:
            row = db.execute("SELECT * FROM resumes WHERE id=?", (resume_id,)).fetchone()
            if not row:
                raise ValueError("Resume not found")
            if row["status"] != "processed":
                raise ValueError("This resume could not be processed; reprocess or re-upload it before activating")
            db.execute("UPDATE resumes SET is_default=CASE WHEN id=? THEN 1 ELSE 0 END", (resume_id,))
            self._sync_legacy_profile(db, _loads(row["profile_json"], {}), row["filename"], now)

    def delete_resume(self, resume_id: int) -> None:
        now = self.now()
        with self.connect() as db:
            row = db.execute("SELECT is_default FROM resumes WHERE id=?", (resume_id,)).fetchone()
            db.execute("DELETE FROM resumes WHERE id=?", (resume_id,))
            if row and row["is_default"]:
                nxt = db.execute("SELECT * FROM resumes WHERE status='processed' ORDER BY id LIMIT 1").fetchone()
                if nxt:
                    db.execute("UPDATE resumes SET is_default=1 WHERE id=?", (nxt["id"],))
                    self._sync_legacy_profile(db, _loads(nxt["profile_json"], {}), nxt["filename"], now)
                else:
                    db.execute("DELETE FROM candidate_profile WHERE id=1")

    @staticmethod
    def _sync_legacy_profile(db: sqlite3.Connection, profile: dict[str, Any],
                             filename: str | None, now: str) -> None:
        db.execute("""INSERT INTO candidate_profile(id,profile_json,resume_filename,extracted_at,updated_at)
                      VALUES(1,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                      profile_json=excluded.profile_json, resume_filename=excluded.resume_filename,
                      updated_at=excluded.updated_at""",
                   (_json(profile), filename, now, now))

    def profile(self) -> dict[str, Any] | None:
        """The default resume profile (single-profile compatibility)."""
        with self.connect() as db:
            row = db.execute("SELECT * FROM resumes WHERE is_default=1 ORDER BY id LIMIT 1").fetchone()
        return self._resume_row(row) if row else None

    def save_profile(self, profile: dict[str, Any], filename: str | None = None) -> None:
        """Replace the default resume's profile, creating one if none exists."""
        current = self.profile()
        if current:
            with self.connect() as db:
                db.execute("UPDATE resumes SET profile_json=?, filename=COALESCE(?, filename), updated_at=? WHERE id=?",
                           (_json(profile), filename, self.now(), current["id"]))
                self._sync_legacy_profile(db, profile, filename or current.get("filename"), self.now())
        else:
            self.add_resume(profile, filename, make_default=True)

    # ------------------------------------------------------------ job listings
    def upsert_jobs(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        now = self.now()
        saved = []
        with self.connect() as db:
            for record in records:
                url = str(record.get("canonical_url") or record.get("url") or "").strip()
                if not url:
                    continue
                original = str(record.get("original_url") or record.get("url") or url)
                row = db.execute("SELECT id, first_seen, sources_json FROM job_listings WHERE canonical_url=?",
                                 (url,)).fetchone()
                first_seen = row["first_seen"] if row else now
                sources = _merge_sources(_loads(row["sources_json"], []) if row else [],
                                         record.get("sources") or [])
                db.execute("""INSERT INTO job_listings(
                    canonical_url,original_url,employer,title,location,remote,employment_type,
                    experience,skills_json,salary,posted_date,deadline,status,source_platform,
                    match_score,match_reason,evidence_json,raw_json,first_seen,last_seen,last_verified,
                    best_resume_id,best_resume_label,resume_scores_json,sources_json,eligibility_json,
                    discovered_via)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(canonical_url) DO UPDATE SET
                    original_url=excluded.original_url, employer=excluded.employer, title=excluded.title,
                    location=excluded.location, remote=excluded.remote, employment_type=excluded.employment_type,
                    experience=excluded.experience, skills_json=excluded.skills_json, salary=excluded.salary,
                    posted_date=excluded.posted_date, deadline=excluded.deadline, status=excluded.status,
                    source_platform=excluded.source_platform, match_score=excluded.match_score,
                    match_reason=excluded.match_reason, evidence_json=excluded.evidence_json,
                    raw_json=excluded.raw_json, last_seen=excluded.last_seen, last_verified=excluded.last_verified,
                    best_resume_id=excluded.best_resume_id, best_resume_label=excluded.best_resume_label,
                    resume_scores_json=excluded.resume_scores_json, sources_json=excluded.sources_json,
                    eligibility_json=excluded.eligibility_json, discovered_via=excluded.discovered_via""",
                    (url, original, record.get("employer"), record.get("title") or "Untitled role",
                     record.get("location"), record.get("remote"), record.get("employment_type"),
                     record.get("experience"), _json(record.get("skills") or []), record.get("salary"),
                     record.get("posted_date"), record.get("deadline"), record.get("status") or "unverified",
                     record.get("source_platform"), record.get("match_score"), record.get("match_reason"),
                     _json(record.get("evidence") or []), _json(record.get("raw")), first_seen, now,
                     record.get("last_verified") or now, record.get("best_resume_id"),
                     record.get("best_resume_label"), _json(record.get("resume_scores")),
                     _json(sources), _json(record.get("eligibility")), record.get("discovered_via")))
                row = db.execute("SELECT * FROM job_listings WHERE canonical_url=?", (url,)).fetchone()
                saved.append(self._row(row, "job_listings"))
        return saved

    def jobs(self, *, query: str = "", status: str = "", limit: int = 100,
             fresh_only: bool = False, max_age_days: int = 45,
             stale_after_days: int = 21) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM job_listings ORDER BY COALESCE(posted_date,'') DESC, last_seen DESC LIMIT ?",
                              (max(1, min(limit, 2000)),)).fetchall()
        items = [self._row(row, "job_listings") for row in rows]
        if fresh_only:
            today = date.today()
            fresh = []
            for item in items:
                if item.get("status") in {"expired", "closed"}:
                    continue
                posted = _iso_date(item.get("posted_date"))
                if posted and (today - posted).days > max_age_days:
                    continue
                seen = _iso_date(str(item.get("last_seen") or "")[:10])
                if seen and (today - seen).days > stale_after_days:
                    continue
                fresh.append(item)
            items = fresh
        if query:
            needle = query.casefold()
            items = [item for item in items
                     if needle in " ".join(str(item.get(key) or "") for key in
                                           ("employer", "title", "location", "skills", "source_platform")).casefold()]
        if status:
            items = [item for item in items if item.get("status") == status]
        return items

    # ------------------------------------------------------ recruitment notices
    def upsert_notices(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        now = self.now()
        saved = []
        with self.connect() as db:
            for record in records:
                url = str(record.get("canonical_url") or record.get("url") or "").strip()
                if not url:
                    continue
                original = str(record.get("original_url") or record.get("url") or url)
                row = db.execute("SELECT first_seen FROM recruitment_notices WHERE canonical_url=?", (url,)).fetchone()
                first_seen = row["first_seen"] if row else now
                db.execute("""INSERT INTO recruitment_notices(
                    canonical_url,original_url,organization,advertisement_number,post_name,discipline,
                    vacancies,qualifications,cse_eligibility,gate_paper,age_limit,salary,location,
                    opening_date,closing_date,exam_date,selection_process,document_type,
                    notification_url,application_url,status,evidence_json,raw_json,
                    first_seen,last_seen,last_verified)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(canonical_url) DO UPDATE SET
                    original_url=excluded.original_url, organization=excluded.organization,
                    advertisement_number=excluded.advertisement_number, post_name=excluded.post_name,
                    discipline=excluded.discipline, vacancies=excluded.vacancies,
                    qualifications=excluded.qualifications, cse_eligibility=excluded.cse_eligibility,
                    gate_paper=excluded.gate_paper, age_limit=excluded.age_limit, salary=excluded.salary,
                    location=excluded.location, opening_date=excluded.opening_date,
                    closing_date=excluded.closing_date, exam_date=excluded.exam_date,
                    selection_process=excluded.selection_process, document_type=excluded.document_type,
                    notification_url=excluded.notification_url, application_url=excluded.application_url,
                    status=excluded.status, evidence_json=excluded.evidence_json, raw_json=excluded.raw_json,
                    last_seen=excluded.last_seen, last_verified=excluded.last_verified""",
                    (url, original, record.get("organization"), record.get("advertisement_number"),
                     record.get("post_name"), record.get("discipline"), record.get("vacancies"),
                     record.get("qualifications"), record.get("cse_eligibility") or "not_verified",
                     record.get("gate_paper"), record.get("age_limit"), record.get("salary"),
                     record.get("location"), record.get("opening_date"), record.get("closing_date"),
                     record.get("exam_date"), record.get("selection_process"), record.get("document_type"),
                     record.get("notification_url"), record.get("application_url"),
                     record.get("status") or "unverified", _json(record.get("evidence") or []),
                     _json(record.get("raw")), first_seen, now, record.get("last_verified") or now))
                row = db.execute("SELECT * FROM recruitment_notices WHERE canonical_url=?", (url,)).fetchone()
                saved.append(self._row(row, "recruitment_notices"))
        return saved

    def notices(self, *, query: str = "", limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM recruitment_notices ORDER BY COALESCE(closing_date,'') ASC, last_seen DESC LIMIT ?",
                              (max(1, min(limit, 500)),)).fetchall()
        items = [self._row(row, "recruitment_notices") for row in rows]
        if query:
            needle = query.casefold()
            items = [item for item in items
                     if needle in " ".join(str(item.get(key) or "") for key in
                                           ("organization", "post_name", "discipline", "qualifications", "location")).casefold()]
        return items

    # ------------------------------------------------------------ exam events
    def upsert_exams(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        now = self.now()
        saved = []
        with self.connect() as db:
            for record in records:
                url = str(record.get("canonical_url") or record.get("url") or "").strip()
                if not url:
                    continue
                original = str(record.get("original_url") or record.get("url") or url)
                row = db.execute("SELECT first_seen FROM exam_events WHERE canonical_url=?", (url,)).fetchone()
                first_seen = row["first_seen"] if row else now
                db.execute("""INSERT INTO exam_events(
                    canonical_url,original_url,exam_name,organization,event_type,event_date,date_status,
                    notification_url,application_url,evidence_json,raw_json,first_seen,last_seen,last_verified)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(canonical_url) DO UPDATE SET
                    original_url=excluded.original_url, exam_name=excluded.exam_name,
                    organization=excluded.organization, event_type=excluded.event_type,
                    event_date=excluded.event_date, date_status=excluded.date_status,
                    notification_url=excluded.notification_url, application_url=excluded.application_url,
                    evidence_json=excluded.evidence_json, raw_json=excluded.raw_json,
                    last_seen=excluded.last_seen, last_verified=excluded.last_verified""",
                    (url, original, record.get("exam_name") or "Examination",
                     record.get("organization"), record.get("event_type"), record.get("event_date"),
                     record.get("date_status") or "unverified", record.get("notification_url"),
                     record.get("application_url"), _json(record.get("evidence") or []),
                     _json(record.get("raw")), first_seen, now, record.get("last_verified") or now))
                row = db.execute("SELECT * FROM exam_events WHERE canonical_url=?", (url,)).fetchone()
                saved.append(self._row(row, "exam_events"))
        return saved

    def exams(self, *, query: str = "", upcoming_only: bool = False, limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM exam_events ORDER BY COALESCE(event_date,'9999') ASC, exam_name LIMIT ?",
                              (max(1, min(limit, 1000)),)).fetchall()
        items = [self._row(row, "exam_events") for row in rows]
        if query:
            needle = query.casefold()
            items = [item for item in items
                     if needle in f"{item.get('exam_name') or ''} {item.get('organization') or ''} {item.get('event_type') or ''}".casefold()]
        if upcoming_only:
            today = date.today().isoformat()
            items = [item for item in items if (item.get("event_date") or "9999") >= today]
        return items

    # ------------------------------------------------------------- intel items
    def upsert_intel(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        now = self.now()
        saved = []
        with self.connect() as db:
            for record in records:
                url = str(record.get("canonical_url") or record.get("url") or "").strip()
                if not url:
                    continue
                original = str(record.get("original_url") or record.get("url") or url)
                row = db.execute("SELECT first_seen FROM intel_items WHERE canonical_url=?", (url,)).fetchone()
                first_seen = row["first_seen"] if row else now
                db.execute("""INSERT INTO intel_items(
                    canonical_url,original_url,category,title,publisher,published_date,summary,
                    why_it_matters,authors,code_url,dataset_url,region,topic,peer_reviewed,freshness,
                    evidence_json,raw_json,first_seen,last_seen)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(canonical_url) DO UPDATE SET
                    original_url=excluded.original_url, category=excluded.category, title=excluded.title,
                    publisher=excluded.publisher, published_date=excluded.published_date,
                    summary=excluded.summary, why_it_matters=excluded.why_it_matters,
                    authors=excluded.authors, code_url=excluded.code_url, dataset_url=excluded.dataset_url,
                    region=excluded.region, topic=excluded.topic,
                    peer_reviewed=excluded.peer_reviewed, freshness=excluded.freshness,
                    evidence_json=excluded.evidence_json, raw_json=excluded.raw_json,
                    last_seen=excluded.last_seen""",
                    (url, original, record.get("category") or "news", record.get("title") or "Untitled",
                     record.get("publisher"), record.get("published_date"), record.get("summary"),
                     record.get("why_it_matters"), record.get("authors"), record.get("code_url"),
                     record.get("dataset_url"), record.get("region"), record.get("topic"),
                     record.get("peer_reviewed") or "not_verified",
                     record.get("freshness") or "unverified", _json(record.get("evidence") or []),
                     _json(record.get("raw")), first_seen, now))
                row = db.execute("SELECT * FROM intel_items WHERE canonical_url=?", (url,)).fetchone()
                saved.append(self._row(row, "intel_items"))
        return saved

    def intel(self, *, category: str = "", query: str = "", freshness: str = "",
              region: str = "", topic: str = "", limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as db:
            if category:
                rows = db.execute("SELECT * FROM intel_items WHERE category=? ORDER BY COALESCE(published_date,'') DESC, last_seen DESC LIMIT ?",
                                  (category, max(1, min(limit, 500)))).fetchall()
            else:
                rows = db.execute("SELECT * FROM intel_items ORDER BY COALESCE(published_date,'') DESC, last_seen DESC LIMIT ?",
                                  (max(1, min(limit, 500)),)).fetchall()
        items = [self._row(row, "intel_items") for row in rows]
        if query:
            needle = query.casefold()
            items = [item for item in items
                     if needle in f"{item.get('title') or ''} {item.get('summary') or ''} {item.get('publisher') or ''}".casefold()]
        if freshness:
            items = [item for item in items if item.get("freshness") == freshness]
        if region:
            items = [item for item in items if str(item.get("region") or "").casefold() == region.casefold()]
        if topic:
            needle = topic.casefold()
            items = [item for item in items
                     if needle in f"{item.get('topic') or ''} {item.get('title') or ''} {item.get('summary') or ''}".casefold()]
        return items

    def update_intel_labels(self, updates: list[dict[str, Any]]) -> None:
        with self.connect() as db:
            for update in updates:
                db.execute("UPDATE intel_items SET region=?, topic=? WHERE id=?",
                           (update.get("region"), update.get("topic"), update["id"]))

    # ------------------------------------------------------------- item state
    ITEM_STATES = {"saved", "applied", "interview", "offer", "rejected", "dismissed",
                   "follow_up", "completed", "seen"}

    def set_item_state(self, kind: str, item_id: int, state: str, *,
                       resume_id: int | None = None, note: str | None = None) -> None:
        if state not in self.ITEM_STATES:
            raise ValueError("Unsupported item state")
        now = self.now()
        with self.connect() as db:
            db.execute("""INSERT INTO saved_items(kind,item_id,state,created_at,updated_at,applied_at,resume_id,note)
                          VALUES(?,?,?,?,?,?,?,?)
                          ON CONFLICT(kind,item_id) DO UPDATE SET state=excluded.state,
                          updated_at=excluded.updated_at,
                          applied_at=COALESCE(saved_items.applied_at, excluded.applied_at),
                          resume_id=COALESCE(excluded.resume_id, saved_items.resume_id),
                          note=COALESCE(excluded.note, saved_items.note)""",
                       (kind, int(item_id), state, now, now, now if state == "applied" else None,
                        resume_id, (note or None) and " ".join(note.split())[:500]))

    def clear_item_state(self, kind: str, item_id: int) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM saved_items WHERE kind=? AND item_id=?", (kind, int(item_id)))

    def tracker(self) -> list[dict[str, Any]]:
        """Jobs in the application pipeline, joined with their listing."""
        with self.connect() as db:
            rows = db.execute("""SELECT s.state, s.applied_at, s.resume_id, s.note, s.updated_at AS state_updated_at,
                                        j.* FROM saved_items s JOIN job_listings j ON j.id=s.item_id
                                 WHERE s.kind='job' AND s.state NOT IN ('dismissed','seen')
                                 ORDER BY s.updated_at DESC""").fetchall()
        return [self._row(row, "job_listings") for row in rows]

    def item_states(self) -> dict[str, dict[int, str]]:
        with self.connect() as db:
            rows = db.execute("SELECT kind,item_id,state FROM saved_items").fetchall()
        output: dict[str, dict[int, str]] = {}
        for row in rows:
            output.setdefault(row["kind"], {})[int(row["item_id"])] = row["state"]
        return output

    def saved_items(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM saved_items ORDER BY updated_at DESC").fetchall()
        return [dict(row) for row in rows]

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

    # ------------------------------------------------------------- maintenance
    def clear_intel(self) -> dict[str, int]:
        """Remove discovered intelligence while preserving tasks, history and briefings."""
        with self.connect() as db:
            removed = {}
            for table in ("job_listings", "recruitment_notices", "exam_events",
                          "intel_items", "search_sessions", "saved_items"):
                removed[table] = int(db.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"])
                db.execute(f"DELETE FROM {table}")
            return removed

    def export_data(self) -> dict[str, Any]:
        with self.connect() as db:
            output: dict[str, Any] = {"exported_at": self.now()}
            for table in ("tasks", "history", "briefings", "preferences",
                          "job_listings", "recruitment_notices", "exam_events",
                          "intel_items", "exam_watchlist", "organization_watchlist",
                          "saved_items", "search_sessions", "candidate_profile", "resumes"):
                rows = [dict(row) for row in db.execute(f"SELECT * FROM {table}")]
                for row in rows:
                    for key in list(row):
                        if key.endswith("_json") and isinstance(row[key], str):
                            try:
                                row[key.removesuffix("_json")] = json.loads(row.pop(key))
                            except json.JSONDecodeError:
                                pass
                output[table] = rows
            return output

    # ---------------------------------------------------------------- helpers
    def counts(self) -> dict[str, int]:
        with self.connect() as db:
            def count(table: str) -> int:
                return int(db.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"])
            return {
                "jobs": count("job_listings"),
                "notices": count("recruitment_notices"),
                "exams": count("exam_events"),
                "news": int(db.execute("SELECT COUNT(*) AS n FROM intel_items WHERE category='news'").fetchone()["n"]),
                "papers": int(db.execute("SELECT COUNT(*) AS n FROM intel_items WHERE category='papers'").fetchone()["n"]),
            }

    def update_job_matches(self, updates: list[dict[str, Any]]) -> None:
        with self.connect() as db:
            for update in updates:
                db.execute("""UPDATE job_listings SET match_score=?, match_reason=?, best_resume_id=?,
                              best_resume_label=?, resume_scores_json=?,
                              eligibility_json=COALESCE(?, eligibility_json) WHERE id=?""",
                           (update.get("match_score"), update.get("match_reason"),
                            update.get("best_resume_id"), update.get("best_resume_label"),
                            _json(update.get("resume_scores")), _json(update.get("eligibility")),
                            update["id"]))

    def _row(self, row: sqlite3.Row, table: str) -> dict[str, Any]:
        item = dict(row)
        for column in JSON_COLUMNS.get(table, ()):
            if column not in item:
                continue
            key = column.removesuffix("_json")
            item[key] = _loads(item.pop(column), [] if key in {"skills", "evidence", "resume_scores",
                                                               "sources"} else {})
        return item


def _merge_sources(existing: list[Any], new: list[Any]) -> list[dict[str, Any]]:
    """Keep every distinct source reference for a listing (platform + URL)."""
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in list(existing or []) + list(new or []):
        if not isinstance(item, dict) or not item.get("url"):
            continue
        key = str(item["url"]).rstrip("/").casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append({"platform": item.get("platform"), "url": item["url"],
                       "via": item.get("via")})
    return output[:12]


def _iso_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None
