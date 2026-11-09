"""Resumes and the candidate profile."""
from __future__ import annotations

import sqlite3
from typing import Any

from app.memory.store_parts.common import _json, _loads, _resume_label


class ProfileMixin:
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
