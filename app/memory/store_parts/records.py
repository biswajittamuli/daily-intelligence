"""Recruitment notices, exam events and intel items (news, papers)."""
from __future__ import annotations

from datetime import date
from typing import Any

from app.memory.store_parts.common import _json


class RecordsMixin:
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
