"""Local SQLite store: tasks, history, briefings, preferences and intelligence records.

Schema changes are additive (CREATE TABLE IF NOT EXISTS) so existing tasks, history,
briefings and source snapshots are preserved across upgrades.
"""
from __future__ import annotations

import hashlib
import json
import re
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
CREATE TABLE IF NOT EXISTS employers (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, normalized_name TEXT NOT NULL, domain TEXT,
    website TEXT, headquarters TEXT, locations_json TEXT, industry TEXT, description TEXT,
    classification TEXT DEFAULT 'unknown', country TEXT, funding_json TEXT, career_url TEXT,
    ats_provider TEXT, ats_slug TEXT, career_status TEXT, discovery_sources_json TEXT,
    aliases_json TEXT, evidence_json TEXT, first_discovered TEXT NOT NULL, last_discovery TEXT NOT NULL,
    last_career_check TEXT, open_jobs INTEGER DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_employers_domain ON employers(domain) WHERE domain IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_employers_name ON employers(normalized_name);
CREATE TABLE IF NOT EXISTS employer_signals (
    id INTEGER PRIMARY KEY, employer_id INTEGER, company_name TEXT NOT NULL, signal_type TEXT NOT NULL,
    title TEXT, detail TEXT, amount TEXT, source_url TEXT NOT NULL, publisher TEXT, signal_date TEXT,
    evidence TEXT, first_seen TEXT NOT NULL,
    UNIQUE(source_url, signal_type, company_name)
);
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY, job_id INTEGER, company TEXT, role TEXT NOT NULL, job_url TEXT,
    resume_id INTEGER, status TEXT NOT NULL DEFAULT 'interested', applied_at TEXT,
    recruiter_name TEXT, recruiter_contact TEXT, interview_dates_json TEXT, follow_up_date TEXT,
    next_action TEXT, notes TEXT, history_json TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_applications_job ON applications(job_id) WHERE job_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_jobs_last_seen ON job_listings(last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_notices_last_seen ON recruitment_notices(last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_exam_events_date ON exam_events(event_date);
CREATE INDEX IF NOT EXISTS idx_intel_category ON intel_items(category, last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_created ON search_sessions(created_at DESC);
CREATE TABLE IF NOT EXISTS source_reports (
    id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL, source_key TEXT NOT NULL, name TEXT NOT NULL,
    category TEXT, domain TEXT, method TEXT, state TEXT NOT NULL, started_at TEXT, completed_at TEXT,
    http_status INTEGER, queries INTEGER, search_results INTEGER, fetched INTEGER, parsed INTEGER,
    listings INTEGER, unique_count INTEGER, duplicates INTEGER, rejected INTEGER, stored INTEGER, verified INTEGER,
    retries INTEGER, duration_ms INTEGER, failure_reason TEXT, detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_source_reports_session ON source_reports(session_id);
CREATE TABLE IF NOT EXISTS source_health (
    source_key TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT, domain TEXT, method TEXT,
    last_state TEXT, last_success_at TEXT, last_failure_at TEXT, last_failure_reason TEXT,
    success_count INTEGER NOT NULL DEFAULT 0, failure_count INTEGER NOT NULL DEFAULT 0,
    last_listings INTEGER, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS job_exclusions (
    id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL, url TEXT, title TEXT, employer TEXT, source TEXT,
    reason TEXT NOT NULL, stage TEXT, detail TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_job_exclusions_session ON job_exclusions(session_id, reason);
CREATE TABLE IF NOT EXISTS listing_reports (
    id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL, reason TEXT NOT NULL, note TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS source_state (
    source_id TEXT PRIMARY KEY, enabled INTEGER, last_attempt_at TEXT, last_success_at TEXT, last_result_at TEXT,
    last_state TEXT, last_failure_reason TEXT, attempts INTEGER NOT NULL DEFAULT 0, successes INTEGER NOT NULL DEFAULT 0,
    partials INTEGER NOT NULL DEFAULT 0, failures INTEGER NOT NULL DEFAULT 0, consecutive_failures INTEGER NOT NULL DEFAULT 0,
    results_total INTEGER NOT NULL DEFAULT 0, last_results INTEGER, last_unique INTEGER,
    extraction_ok INTEGER NOT NULL DEFAULT 0, extraction_total INTEGER NOT NULL DEFAULT 0,
    verification_ok INTEGER NOT NULL DEFAULT 0, verification_total INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT, updated_at TEXT
);
"""

JSON_COLUMNS = {
    "job_listings": ("skills_json", "evidence_json", "raw_json", "resume_scores_json",
                     "sources_json", "eligibility_json", "verify_history_json", "conflicts_json"),
    "employers": ("locations_json", "funding_json", "discovery_sources_json", "aliases_json", "evidence_json",
                  "career_discovery_json"),
    "applications": ("interview_dates_json", "history_json"),
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


SCHEMA_VERSION = 10  # bump whenever _migrate adds tables/columns


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
            "tasks": {"due_time": "TEXT", "recurrence": "TEXT", "category": "TEXT",
                      "archived": "INTEGER NOT NULL DEFAULT 0", "original_text": "TEXT"},
            "saved_items": {"applied_at": "TEXT", "resume_id": "INTEGER", "note": "TEXT"},
            "resumes": {"stored_path": "TEXT", "status": "TEXT NOT NULL DEFAULT 'processed'",
                        "error": "TEXT", "file_size": "INTEGER", "processed_at": "TEXT"},
            "job_listings": {"best_resume_id": "INTEGER", "best_resume_label": "TEXT",
                             "resume_scores_json": "TEXT", "sources_json": "TEXT",
                             "eligibility_json": "TEXT", "discovered_via": "TEXT",
                             "updated_date": "TEXT", "employer_url": "TEXT", "application_url": "TEXT",
                             "requisition_id": "TEXT", "status_evidence": "TEXT", "repost_of": "INTEGER",
                             "verify_history_json": "TEXT", "missing_count": "INTEGER DEFAULT 0",
                             "employer_id": "INTEGER", "dedup_key": "TEXT",
                             # v6: canonical schema + evidence
                             "extraction_method": "TEXT", "evidence_confidence": "INTEGER", "ats_ref": "TEXT",
                             "salary_currency": "TEXT", "education": "TEXT", "conflicts_json": "TEXT",
                             "retrieved_at": "TEXT", "verification_source": "TEXT",
                             # v9: posting-date provenance
                             "posted_date_source": "TEXT", "posting_date_confidence": "TEXT"},
            "employers": {"career_discovery_json": "TEXT", "career_outcome": "TEXT", "next_discovery_at": "TEXT",
                          "discovery_attempts": "INTEGER DEFAULT 0", "last_discovery_method": "TEXT",
                          "last_discovery_success": "TEXT",
                          # v8: registry fields
                          "city": "TEXT", "stage": "TEXT", "followed": "INTEGER NOT NULL DEFAULT 0",
                          "verification_status": "TEXT"},
            "intel_items": {"region": "TEXT", "topic": "TEXT", "updated_date": "TEXT"},
        }
        for table, columns in additions.items():
            existing = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
            for name, kind in columns.items():
                if name not in existing:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")
        # Existing tracked jobs become application records once (history preserved).
        if not db.execute("SELECT COUNT(*) AS n FROM applications").fetchone()["n"]:
            state_map = {"saved": "saved", "applied": "applied", "interview": "interview", "offer": "offer",
                         "rejected": "rejected", "follow_up": "applied"}
            for row in db.execute("""SELECT s.item_id, s.state, s.applied_at, s.resume_id, s.note, s.created_at,
                                     s.updated_at, j.title, j.employer, j.original_url FROM saved_items s
                                     JOIN job_listings j ON j.id=s.item_id WHERE s.kind='job'""").fetchall():
                if row["state"] in state_map:
                    db.execute("""INSERT OR IGNORE INTO applications(job_id,company,role,job_url,resume_id,status,
                                  applied_at,notes,history_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                               (row["item_id"], row["employer"], row["title"], row["original_url"], row["resume_id"],
                                state_map[row["state"]], row["applied_at"], row["note"],
                                _json([{"status": state_map[row["state"]], "at": row["updated_at"]}]),
                                row["created_at"], row["updated_at"]))
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
        """Insert or update listings.

        Cross-source dedup: a listing with the same employer + normalized title + city (and
        no conflicting requisition id) as an *open* stored listing is the same opening seen on
        another source — its URL is added to that listing's sources instead of a new row.
        Repost: the same key on a new URL while the stored listing is closed/expired creates a
        new row linked via ``repost_of`` (history preserved).
        """
        now = self.now()
        saved = []
        with self.connect() as db:
            for record in records:
                url = str(record.get("canonical_url") or record.get("url") or "").strip()
                if not url:
                    continue
                original = str(record.get("original_url") or record.get("url") or url)
                key = dedup_key(record)
                row = db.execute("SELECT id, first_seen, sources_json, verify_history_json, repost_of, posted_date, "
                                 "posting_date_confidence, posted_date_source FROM job_listings "
                                 "WHERE canonical_url=?", (url,)).fetchone()
                from app.services.freshness import date_confidence, stronger_date
                record = dict(record)
                record["posting_date_confidence"] = record.get("posting_date_confidence") or \
                    date_confidence(record.get("posted_date_source"), record.get("posted_date"))
                if row is not None and row["posted_date"] and not stronger_date(
                        record.get("posted_date"), record["posting_date_confidence"], row["posted_date"],
                        row["posting_date_confidence"] or "low"):
                    # Keep the better-evidenced stored date; a re-fetch never downgrades it.
                    record["posted_date"], record["posted_date_source"] = row["posted_date"], row["posted_date_source"]
                    record["posting_date_confidence"] = row["posting_date_confidence"]
                repost_of = row["repost_of"] if row else None
                if row is None and key:
                    twins = db.execute("SELECT id, canonical_url, status, requisition_id, sources_json FROM job_listings "
                                       "WHERE dedup_key=? ORDER BY id DESC", (key,)).fetchall()
                    req = record.get("requisition_id")
                    # Same requisition id first; then a twin without one. A different id is a different opening.
                    twin = next((t for t in twins if req and t["requisition_id"] == req), None) or \
                        next((t for t in twins if not req or not t["requisition_id"]), None)
                    if twin is not None:
                        if twin["status"] in {"closed", "expired"}:
                            repost_of = twin["id"]
                        else:
                            self._merge_twin(db, twin["id"], record, original, now)
                            saved.append(self._row(db.execute("SELECT * FROM job_listings WHERE id=?",
                                                              (twin["id"],)).fetchone(), "job_listings"))
                            continue
                first_seen = row["first_seen"] if row else now
                sources = _merge_sources(_loads(row["sources_json"], []) if row else [],
                                         (record.get("sources") or []) or [{"platform": record.get("source_platform"),
                                                                            "url": original, "via": record.get("discovered_via")}])
                history = _loads(row["verify_history_json"], []) if row else []
                if record.get("verification"):
                    history = (history + [record["verification"]])[-20:]
                db.execute("""INSERT INTO job_listings(
                    canonical_url,original_url,employer,title,location,remote,employment_type,
                    experience,skills_json,salary,posted_date,deadline,status,source_platform,
                    match_score,match_reason,evidence_json,raw_json,first_seen,last_seen,last_verified,
                    best_resume_id,best_resume_label,resume_scores_json,sources_json,eligibility_json,
                    discovered_via,updated_date,employer_url,application_url,requisition_id,status_evidence,
                    repost_of,verify_history_json,employer_id,dedup_key,extraction_method,evidence_confidence,
                    ats_ref,salary_currency,education,retrieved_at,verification_source,posted_date_source,
                    posting_date_confidence)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(canonical_url) DO UPDATE SET
                    original_url=excluded.original_url, employer=COALESCE(excluded.employer, job_listings.employer),
                    title=excluded.title, location=COALESCE(excluded.location, job_listings.location),
                    remote=excluded.remote, employment_type=COALESCE(excluded.employment_type, job_listings.employment_type),
                    experience=excluded.experience, skills_json=excluded.skills_json, salary=excluded.salary,
                    posted_date=COALESCE(excluded.posted_date, job_listings.posted_date),
                    posted_date_source=COALESCE(excluded.posted_date_source, job_listings.posted_date_source),
                    posting_date_confidence=COALESCE(excluded.posting_date_confidence, job_listings.posting_date_confidence),
                    deadline=COALESCE(excluded.deadline, job_listings.deadline), status=excluded.status,
                    source_platform=excluded.source_platform, match_score=excluded.match_score,
                    match_reason=excluded.match_reason, evidence_json=excluded.evidence_json,
                    raw_json=excluded.raw_json, last_seen=excluded.last_seen,
                    last_verified=COALESCE(excluded.last_verified, job_listings.last_verified),
                    best_resume_id=excluded.best_resume_id, best_resume_label=excluded.best_resume_label,
                    resume_scores_json=excluded.resume_scores_json, sources_json=excluded.sources_json,
                    eligibility_json=excluded.eligibility_json, discovered_via=excluded.discovered_via,
                    updated_date=COALESCE(excluded.updated_date, job_listings.updated_date),
                    employer_url=COALESCE(excluded.employer_url, job_listings.employer_url),
                    application_url=COALESCE(excluded.application_url, job_listings.application_url),
                    requisition_id=COALESCE(excluded.requisition_id, job_listings.requisition_id),
                    status_evidence=COALESCE(excluded.status_evidence, job_listings.status_evidence),
                    verify_history_json=excluded.verify_history_json,
                    employer_id=COALESCE(excluded.employer_id, job_listings.employer_id),
                    dedup_key=excluded.dedup_key, missing_count=0,
                    extraction_method=COALESCE(excluded.extraction_method, job_listings.extraction_method),
                    evidence_confidence=COALESCE(excluded.evidence_confidence, job_listings.evidence_confidence),
                    ats_ref=COALESCE(excluded.ats_ref, job_listings.ats_ref),
                    salary_currency=COALESCE(excluded.salary_currency, job_listings.salary_currency),
                    education=COALESCE(excluded.education, job_listings.education),
                    retrieved_at=excluded.retrieved_at,
                    verification_source=COALESCE(excluded.verification_source, job_listings.verification_source)""",
                    (url, original, record.get("employer"), record.get("title") or "Untitled role",
                     record.get("location"), record.get("remote"), record.get("employment_type"),
                     record.get("experience"), _json(record.get("skills") or []), record.get("salary"),
                     record.get("posted_date"), record.get("deadline"), record.get("status") or "unverified",
                     record.get("source_platform"), record.get("match_score"), record.get("match_reason"),
                     _json(record.get("evidence") or []), _json(record.get("raw")), first_seen, now,
                     record.get("last_verified"), record.get("best_resume_id"),
                     record.get("best_resume_label"), _json(record.get("resume_scores")),
                     _json(sources), _json(record.get("eligibility")), record.get("discovered_via"),
                     record.get("updated_date"), record.get("employer_url"), record.get("application_url"),
                     record.get("requisition_id"), record.get("status_evidence"), repost_of,
                     _json(history), record.get("employer_id"), key, record.get("extraction_method"),
                     record.get("evidence_confidence"), record.get("ats_ref"), record.get("salary_currency"),
                     record.get("education"), record.get("retrieved_at") or now, record.get("verification_source"),
                     record.get("posted_date_source"), record.get("posting_date_confidence")))
                row = db.execute("SELECT * FROM job_listings WHERE canonical_url=?", (url,)).fetchone()
                saved.append(self._row(row, "job_listings"))
        return saved

    OFFICIAL_VIA = {"company career board", "company career page"}

    def _merge_twin(self, db: sqlite3.Connection, twin_id: int, record: dict[str, Any], original: str, now: str) -> None:
        """Same opening seen on another source: keep one row, every source reference, and any contradictions.

        When the new sighting comes from the employer's own board or career page and the stored row does
        not, the employer page becomes the official application destination and status evidence.
        """
        twin = db.execute("SELECT * FROM job_listings WHERE id=?", (twin_id,)).fetchone()
        via = record.get("discovered_via")
        merged = _merge_sources(_loads(twin["sources_json"], []),
                                (record.get("sources") or []) + [{"platform": record.get("source_platform"),
                                                                  "url": original, "via": via or "duplicate",
                                                                  "method": record.get("extraction_method"),
                                                                  "retrieved_at": now}])
        conflicts = _loads(twin["conflicts_json"], []) or []
        for field in ("posted_date", "deadline", "location"):
            new, old = record.get(field), twin[field]
            if new and old and str(new)[:10] != str(old)[:10] and \
                    not any(c.get("field") == field and c.get("value") == new for c in conflicts):
                conflicts.append({"field": field, "stored": old, "value": new, "source": original, "seen_at": now})
        new_status = record.get("status")
        if new_status in {"closed", "expired"} and twin["status"] not in {"closed", "expired"}:
            conflicts.append({"field": "status", "stored": twin["status"], "value": new_status, "source": original,
                              "seen_at": now})
        fields = {"sources_json": _json(merged), "last_seen": now, "conflicts_json": _json(conflicts[-12:]) if conflicts else None}
        if record.get("requisition_id") and not twin["requisition_id"]:
            fields["requisition_id"] = record["requisition_id"]
        official_new = via in self.OFFICIAL_VIA
        official_old = twin["discovered_via"] in self.OFFICIAL_VIA
        if official_new and not official_old:
            fields.update({"application_url": record.get("application_url") or original, "employer_url": original,
                           "discovered_via": via, "verification_source": "employer page (merged duplicate)"})
            if via == "company career board":
                fields.update({"status": "open", "last_verified": now,
                               "status_evidence": "Listed on the employer's public job board"})
            for column in ("posted_date", "employer_id", "ats_ref", "extraction_method"):
                if record.get(column) and not twin[column]:
                    fields[column] = record[column]
        db.execute(f"UPDATE job_listings SET {', '.join(k + '=?' for k in fields)} WHERE id=?", (*fields.values(), twin_id))

    def record_verification(self, job_id: int, *, status: str | None, evidence: str, outcome: str,
                            missing: bool = False, posted_date: str | None = None,
                            raw_text: str | None = None) -> dict[str, Any]:
        """Store a re-verification result and its history (never deletes the listing)."""
        now = self.now()
        with self.connect() as db:
            row = db.execute("SELECT * FROM job_listings WHERE id=?", (job_id,)).fetchone()
            if not row:
                raise ValueError("Listing not found")
            history = _loads(row["verify_history_json"], [])
            history = (history + [{"at": now, "outcome": outcome, "status": status or row["status"],
                                   "evidence": evidence[:300]}])[-20:]
            missing_count = (int(row["missing_count"] or 0) + 1) if missing else 0
            fields = {"verify_history_json": _json(history), "missing_count": missing_count,
                      "status_evidence": evidence[:500]}
            if status:
                fields["status"] = status
            if outcome in {"verified_open", "closed", "expired"}:
                fields["last_verified"] = now
                fields["verification_source"] = ("employer public job board" if evidence.startswith("Listed on") else
                                                 "employer page" if evidence.startswith(("Employer page", "JobPosting")) else
                                                 "third-party listing page")
            if posted_date and (not row["posted_date"] or (row["posting_date_confidence"] or "low") in {"low", "unknown"}):
                fields["posted_date"] = posted_date
                fields["posted_date_source"] = "employer ATS" if evidence.startswith("Listed on") else "JobPosting datePosted"
                fields["posting_date_confidence"] = "high"
            if raw_text:
                raw = _loads(row["raw_json"], {}) or {}
                raw["raw_text"] = raw_text[:8000]
                fields["raw_json"] = _json(raw)
            db.execute(f"UPDATE job_listings SET {', '.join(k + '=?' for k in fields)} WHERE id=?",
                       (*fields.values(), job_id))
            return self._row(db.execute("SELECT * FROM job_listings WHERE id=?", (job_id,)).fetchone(), "job_listings")

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
                if record.get("updated_date"):
                    db.execute("UPDATE intel_items SET updated_date=? WHERE canonical_url=?", (record["updated_date"], url))
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

    # -------------------------------------------------------------- employers
    @staticmethod
    def _norm_company(name: str) -> str:
        from app.services.employer_discovery import normalize_name
        return normalize_name(name)

    def find_employer(self, name: str = "", domain: str | None = None) -> dict[str, Any] | None:
        norm = self._norm_company(name) if name else ""
        with self.connect() as db:
            row = None
            if domain:
                row = db.execute("SELECT * FROM employers WHERE domain=?", (domain,)).fetchone()
            if row is None and norm:
                row = db.execute("SELECT * FROM employers WHERE normalized_name=?", (norm,)).fetchone()
            if row is None and norm:
                for candidate in db.execute("SELECT * FROM employers WHERE aliases_json LIKE ?", (f"%{name}%",)).fetchall():
                    if norm in {self._norm_company(a) for a in _loads(candidate["aliases_json"], [])}:
                        row = candidate
                        break
        return self._row(row, "employers") if row else None

    def upsert_employer(self, record: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        """Insert or merge an employer; dedup by registrable domain, normalized name, then aliases."""
        from app.services.employer_discovery import _registrable
        now = self.now()
        name = " ".join(str(record.get("name") or "").split())[:80]
        if not name:
            raise ValueError("Employer needs a name")
        domain = record.get("domain")
        domain = _registrable(domain) if domain else None
        existing = self.find_employer(name, domain)
        with self.connect() as db:
            if existing is None:
                cur = db.execute("""INSERT INTO employers(name,normalized_name,domain,website,headquarters,locations_json,
                    industry,description,classification,country,funding_json,career_url,ats_provider,ats_slug,
                    career_status,discovery_sources_json,aliases_json,evidence_json,first_discovered,last_discovery,
                    last_career_check,open_jobs) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (name, self._norm_company(name), domain, record.get("website"), record.get("headquarters"),
                     _json(record.get("locations") or []), record.get("industry"), record.get("description"),
                     record.get("classification") or "unknown", record.get("country"),
                     _json(record.get("funding") or []), record.get("career_url"), record.get("ats_provider"),
                     record.get("ats_slug"), record.get("career_status"), _json(record.get("discovery_sources") or []),
                     _json([name]), _json(record.get("evidence") or []), now, now, record.get("last_career_check"),
                     int(record.get("open_jobs") or 0)))
                db.execute("UPDATE employers SET city=?, stage=?, verification_status=? WHERE id=?",
                           (record.get("city"), record.get("stage"), record.get("verification_status"), cur.lastrowid))
                row = db.execute("SELECT * FROM employers WHERE id=?", (cur.lastrowid,)).fetchone()
                return self._row(row, "employers"), True
            aliases = list(dict.fromkeys((existing.get("aliases") or []) + [name]))[:10]
            sources = list(dict.fromkeys((existing.get("discovery_sources") or []) + list(record.get("discovery_sources") or [])))[:20]
            evidence = (list(record.get("evidence") or []) + (existing.get("evidence") or []))[:8]
            funding = (list(record.get("funding") or []) + (existing.get("funding") or []))[:6]
            classification = existing.get("classification") if existing.get("classification") not in {None, "unknown"} \
                else record.get("classification") or "unknown"
            db.execute("""UPDATE employers SET domain=COALESCE(domain, ?), website=COALESCE(website, ?),
                country=COALESCE(country, ?), classification=?, career_url=COALESCE(?, career_url),
                ats_provider=COALESCE(?, ats_provider), ats_slug=COALESCE(?, ats_slug),
                career_status=COALESCE(?, career_status), discovery_sources_json=?, aliases_json=?, evidence_json=?,
                funding_json=?, last_discovery=?, last_career_check=COALESCE(?, last_career_check),
                open_jobs=CASE WHEN ? > 0 THEN ? ELSE open_jobs END WHERE id=?""",
                (domain, record.get("website"), record.get("country"), classification, record.get("career_url"),
                 record.get("ats_provider"), record.get("ats_slug"), record.get("career_status"), _json(sources),
                 _json(aliases), _json(evidence), _json(funding), now, record.get("last_career_check"),
                 int(record.get("open_jobs") or 0), int(record.get("open_jobs") or 0), existing["id"]))
            db.execute("""UPDATE employers SET city=COALESCE(city, ?), stage=COALESCE(?, stage),
                          verification_status=COALESCE(?, verification_status) WHERE id=?""",
                       (record.get("city"), record.get("stage"), record.get("verification_status"), existing["id"]))
            row = db.execute("SELECT * FROM employers WHERE id=?", (existing["id"],)).fetchone()
            return self._row(row, "employers"), False

    def employers(self, *, limit: int = 500) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("""SELECT e.*, (SELECT COUNT(*) FROM employer_signals s WHERE s.employer_id=e.id) AS signal_count,
                                        (SELECT COUNT(*) FROM job_listings j WHERE j.employer_id=e.id
                                         AND j.status NOT IN ('closed','expired')) AS stored_jobs
                                 FROM employers e ORDER BY e.last_discovery DESC LIMIT ?""", (limit,)).fetchall()
        return [self._row(row, "employers") for row in rows]

    def add_signal(self, signal: dict[str, Any]) -> bool:
        with self.connect() as db:
            cur = db.execute("""INSERT OR IGNORE INTO employer_signals(employer_id,company_name,signal_type,title,detail,
                                amount,source_url,publisher,signal_date,evidence,first_seen) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                             (signal.get("employer_id"), signal["company_name"], signal["signal_type"],
                              signal.get("title"), signal.get("detail"), signal.get("amount"), signal["source_url"],
                              signal.get("publisher"), signal.get("signal_date"), signal.get("evidence"), self.now()))
            return cur.rowcount > 0

    def signals(self, *, limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM employer_signals ORDER BY COALESCE(signal_date, first_seen) DESC LIMIT ?",
                              (limit,)).fetchall()
        return [dict(row) for row in rows]

    def link_jobs_to_employers(self) -> int:
        """Attach stored listings to employers by normalized employer name (no fuzzy guessing)."""
        from app.services.listing_links import infer_employer
        linked = 0
        with self.connect() as db:
            # Backfill employers that are evident from the URL, recruitment subdomain, title or page links.
            for row in db.execute("SELECT id, original_url, title, raw_json, evidence_json FROM job_listings "
                                  "WHERE employer IS NULL OR employer=''").fetchall():
                name, how = infer_employer(row["original_url"] or "", row["title"] or "",
                                           f"{row['evidence_json'] or ''} {row['raw_json'] or ''}"[:40000])
                if name:
                    raw = _loads(row["raw_json"], {}) or {}
                    if isinstance(raw, dict):
                        raw["employer_source"] = how
                    db.execute("UPDATE job_listings SET employer=?, raw_json=? WHERE id=?", (name, _json(raw), row["id"]))
            employers = {row["normalized_name"]: row["id"] for row in db.execute("SELECT id, normalized_name FROM employers")}
            for row in db.execute("SELECT id, employer FROM job_listings WHERE employer_id IS NULL AND employer IS NOT NULL").fetchall():
                employer_id = employers.get(self._norm_company(row["employer"]))
                if employer_id:
                    db.execute("UPDATE job_listings SET employer_id=? WHERE id=?", (employer_id, row["id"]))
                    linked += 1
        return linked

    # ----------------------------------------------------------- applications
    APPLICATION_STATUSES = ["interested", "saved", "preparing", "applied", "assessment", "interview",
                            "offer", "rejected", "withdrawn", "closed"]

    def applications(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("""SELECT a.*, j.status AS job_status, j.match_score, j.location, j.posted_date,
                                        j.deadline, j.last_verified, j.eligibility_json
                                 FROM applications a LEFT JOIN job_listings j ON j.id=a.job_id
                                 ORDER BY a.updated_at DESC""").fetchall()
        output = []
        for row in rows:
            item = self._row(row, "applications")
            item["eligibility"] = _loads(item.pop("eligibility_json", None), {})
            output.append(item)
        return output

    def application(self, app_id: int) -> dict[str, Any] | None:
        return next((item for item in self.applications() if item["id"] == app_id), None)

    def save_application(self, values: dict[str, Any], app_id: int | None = None) -> dict[str, Any]:
        """Create/update an application record; status changes are appended to history."""
        now = self.now()
        allowed = {"job_id", "company", "role", "job_url", "resume_id", "status", "applied_at", "recruiter_name",
                   "recruiter_contact", "interview_dates", "follow_up_date", "next_action", "notes"}
        clean = {key: value for key, value in values.items() if key in allowed}
        if "status" in clean and clean["status"] not in self.APPLICATION_STATUSES:
            raise ValueError("Unknown application status")
        for key in ("company", "role", "job_url", "recruiter_name", "recruiter_contact", "next_action"):
            if key in clean and clean[key] is not None:
                clean[key] = " ".join(str(clean[key]).split())[:300] or None
        if "notes" in clean and clean["notes"] is not None:
            clean["notes"] = str(clean["notes"])[:4000]
        for key in ("applied_at", "follow_up_date"):
            if clean.get(key):
                value = _iso_date(clean[key])
                if value is None:
                    raise ValueError(f"{key} must be a date (YYYY-MM-DD)")
                clean[key] = value.isoformat()
        if "interview_dates" in clean:
            dates = []
            for item in clean.pop("interview_dates") or []:
                text = str(item.get("at") if isinstance(item, dict) else item)[:16]
                try:
                    datetime.fromisoformat(text)
                except ValueError:
                    raise ValueError("Interview dates must be YYYY-MM-DD or YYYY-MM-DDTHH:MM")
                dates.append({"at": text, "note": (item.get("note") if isinstance(item, dict) else None)})
            clean["interview_dates_json"] = _json(dates)
        with self.connect() as db:
            if app_id is None and clean.get("job_id"):
                row = db.execute("SELECT id FROM applications WHERE job_id=?", (clean["job_id"],)).fetchone()
                app_id = row["id"] if row else None
            if app_id is None:
                if not clean.get("role"):
                    raise ValueError("An application needs a role")
                status = clean.get("status") or "interested"
                if status == "applied" and not clean.get("applied_at"):
                    clean["applied_at"] = date.today().isoformat()
                clean.update(status=status, history_json=_json([{"status": status, "at": now}]),
                             created_at=now, updated_at=now)
                columns = ", ".join(clean)
                cur = db.execute(f"INSERT INTO applications({columns}) VALUES({', '.join('?' for _ in clean)})",
                                 tuple(clean.values()))
                app_id = int(cur.lastrowid)
            else:
                row = db.execute("SELECT status, history_json, applied_at FROM applications WHERE id=?", (app_id,)).fetchone()
                if not row:
                    raise ValueError("Application not found")
                if clean.get("status") and clean["status"] != row["status"]:
                    history = _loads(row["history_json"], []) + [{"status": clean["status"], "at": now}]
                    clean["history_json"] = _json(history[-40:])
                    if clean["status"] == "applied" and not row["applied_at"] and not clean.get("applied_at"):
                        clean["applied_at"] = date.today().isoformat()
                clean["updated_at"] = now
                db.execute(f"UPDATE applications SET {', '.join(k + '=?' for k in clean)} WHERE id=?",
                           (*clean.values(), app_id))
        return self.application(app_id)

    def delete_application(self, app_id: int) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM applications WHERE id=?", (app_id,))

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
                    "last_success_at": now if state in {"successful", "partial"} else (row["last_success_at"] if row else None),
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

    REPORT_REASONS = {"closed", "wrong_location", "wrong_details", "duplicate", "not_a_job", "scam", "other"}

    def report_listing(self, job_id: int, reason: str, note: str | None = None) -> None:
        if reason not in self.REPORT_REASONS:
            raise ValueError("Unsupported report reason")
        with self.connect() as db:
            db.execute("INSERT INTO listing_reports(job_id,reason,note,created_at) VALUES(?,?,?,?)",
                       (int(job_id), reason, (note or None) and " ".join(note.split())[:500], self.now()))

    def reported_listings(self) -> dict[int, list[dict[str, Any]]]:
        with self.connect() as db:
            output: dict[int, list[dict[str, Any]]] = {}
            for row in db.execute("SELECT * FROM listing_reports ORDER BY id"):
                output.setdefault(row["job_id"], []).append(dict(row))
            return output

    def unreport_listing(self, job_id: int) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM listing_reports WHERE job_id=?", (int(job_id),))

    def set_employer_followed(self, employer_id: int, followed: bool) -> None:
        with self.connect() as db:
            db.execute("UPDATE employers SET followed=? WHERE id=?", (int(followed), employer_id))

    def followed_employers(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [self._row(row, "employers") for row in db.execute("SELECT * FROM employers WHERE followed=1")]

    def save_career_discovery(self, employer_id: int, result: dict[str, Any]) -> None:
        """Store a career-discovery outcome (methods attempted, last success, next retry) on an employer."""
        ats = result.get("ats") or {}
        status = result.get("outcome_label") or result.get("outcome")
        compact = {k: result.get(k) for k in ("outcome", "outcome_label", "career_url", "candidates", "ats", "ats_all",
                                              "jobs_endpoint", "methods", "checked_at", "homepage_status", "attempts",
                                              "last_method", "last_success_at", "next_retry_at", "homepage_fingerprint",
                                              "homepage_changed")}
        compact["listings_found"] = len(result.get("listings") or [])
        with self.connect() as db:
            db.execute("""UPDATE employers SET career_discovery_json=?, career_outcome=?, next_discovery_at=?,
                          discovery_attempts=?, last_discovery_method=COALESCE(?, last_discovery_method),
                          last_discovery_success=COALESCE(?, last_discovery_success), career_status=?,
                          career_url=COALESCE(?, career_url), last_career_check=?,
                          verification_status=CASE WHEN ? IN ('career_verified') THEN 'career page verified'
                               WHEN ? IN ('ats_identified','jobs_endpoint') THEN 'job board verified'
                               ELSE COALESCE(verification_status, 'website checked') END,
                          ats_provider=COALESCE(?, ats_provider),
                          ats_slug=CASE WHEN ? THEN COALESCE(?, ats_slug) ELSE ats_slug END WHERE id=?""",
                       (_json(compact), result.get("outcome"), result.get("next_retry_at"), result.get("attempts") or 1,
                        result.get("last_method"), result.get("last_success_at"), status, result.get("career_url"),
                        result.get("checked_at"), result.get("outcome"), result.get("outcome"),
                        ats.get("provider"), 1 if ats.get("readable") else 0, ats.get("slug"),
                        employer_id))

    def employers_due_for_discovery(self, *, limit: int = 10) -> list[dict[str, Any]]:
        """Employers with a website whose career discovery has never run or whose retry time has come."""
        now = self.now()
        with self.connect() as db:
            rows = db.execute("""SELECT * FROM employers WHERE website IS NOT NULL AND website != ''
                                 AND (next_discovery_at IS NULL OR next_discovery_at <= ?)
                                 AND NOT (ats_provider IN ('greenhouse','lever','ashby','workable','smartrecruiters','recruitee')
                                          AND ats_slug IS NOT NULL AND career_outcome IS NOT NULL)
                                 ORDER BY (career_outcome IS NULL) DESC, COALESCE(next_discovery_at, '') ASC LIMIT ?""",
                              (now, limit)).fetchall()
        return [self._row(row, "employers") for row in rows]

    # ------------------------------------------------------------- maintenance
    def clear_intel(self) -> dict[str, int]:
        """Remove discovered intelligence while preserving tasks, history and briefings."""
        with self.connect() as db:
            removed = {}
            for table in ("job_listings", "recruitment_notices", "exam_events",
                          "intel_items", "search_sessions", "saved_items", "source_reports", "job_exclusions"):
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
            item[key] = _loads(item.pop(column), [] if key in {"skills", "evidence", "resume_scores", "sources",
                                                               "verify_history", "locations", "discovery_sources",
                                                               "aliases", "interview_dates", "history"} else {})
        return item


_CITY_ALIASES = {"bangalore": "bengaluru", "gurgaon": "gurugram", "bombay": "mumbai", "new delhi": "delhi",
                 "madras": "chennai", "calcutta": "kolkata", "cochin": "kochi"}


def dedup_key(record: dict[str, Any]) -> str | None:
    """employer|normalized title|city — None when employer or title is unknown (no risky merges)."""
    employer = re.sub(r"[^a-z0-9]+", " ", str(record.get("employer") or "").casefold()).strip()
    title = re.sub(r"\b(?:at|@)\s+.*$", "", str(record.get("title") or "").casefold())
    title = re.sub(r"[^a-z0-9+#]+", " ", title).strip()
    if not employer or not title or employer in {"none", "company hidden", "confidential"}:
        return None
    employer = re.sub(r"\b(private limited|pvt ltd|pvt|ltd|limited|inc|llc|technologies|technology|labs?|"
                      r"careers|job board|india)\b", "", employer).strip()
    city = str(record.get("location") or "").casefold().split(",")[0].strip()
    city = re.sub(r"[^a-z ]+", "", city).strip()
    city = _CITY_ALIASES.get(city, city)
    return f"{employer}|{title}|{city}"


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
        entry = {"platform": item.get("platform"), "url": item["url"], "via": item.get("via")}
        for extra in ("method", "retrieved_at", "kind", "policy"):
            if item.get(extra):
                entry[extra] = item[extra]
        output.append(entry)
    return output[:16]


def _iso_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None
