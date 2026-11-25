"""Government / PSU source-first crawling state: per-source scan state, fetched documents, signals, notices.

``gov_sources`` holds the incremental state of every catalogue source (ETag, Last-Modified, content hash,
next due time, failures). ``gov_documents`` is the evidence store: every notification page or PDF that was
read, with its full extracted text. ``opportunity_signals`` holds aggregator entries and hiring news — leads
that point at an opportunity but are never the canonical record.
"""
from __future__ import annotations

import re
from typing import Any

from app.memory.store_parts.common import _json, _loads

NOTICE_COLUMNS = ("organization", "advertisement_number", "post_name", "discipline", "vacancies", "qualifications",
                  "gate_paper", "age_limit", "salary", "location", "opening_date", "closing_date", "exam_date",
                  "selection_process", "document_type", "notification_url", "application_url", "status",
                  "source_id", "official_source", "document_url", "notification_text", "age_min", "age_max",
                  "qualification_level", "min_percentage", "gate_required", "gate_score_min", "dedup_key")
NOTICE_JSON = {"evidence": "evidence_json", "raw": "raw_json", "requirements": "requirements_json",
               "branches": "branches_json", "provenance": "provenance_json"}


def notice_dedup_key(organization: Any, advertisement_number: Any, post_name: Any = None) -> str | None:
    """organization | advertisement number | post — None without an advertisement number (URL is the fallback)."""
    org = re.sub(r"[^a-z0-9]+", " ", str(organization or "").casefold()).strip()
    adv = re.sub(r"[^a-z0-9]+", "", str(advertisement_number or "").casefold())
    if not org or len(adv) < 3:
        return None
    post = re.sub(r"[^a-z0-9]+", " ", str(post_name or "").casefold()).strip()[:60]
    return f"{org}|{adv}|{post}"


