"""Local SQLite store: tasks, history, briefings, preferences and intelligence records.

Schema changes are additive (CREATE TABLE IF NOT EXISTS) so existing tasks, history,
briefings and source snapshots are preserved across upgrades.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.memory.store_parts.common import JSON_COLUMNS, _json, _loads, _resume_label  # noqa: F401 (re-exported)
from app.memory.store_parts.employers import EmployersMixin
from app.memory.store_parts.jobs import JobsMixin
from app.memory.store_parts.personal import PersonalMixin
from app.memory.store_parts.profile import ProfileMixin
from app.memory.store_parts.records import RecordsMixin
from app.memory.store_parts.sources import SourcesMixin
from app.memory.store_parts.tracking import TrackingMixin


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
CREATE TABLE IF NOT EXISTS job_status_history (
    id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL, at TEXT NOT NULL,
    from_status TEXT, to_status TEXT, outcome TEXT, evidence TEXT
);
CREATE INDEX IF NOT EXISTS idx_job_status_history_job ON job_status_history(job_id);
"""









SCHEMA_VERSION = 11  # bump whenever _migrate adds tables/columns


class Store(PersonalMixin, ProfileMixin, JobsMixin, RecordsMixin, EmployersMixin, TrackingMixin, SourcesMixin):
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
            self._prune_backups(backups)
        finally:
            source.close()

    BACKUPS_KEPT = 5

    @classmethod
    def _prune_backups(cls, backups: Path) -> None:
        """Keep the newest migration backups; called only after a new one was written successfully."""
        files = sorted(backups.glob("daily-intelligence-*-schema*.sqlite3"), key=lambda p: p.name, reverse=True)
        for old in files[cls.BACKUPS_KEPT:]:
            old.unlink(missing_ok=True)

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
                             "posted_date_source": "TEXT", "posting_date_confidence": "TEXT",
                             # v11: validation gate results (document type, geography, status, verification level)
                             "document_type": "TEXT", "geo_class": "TEXT", "vacancy_status": "TEXT",
                             "verification_level": "TEXT", "validation_json": "TEXT", "last_fetched_at": "TEXT"},
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
