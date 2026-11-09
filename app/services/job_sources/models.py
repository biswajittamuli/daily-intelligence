"""Shared vocabulary for job acquisition: source states, reports, exclusions and the canonical job.

Every adapter speaks these types, so the orchestrator, the coverage dashboard and the
database never need to know which adapter produced a record.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SourceState:
    """Distinct acquisition outcomes. Never collapse these into a single "failed"."""

    NOT_TARGETED = "not_targeted"
    TARGETED = "targeted"
    SEARCH_OK = "search_successful"
    NO_RESULTS = "no_results"
    FETCH_OK = "fetch_successful"
    EXTRACT_OK = "extraction_successful"
    PARTIAL = "partially_successful"
    ACCESS_DENIED = "access_denied"
    AUTH_REQUIRED = "authentication_required"
    RATE_LIMITED = "rate_limited"
    BOT_CHALLENGE = "bot_challenge"
    NOT_FOUND = "not_found"
    SERVER_ERROR = "server_error"
    TIMEOUT = "timeout"
    UNSUPPORTED = "unsupported_format"
    EXTRACT_FAILED = "extraction_failed"
    UNAVAILABLE = "temporarily_unavailable"
    POLICY_SKIPPED = "skipped_by_access_policy"
    ROBOTS_DISALLOWED = "disallowed_by_robots_txt"

    LABELS = {
        "not_targeted": "Not targeted", "targeted": "Targeted", "search_successful": "Search successful",
        "no_results": "No results", "fetch_successful": "Fetch successful",
        "extraction_successful": "Extraction successful", "partially_successful": "Partially successful",
        "access_denied": "Access denied", "authentication_required": "Authentication required",
        "rate_limited": "Rate limited", "bot_challenge": "CAPTCHA or bot challenge", "not_found": "Not found",
        "server_error": "Server error", "timeout": "Timeout", "unsupported_format": "Unsupported format",
        "extraction_failed": "Extraction failed", "temporarily_unavailable": "Temporarily unavailable",
        "skipped_by_access_policy": "Skipped (access policy)", "disallowed_by_robots_txt": "Disallowed by robots.txt",
    }
    SUCCESS = {"search_successful", "fetch_successful", "extraction_successful", "partially_successful"}
    BLOCKED = {"access_denied", "authentication_required", "rate_limited", "bot_challenge",
               "skipped_by_access_policy", "disallowed_by_robots_txt"}

    @classmethod
    def from_http(cls, status: int | None) -> str:
        if status is None:
            return cls.UNAVAILABLE
        if 200 <= status < 300:
            return cls.FETCH_OK
        if status == 401:
            return cls.AUTH_REQUIRED
        if status in {403, 451}:
            return cls.ACCESS_DENIED
        if status == 429:
            return cls.RATE_LIMITED
        if status in {404, 410}:
            return cls.NOT_FOUND
        if status in {502, 503, 504}:
            return cls.UNAVAILABLE
        if status >= 500:
            return cls.SERVER_ERROR
        return cls.UNSUPPORTED


class Category:
    SEARCH = "search_engine"
    ATS = "ats_board"
    CAREER = "career_page"
    PORTAL = "job_portal"
    BROWSER = "browser_render"
    EXTRACTOR = "third_party_extractor"
    EMPLOYER_DISCOVERY = "employer_discovery"


@dataclass
class SourceReport:
    """One source's outcome inside one acquisition session."""

    name: str
    category: str
    method: str
    domain: str | None = None
    state: str = SourceState.TARGETED
    started_at: str = field(default_factory=utc_now)
    completed_at: str | None = None
    http_status: int | None = None
    queries: int = 0
    search_results: int = 0
    fetched: int = 0
    parsed: int = 0
    listings: int = 0
    unique: int = 0
    duplicates: int = 0
    rejected: int = 0
    stored: int = 0
    verified: int = 0
    retries: int = 0
    failure_reason: str | None = None
    detail: str | None = None
    _t0: float = field(default_factory=time.perf_counter, repr=False)
    duration_ms: int | None = None

    @property
    def key(self) -> str:
        return f"{self.category}|{self.name}|{self.method}"

    def finish(self, state: str | None = None, *, failure: str | None = None, http_status: int | None = None) -> "SourceReport":
        if state:
            self.state = state
        if failure:
            self.failure_reason = failure[:300]
        if http_status is not None:
            self.http_status = http_status
        self.completed_at = utc_now()
        self.duration_ms = int((time.perf_counter() - self._t0) * 1000)
        return self

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("_t0", None)
        data["key"] = self.key
        data["state_label"] = SourceState.LABELS.get(self.state, self.state)
        return data


class Exclusion:
    """Reasons a discovered result did not become a stored listing (shown to the user)."""

    ARTICLE = "Article or hiring news, not a vacancy"
    SEARCH_PAGE = "Search or listing-index page, not a job detail"
    DUPLICATE = "Duplicate of another listing"
    EXPIRED = "Expired or closed"
    IRRELEVANT_ROLE = "Role does not match your target roles"
    NON_TECH = "Not a technical role for your profile"
    GEOGRAPHY = "Outside your selected geography"
    REMOTE_RESTRICTED = "Remote role restricted to another country or region"
    INSUFFICIENT = "Insufficient job evidence"
    BROKEN_URL = "Broken or unsafe URL"
    EXTRACTION_FAILED = "Extraction failure"
    POOL_LIMIT = "Below the shortlist cut-off (pool size)"
    INELIGIBLE = "Not eligible (kept only if a strong stretch match)"
    NOT_VACANCY = "Not a single vacancy (talent network, registration, careers home, news)"
    GEO_UNKNOWN = "Geography unknown"


# Lifecycle states for a vacancy (Part 10). ``app.services.verification.lifecycle`` maps stored rows onto these.
LIFECYCLE_STATES = {
    "discovered": "Discovered", "extracted": "Extracted", "pending_verification": "Pending verification",
    "open_verified": "Open · employer verified", "open_page_checked": "Open · third-party source only",
    "open_not_recent": "Open · not recently verified", "unverified": "Unverified", "closed": "Closed",
    "expired": "Expired", "reposted": "Reposted", "removed": "Removed", "inaccessible": "Inaccessible",
    "unknown": "Unknown", "recheck_pending": "Possibly open · last check failed",
}


# Canonical job schema (Part 9). Every acquisition path produces dicts with these keys; missing values stay None.
CANONICAL_JOB_FIELDS = (
    "employer", "title", "original_url", "canonical_url", "application_url", "source_platform", "location",
    "remote", "employment_type", "experience", "education", "mandatory_skills", "preferred_skills", "skills",
    "salary", "salary_currency", "posted_date", "updated_date", "deadline", "status", "description",
    "evidence", "retrieved_at", "last_verified", "extraction_method", "confidence", "employer_id", "ats_ref",
    "requisition_id",
)


def canonical_job(**values: Any) -> dict[str, Any]:
    """A job dict with every canonical field present (None when not evidenced). Extra keys are kept."""
    job = {name: None for name in CANONICAL_JOB_FIELDS}
    job.update({key: value for key, value in values.items() if value not in ("", [])} )
    job.setdefault("retrieved_at", utc_now())
    if not job.get("retrieved_at"):
        job["retrieved_at"] = utc_now()
    return job
