"""Job listings: upsert with cross-source dedup, verification, queries, match updates."""
from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any

from app.memory.store_parts.common import _iso_date, _json, _loads, _merge_sources, dedup_key


class JobsMixin:
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
                row = db.execute("SELECT id, status, first_seen, sources_json, verify_history_json, repost_of, posted_date, "
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
                previous_status = row["status"] if row is not None else None
                row = db.execute("SELECT * FROM job_listings WHERE canonical_url=?", (url,)).fetchone()
                db.execute("UPDATE job_listings SET last_fetched_at=? WHERE id=?", (now, row["id"]))
                if previous_status != row["status"]:
                    db.execute("INSERT INTO job_status_history(job_id,at,from_status,to_status,outcome,evidence) "
                               "VALUES(?,?,?,?,?,?)", (row["id"], now, previous_status, row["status"],
                                                        "discovered" if previous_status is None else "refetched",
                                                        str(record.get("status_evidence") or "")[:300]))
                saved.append(self._row(row, "job_listings"))
        return saved

    def update_validations(self, updates: list[dict[str, Any]]) -> None:
        """Persist validation-gate results (document type, geography, vacancy status, stages) per listing."""
        with self.connect() as db:
            for update in updates:
                db.execute("UPDATE job_listings SET document_type=?, geo_class=?, vacancy_status=?, "
                           "verification_level=?, validation_json=? WHERE id=?",
                           (update.get("document_type"), update.get("geo_class"), update.get("vacancy_status"),
                            update.get("verification_level"), _json(update.get("validation")), update["id"]))

    def status_history(self, job_id: int) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT at, from_status, to_status, outcome, evidence FROM job_status_history WHERE job_id=? ORDER BY id",
                (job_id,))]

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
                            raw_text: str | None = None, posted_source: str | None = None,
                            deadline: str | None = None) -> dict[str, Any]:
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
            from app.services.freshness import date_confidence, stronger_date
            source = posted_source or ("employer ATS" if evidence.startswith("Listed on") else "JobPosting datePosted")
            confidence = date_confidence(source, posted_date)
            if posted_date and stronger_date(posted_date, confidence, row["posted_date"],
                                             row["posting_date_confidence"] or "low"):
                fields["posted_date"] = posted_date
                fields["posted_date_source"] = source
                fields["posting_date_confidence"] = confidence
            if deadline and not row["deadline"]:
                fields["deadline"] = deadline
            fields["last_fetched_at"] = now
            if status and status != row["status"]:
                db.execute("INSERT INTO job_status_history(job_id,at,from_status,to_status,outcome,evidence) "
                           "VALUES(?,?,?,?,?,?)", (job_id, now, row["status"], status, outcome, evidence[:300]))
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
