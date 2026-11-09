"""Applications, per-item state (saved/applied/hidden) and listing reports."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.memory.store_parts.common import _iso_date, _json, _loads


class TrackingMixin:
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
