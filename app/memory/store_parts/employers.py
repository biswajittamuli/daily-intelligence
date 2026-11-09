"""Employers, hiring signals, following and career-page discovery state."""
from __future__ import annotations

from typing import Any

from app.memory.store_parts.common import _json, _loads


class EmployersMixin:
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
