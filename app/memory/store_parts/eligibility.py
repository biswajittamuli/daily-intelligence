"""Candidate eligibility profile (single row) and stored eligibility verdicts for notices and exams."""
from __future__ import annotations

from typing import Any

from app.memory.store_parts.common import _json, _loads


class EligibilityMixin:
    def eligibility_profile(self) -> dict[str, Any] | None:
        """The declared profile, or None when the user has never saved one (nothing is ever inferred)."""
        with self.connect() as db:
            row = db.execute("SELECT profile_json, updated_at FROM candidate_eligibility WHERE id=1").fetchone()
        if not row:
            return None
        profile = _loads(row["profile_json"], {})
        profile["updated_at"] = row["updated_at"]
        return profile

    def save_eligibility_profile(self, profile: dict[str, Any]) -> dict[str, Any]:
        now = self.now()
        clean = {k: v for k, v in profile.items() if k != "updated_at"}
        with self.connect() as db:
            db.execute("""INSERT INTO candidate_eligibility(id, profile_json, updated_at) VALUES(1,?,?)
                          ON CONFLICT(id) DO UPDATE SET profile_json=excluded.profile_json,
                          updated_at=excluded.updated_at""", (_json(clean), now))
        return {**clean, "updated_at": now}

    def set_eligibility(self, table: str, item_id: int, result: dict[str, Any]) -> None:
        if table not in {"recruitment_notices", "exam_events"}:
            raise ValueError("Unsupported table")
        with self.connect() as db:
            db.execute(f"""UPDATE {table} SET eligibility_status=?, eligibility_json=?, missing_facts_json=?,
                           eligibility_as_of=? WHERE id=?""",
                       (result.get("status"), _json(result), _json(result.get("missing_facts") or []),
                        result.get("as_of"), int(item_id)))