class GovMixin:
    # ------------------------------------------------------------ source state
    def gov_source_states(self) -> dict[str, dict[str, Any]]:
        with self.connect() as db:
            return {row["source_id"]: dict(row) for row in db.execute("SELECT * FROM gov_sources")}

    def save_gov_source_state(self, source_id: str, **values: Any) -> None:
        allowed = {"etag", "last_modified", "content_hash", "last_scan_at", "last_success_at", "last_change_at",
                   "next_due_at", "last_state", "last_error", "consecutive_failures", "scans", "links_seen",
                   "documents_new", "notices_found", "last_method"}
        clean = {k: v for k, v in values.items() if k in allowed}
        clean["updated_at"] = self.now()
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO gov_sources(source_id, updated_at) VALUES(?,?)", (source_id, clean["updated_at"]))
            db.execute(f"UPDATE gov_sources SET {', '.join(k + '=?' for k in clean)} WHERE source_id=?",
                       (*clean.values(), source_id))

    # --------------------------------------------------------------- documents
    def gov_document(self, url: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM gov_documents WHERE url=?", (url,)).fetchone()
        return dict(row) if row else None

    def known_gov_urls(self, source_id: str) -> set[str]:
        with self.connect() as db:
            return {row["url"] for row in db.execute("SELECT url FROM gov_documents WHERE source_id=?", (source_id,))}

    def save_gov_document(self, source_id: str, url: str, **values: Any) -> int:
        """Insert or update one fetched/seen document. ``first_seen`` never changes."""
        allowed = {"title", "doc_class", "content_type", "content_hash", "text", "text_chars", "state", "error",
                   "notice_id", "fetched_at"}
        clean = {k: v for k, v in values.items() if k in allowed}
        now = self.now()
        with self.connect() as db:
            db.execute("""INSERT INTO gov_documents(source_id,url,first_seen,last_seen) VALUES(?,?,?,?)
                          ON CONFLICT(url) DO UPDATE SET last_seen=excluded.last_seen""", (source_id, url, now, now))
            if clean:
                db.execute(f"UPDATE gov_documents SET {', '.join(k + '=?' for k in clean)} WHERE url=?",
                           (*clean.values(), url))
            return int(db.execute("SELECT id FROM gov_documents WHERE url=?", (url,)).fetchone()["id"])

    def gov_documents(self, *, source_id: str = "", limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as db:
            if source_id:
                rows = db.execute("""SELECT id,source_id,url,title,doc_class,content_type,text_chars,state,error,notice_id,
                                     first_seen,last_seen,fetched_at FROM gov_documents WHERE source_id=?
                                     ORDER BY last_seen DESC LIMIT ?""", (source_id, limit)).fetchall()
            else:
                rows = db.execute("""SELECT id,source_id,url,title,doc_class,content_type,text_chars,state,error,notice_id,
                                     first_seen,last_seen,fetched_at FROM gov_documents ORDER BY last_seen DESC LIMIT ?""",
                                  (limit,)).fetchall()
        return [dict(row) for row in rows]

    # ----------------------------------------------------------------- notices
    def find_notice(self, *, dedup_key: str | None = None, url: str | None = None) -> dict[str, Any] | None:
        with self.connect() as db:
            row = None
            if dedup_key:
                row = db.execute("SELECT * FROM recruitment_notices WHERE dedup_key=? ORDER BY id LIMIT 1", (dedup_key,)).fetchone()
            if row is None and url:
                row = db.execute("""SELECT * FROM recruitment_notices WHERE canonical_url=? OR document_url=?
                                    OR notification_url=? ORDER BY id LIMIT 1""", (url, url, url)).fetchone()
        return self._row(row, "recruitment_notices") if row else None

    def find_notice_by_advertisement(self, organization: str, advertisement_number: str) -> dict[str, Any] | None:
        """The notice a corrigendum refers to: same organization and advertisement number, any post."""
        key = notice_dedup_key(organization, advertisement_number)
        if not key:
            return None
        prefix = key.rsplit("|", 1)[0] + "|"
        with self.connect() as db:
            row = db.execute("SELECT * FROM recruitment_notices WHERE dedup_key LIKE ? ORDER BY id LIMIT 1",
                             (prefix.replace("%", "") + "%",)).fetchone()
        return self._row(row, "recruitment_notices") if row else None

    def save_gov_notice(self, record: dict[str, Any], *, change: str | None = None) -> tuple[dict[str, Any], bool]:
        """Insert a notice, or merge into the existing one with the same dedup key / URL.

        Returns (notice, created). On a merge only values the new record actually states replace stored ones,
        and a changed date is appended to ``history`` (so a corrigendum updates the notice, never duplicates it)."""
        now = self.now()
        url = str(record.get("canonical_url") or record.get("url") or "").strip()
        if not url:
            raise ValueError("A notice needs a URL")
        key = record.get("dedup_key") or notice_dedup_key(record.get("organization"), record.get("advertisement_number"),
                                                         record.get("post_name"))
        record = {**record, "dedup_key": key}
        existing = self.find_notice(dedup_key=key, url=url)
        with self.connect() as db:
            if existing is None:
                columns = {name: record.get(name) for name in NOTICE_COLUMNS}
                columns["status"] = columns.get("status") or "unverified"
                for field, column in NOTICE_JSON.items():
                    columns[column] = _json(record.get(field) if record.get(field) is not None else
                                            ([] if field in {"evidence", "branches"} else None))
                columns["history_json"] = _json([{"at": now, "change": change or "first seen", "url": record.get("document_url") or url}])
                db.execute(f"""INSERT INTO recruitment_notices(canonical_url, original_url, cse_eligibility, first_seen,
                               last_seen, last_verified, {', '.join(columns)})
                               VALUES(?,?,?,?,?,?{', ?' * len(columns)})""",
                           (url, record.get("original_url") or url, "not_verified", now, now, now, *columns.values()))
                created = True
            else:
                updates: dict[str, Any] = {"last_seen": now, "last_verified": now}
                history = list(existing.get("history") or [])
                for name in NOTICE_COLUMNS:
                    value = record.get(name)
                    if value in (None, "", []):
                        continue
                    if name in {"opening_date", "closing_date", "exam_date"} and existing.get(name) and existing[name] != value:
                        history.append({"at": now, "change": change or "revised", "field": name, "from": existing[name],
                                        "to": value, "url": record.get("document_url") or url})
                    elif name in {"notification_text", "document_url", "notification_url"} and existing.get(name) and change:
                        continue  # a corrigendum never replaces the original notification's text or link
                    updates[name] = value
                for field, column in NOTICE_JSON.items():
                    if record.get(field) and not (change and field in {"requirements", "branches", "raw"}):
                        updates[column] = _json(record[field])
                if change and not any(h.get("url") == (record.get("document_url") or url) and h.get("change") == change
                                      for h in history):
                    history.append({"at": now, "change": change, "url": record.get("document_url") or url})
                updates["history_json"] = _json(history[-30:])
                db.execute(f"UPDATE recruitment_notices SET {', '.join(k + '=?' for k in updates)} WHERE id=?",
                           (*updates.values(), existing["id"]))
                created = False
            row = db.execute("SELECT * FROM recruitment_notices WHERE id=?" if existing else
                             "SELECT * FROM recruitment_notices WHERE canonical_url=?",
                             (existing["id"],) if existing else (url,)).fetchone()
        return self._row(row, "recruitment_notices"), created

    def notice(self, notice_id: int) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM recruitment_notices WHERE id=?", (int(notice_id),)).fetchone()
        return self._row(row, "recruitment_notices") if row else None

    # ----------------------------------------------------------------- signals
    def save_signal(self, signal: dict[str, Any]) -> tuple[int, bool]:
        """Record a lead (aggregator entry or hiring news). Returns (id, created)."""
        now = self.now()
        url = str(signal.get("url") or "").strip()
        title = " ".join(str(signal.get("title") or "").split())[:300]
        if not url or not title:
            raise ValueError("A signal needs a URL and a title")
        with self.connect() as db:
            row = db.execute("SELECT id FROM opportunity_signals WHERE url=?", (url,)).fetchone()
            if row:
                db.execute("UPDATE opportunity_signals SET last_seen=? WHERE id=?", (now, row["id"]))
                return int(row["id"]), False
            cur = db.execute("""INSERT INTO opportunity_signals(kind,source_id,title,url,organization,official_url,notice_id,
                                status,detail,published,first_seen,last_seen) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                             (signal.get("kind") or "news", signal.get("source_id"), title, url, signal.get("organization"),
                              signal.get("official_url"), signal.get("notice_id"), signal.get("status") or "unresolved",
                              (signal.get("detail") or None) and str(signal["detail"])[:600], signal.get("published"), now, now))
            return int(cur.lastrowid), True

    def resolve_signal(self, signal_id: int, *, status: str, official_url: str | None = None,
                       notice_id: int | None = None, organization: str | None = None) -> None:
        with self.connect() as db:
            db.execute("""UPDATE opportunity_signals SET status=?, official_url=COALESCE(?, official_url),
                          notice_id=COALESCE(?, notice_id), organization=COALESCE(?, organization), last_seen=? WHERE id=?""",
                       (status, official_url, notice_id, organization, self.now(), int(signal_id)))

    def signals_list(self, *, status: str = "", kind: str = "", limit: int = 100) -> list[dict[str, Any]]:
        where, args = [], []
        if status:
            where.append("status=?")
            args.append(status)
        if kind:
            where.append("kind=?")
            args.append(kind)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                f"SELECT * FROM opportunity_signals {clause} ORDER BY last_seen DESC LIMIT ?", (*args, max(1, min(limit, 500))))]

    def gov_counts(self) -> dict[str, Any]:
        with self.connect() as db:
            one = lambda sql: db.execute(sql).fetchone()[0]
            by_status = {row[0] or "undecided": row[1] for row in db.execute(
                "SELECT eligibility_status, COUNT(*) FROM recruitment_notices GROUP BY eligibility_status")}
            needs_fact = one("""SELECT COUNT(*) FROM recruitment_notices
                                WHERE missing_facts_json IS NOT NULL AND missing_facts_json NOT IN ('[]','')""")
            # Dashboard totals over the per-status counts; a notice with a missing fact is never "decided".
            by_status["decided"] = sum(by_status.get(name, 0) for name in ("eligible", "likely_eligible", "not_eligible"))
            by_status["needs_fact"] = needs_fact
            return {
                "notices": one("SELECT COUNT(*) FROM recruitment_notices"),
                "notices_official": one("SELECT COUNT(*) FROM recruitment_notices WHERE official_source=1"),
                "notices_from_catalogue": one("SELECT COUNT(*) FROM recruitment_notices WHERE source_id IS NOT NULL"),
                "notices_with_missing_facts": needs_fact,
                "eligibility": by_status,
                "documents": one("SELECT COUNT(*) FROM gov_documents"),
                "documents_with_text": one("SELECT COUNT(*) FROM gov_documents WHERE text_chars > 0"),
                "signals": one("SELECT COUNT(*) FROM opportunity_signals"),
                "signals_resolved": one("SELECT COUNT(*) FROM opportunity_signals WHERE status='resolved'"),
            }
