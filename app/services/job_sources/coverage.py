"""Per-session coverage collector: source reports, the acquisition funnel and inspectable exclusions."""
from __future__ import annotations

from collections import Counter
from typing import Any
from urllib.parse import urlsplit

from app.services.job_sources.models import SourceReport, SourceState

FUNNEL_STAGES = [
    ("search_results", "Search results"),
    ("ats_openings", "Employer board openings"),
    ("career_page_listings", "Career-page listings"),
    ("harvested", "Listings expanded from index pages"),
    ("unique_urls", "Unique URLs"),
    ("pages_fetched", "Pages fetched"),
    ("pages_parsed", "Pages parsed"),
    ("listings_extracted", "Job listings extracted"),
    ("valid_jobs", "Valid jobs (vacancies)"),
    ("relevant_jobs", "Relevant jobs"),
    ("stored_jobs", "Stored jobs"),
]


class Coverage:
    def __init__(self) -> None:
        self.reports: dict[str, SourceReport] = {}
        self.exclusions: list[dict[str, Any]] = []
        self.exclusion_counts: Counter[str] = Counter()
        self.funnel: dict[str, int] = {key: 0 for key, _ in FUNNEL_STAGES}
        self.max_exclusion_rows = 12000

    def report(self, name: str, category: str, method: str, *, domain: str | None = None) -> SourceReport:
        candidate = SourceReport(name=name, category=category, method=method, domain=domain)
        existing = self.reports.get(candidate.key)
        if existing is None:
            self.reports[candidate.key] = candidate
            return candidate
        return existing

    def exclude(self, item: dict[str, Any], reason: str, stage: str) -> None:
        self.exclusion_counts[reason] += 1
        if len(self.exclusions) >= self.max_exclusion_rows:
            return
        url = str(item.get("url") or item.get("original_url") or "")
        self.exclusions.append({"url": url[:1000], "title": str(item.get("title") or "")[:240],
                                "employer": str(item.get("employer") or "")[:120] or None,
                                "source": str(item.get("_via") or item.get("source_platform") or
                                              (urlsplit(url).hostname or ""))[:120],
                                "reason": reason, "stage": stage,
                                "detail": str(item.get("_exclusion_detail") or "")[:300] or None})

    def add(self, stage: str, count: int = 1) -> None:
        self.funnel[stage] = self.funnel.get(stage, 0) + count

    def set(self, stage: str, count: int) -> None:
        self.funnel[stage] = count

    # ------------------------------------------------------------ output
    def source_rows(self) -> list[dict[str, Any]]:
        rows = [report.to_dict() for report in self.reports.values()]
        order = {state: index for index, state in enumerate([
            SourceState.EXTRACT_OK, SourceState.PARTIAL, SourceState.FETCH_OK, SourceState.SEARCH_OK,
            SourceState.NO_RESULTS, SourceState.POLICY_SKIPPED, SourceState.ROBOTS_DISALLOWED, SourceState.RATE_LIMITED,
            SourceState.BOT_CHALLENGE, SourceState.ACCESS_DENIED, SourceState.AUTH_REQUIRED, SourceState.NOT_FOUND,
            SourceState.TIMEOUT, SourceState.SERVER_ERROR, SourceState.UNAVAILABLE, SourceState.EXTRACT_FAILED,
            SourceState.UNSUPPORTED, SourceState.TARGETED, SourceState.NOT_TARGETED])}
        rows.sort(key=lambda r: (-(r["stored"] or 0), -(r["listings"] or 0), order.get(r["state"], 99), r["name"]))
        return rows

    def funnel_rows(self) -> list[dict[str, Any]]:
        return [{"stage": key, "label": label, "count": self.funnel.get(key, 0)} for key, label in FUNNEL_STAGES]

    def summary(self) -> dict[str, Any]:
        rows = self.source_rows()
        by_state = Counter(row["state"] for row in rows)
        successful = [row for row in rows if row["state"] in SourceState.SUCCESS and
                      (row["listings"] or row["search_results"] or row["parsed"])]
        return {
            "sources": rows,
            "funnel_stages": self.funnel_rows(),
            "exclusion_reasons": dict(self.exclusion_counts.most_common()),
            "sources_targeted": len(rows),
            "sources_successful": len(successful),
            "sources_by_state": dict(by_state),
            "sources_inaccessible": [{"name": r["name"], "method": r["method"], "state": r["state_label"],
                                      "reason": r["failure_reason"]} for r in rows if r["state"] in SourceState.BLOCKED
                                     or r["state"] in {SourceState.TIMEOUT, SourceState.SERVER_ERROR,
                                                       SourceState.UNAVAILABLE, SourceState.NOT_FOUND}],
        }
