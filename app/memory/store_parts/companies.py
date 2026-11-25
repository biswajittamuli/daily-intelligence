"""Company registry (v5), query-rotation coverage and "missed opportunity" reports."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit

SEGMENTS = ("gcc", "product", "unicorn", "startup", "services", "psu_enterprise")


def _when(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class CompaniesMixin:
    # ---------------------------------------------------------------- registry
    def seed_companies(self, companies: list[dict[str, Any]], *, source: str = "built-in verified seed") -> int:
        """Insert seed companies; existing rows keep their scan state and any user changes (enabled/followed)."""
        now = self.now()
        added = 0
        with self.connect() as db:
            for item in companies:
                domain = str(item.get("domain") or "").strip().casefold()
                segment = item.get("segment") if item.get("segment") in SEGMENTS else "product"
                if not domain or not item.get("name"):
                    continue
                row = db.execute("SELECT id FROM company_registry WHERE domain=?", (domain,)).fetchone()
                if row:
                    db.execute("""UPDATE company_registry SET name=?, segment=?, ats=COALESCE(?, ats),
                                  tenant=COALESCE(?, tenant), careers_url=COALESCE(?, careers_url), priority=?,
                                  verified_at=COALESCE(?, verified_at), updated_at=? WHERE id=?""",
                               (item["name"], segment, item.get("ats"), item.get("tenant"), item.get("careers_url"),
                                int(item.get("priority") or 50), item.get("verified_at"), now, row["id"]))
                    continue
                db.execute("""INSERT INTO company_registry(name,domain,segment,ats,tenant,careers_url,priority,source,
                              verified_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                           (item["name"], domain, segment, item.get("ats"), item.get("tenant"), item.get("careers_url"),
                            int(item.get("priority") or 50), item.get("source") or source, item.get("verified_at"), now, now))
                added += 1
        return added

    def companies(self, *, segment: str = "", limit: int = 2000) -> list[dict[str, Any]]:
        with self.connect() as db:
            if segment:
                rows = db.execute("SELECT * FROM company_registry WHERE segment=? ORDER BY priority DESC, name LIMIT ?",
                                  (segment, limit)).fetchall()
            else:
                rows = db.execute("SELECT * FROM company_registry ORDER BY priority DESC, name LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def company(self, company_id: int) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM company_registry WHERE id=?", (int(company_id),)).fetchone()
        return dict(row) if row else None

    def companies_due(self, *, limit: int = 10, now: datetime | None = None) -> list[dict[str, Any]]:
        """Round-robin: enabled companies whose ``next_due_at`` has passed (never-scanned first), followed
        companies and higher priority ahead, then the least recently scanned."""
        now = now or datetime.now(timezone.utc)
        with self.connect() as db:
            rows = [dict(row) for row in db.execute("SELECT * FROM company_registry WHERE enabled=1")]
        due = [row for row in rows if not row.get("next_due_at") or (_when(row["next_due_at"]) or now) <= now]
        due.sort(key=lambda r: (-int(r.get("followed") or 0), r.get("last_scan_at") is not None, -int(r.get("priority") or 0),
                                str(r.get("last_scan_at") or ""), r["id"]))
        return due[:max(1, limit)]

    def record_company_scan(self, company_id: int, *, ok: bool, state: str, jobs: int = 0, india_jobs: int = 0,
                            error: str | None = None, cadence_hours: float = 24.0, now: datetime | None = None) -> None:
        """Fold one scan into the registry row: success resets failures; failures back off exponentially."""
        now = now or datetime.now(timezone.utc)
        with self.connect() as db:
            row = db.execute("SELECT consecutive_failures, followed FROM company_registry WHERE id=?", (int(company_id),)).fetchone()
            if not row:
                return
            failures = 0 if ok else int(row["consecutive_failures"] or 0) + 1
            hours = (cadence_hours / 2 if row["followed"] else cadence_hours) if ok else min(cadence_hours * 2 ** failures, 24 * 14)
            values = {"last_scan_at": now.isoformat(), "state": state, "consecutive_failures": failures,
                      "next_due_at": (now + timedelta(hours=hours)).isoformat(), "last_error": None if ok else (error or state)[:300],
                      "updated_at": now.isoformat()}
            if ok:
                values.update(last_success_at=now.isoformat(), jobs_count=int(jobs), india_jobs=int(india_jobs))
            db.execute(f"UPDATE company_registry SET {', '.join(k + '=?' for k in values)} WHERE id=?",
                       (*values.values(), int(company_id)))

    def update_company(self, company_id: int, **values: Any) -> None:
        allowed = {"enabled", "followed", "priority", "ats", "tenant", "careers_url", "next_due_at", "segment"}
        clean = {k: v for k, v in values.items() if k in allowed}
        if not clean:
            return
        clean["updated_at"] = self.now()
        with self.connect() as db:
            db.execute(f"UPDATE company_registry SET {', '.join(k + '=?' for k in clean)} WHERE id=?",
                       (*clean.values(), int(company_id)))

    def company_coverage(self, *, now: datetime | None = None) -> dict[str, Any]:
        now = now or datetime.now(timezone.utc)
        segments: dict[str, dict[str, int]] = {}
        totals = {"companies": 0, "enabled": 0, "scanned": 0, "successful": 0, "failing": 0, "due": 0, "jobs": 0, "india_jobs": 0}
        ats: dict[str, int] = {}
        for row in self.companies(limit=5000):
            entry = segments.setdefault(row["segment"], {"companies": 0, "scanned": 0, "successful": 0, "failing": 0,
                                                         "due": 0, "jobs": 0, "india_jobs": 0})
            due = bool(row["enabled"]) and (not row.get("next_due_at") or (_when(row["next_due_at"]) or now) <= now)
            for bucket in (entry, totals):
                bucket["companies"] += 1
                bucket["scanned"] += int(bool(row.get("last_scan_at")))
                bucket["successful"] += int(bool(row.get("last_success_at")))
                bucket["failing"] += int(int(row.get("consecutive_failures") or 0) >= 3)
                bucket["due"] += int(due)
                bucket["jobs"] += int(row.get("jobs_count") or 0)
                bucket["india_jobs"] += int(row.get("india_jobs") or 0)
            totals["enabled"] += int(bool(row["enabled"]))
            ats[row.get("ats") or "career page"] = ats.get(row.get("ats") or "career page", 0) + 1
        return {"totals": totals, "segments": segments, "ats": dict(sorted(ats.items(), key=lambda kv: -kv[1]))}

    # ---------------------------------------------------------- query coverage
    @staticmethod
    def query_key(family: str, query: str) -> str:
        return hashlib.sha1(f"{family}|{' '.join(query.casefold().split())}".encode()).hexdigest()[:20]

    def query_coverage(self) -> dict[str, dict[str, Any]]:
        with self.connect() as db:
            return {row["query_key"]: dict(row) for row in db.execute("SELECT * FROM query_coverage")}

    def record_queries(self, queries: list[dict[str, Any]]) -> None:
        """Mark planned queries as run ({"family", "query", "results"?})."""
        now = self.now()
        with self.connect() as db:
            for item in queries:
                key = self.query_key(item["family"], item["query"])
                db.execute("""INSERT INTO query_coverage(query_key,family,query,runs,last_run_at,last_results,first_planned_at)
                              VALUES(?,?,?,1,?,?,?) ON CONFLICT(query_key) DO UPDATE SET runs=query_coverage.runs+1,
                              last_run_at=excluded.last_run_at, last_results=COALESCE(excluded.last_results, query_coverage.last_results)""",
                           (key, item["family"], item["query"][:300], now, item.get("results"), now))
            db.execute("""DELETE FROM query_coverage WHERE query_key NOT IN
                          (SELECT query_key FROM query_coverage ORDER BY last_run_at DESC LIMIT 3000)""")

    # ----------------------------------------------------------- missed reports
    MISSED_KINDS = ("missed", "eligible_claim")

    def add_missed_report(self, *, url: str | None, title: str | None = None, kind: str = "missed", reason: str | None = None,
                          note: str | None = None, source: str | None = None, item_kind: str | None = None,
                          item_id: int | None = None) -> dict[str, Any]:
        if kind not in self.MISSED_KINDS:
            raise ValueError("Unknown report kind")
        clean = lambda value, limit: (" ".join(str(value).split())[:limit] or None) if value else None
        url = clean(url, 1000)
        host = None
        if url:
            parts = urlsplit(url)
            if parts.scheme not in {"http", "https"} or not parts.hostname:
                raise ValueError("The link must be an http(s) URL")
            host = parts.hostname.casefold().removeprefix("www.")
        if not url and not clean(title, 300):
            raise ValueError("Give a link or a title for the missed opportunity")
        now = self.now()
        with self.connect() as db:
            cur = db.execute("""INSERT INTO missed_reports(url,title,kind,reason,note,source,host,item_kind,item_id,status,
                                created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,'open',?,?)""",
                             (url, clean(title, 300), kind, clean(reason, 200), clean(note, 1000), clean(source, 120), host,
                              item_kind, item_id, now, now))
            row = db.execute("SELECT * FROM missed_reports WHERE id=?", (cur.lastrowid,)).fetchone()
        return dict(row)

    def missed_reports(self, *, status: str = "", limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as db:
            if status:
                rows = db.execute("SELECT * FROM missed_reports WHERE status=? ORDER BY id DESC LIMIT ?", (status, limit)).fetchall()
            else:
                rows = db.execute("SELECT * FROM missed_reports ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def resolve_missed_report(self, report_id: int, *, status: str, resolution: str | None = None) -> None:
        if status not in {"open", "source_added", "known_source", "fixed", "dismissed"}:
            raise ValueError("Unknown status")
        with self.connect() as db:
            db.execute("UPDATE missed_reports SET status=?, resolution=?, updated_at=? WHERE id=?",
                       (status, (resolution or None) and str(resolution)[:500], self.now(), int(report_id)))
