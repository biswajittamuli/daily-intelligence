"""Readers for the applicant-tracking systems behind company career sites (v5).

One interface for every ATS:

    reader.enumerate(http, board)   -> ReadResult(jobs, state, error, pages, total)
    reader.detail(http, board, job) -> the job with its description filled in (where the ATS exposes one)
    reader.posting_date / location / apply_url / status   -> normalisers, pure and fixture-tested

Access rules (same as the rest of the acquisition layer)
- Only public, unauthenticated job-board interfaces: the JSON/XML/RSS/HTML a candidate's browser receives
  without signing in. No login, no CAPTCHA handling, no private endpoints.
- Every request goes through ``SafeFetcher``: robots.txt, per-host pacing, timeouts, private-network blocking.
  A tenant whose robots.txt disallows the path is reported as such and not read.
- The tenant is always detected from the company's own careers page (``detect_board``); it is never guessed.
- When an ATS has no public interface (Darwinbox, Keka, Zoho Recruit, Freshteam, TurboHire, Taleo) the reader
  reports ``career_page`` and the caller falls back to the existing career-page reader.

Verified live on 2026-11-16: Workday CXS, Oracle Recruiting Cloud REST, Eightfold, Teamtailor RSS, Personio XML,
Kula public pages. SuccessFactors (Career Site Builder), iCIMS and Phenom readers parse the public HTML those
systems serve; whether a given tenant may be read is decided by that tenant's robots.txt.
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import quote, urljoin, urlsplit

from app.services.freshness import parse_date, parse_relative_date
from app.services.job_sources.models import SourceState
from app.services.job_sources.structured import _doc, clean_text

PAGE_LIMIT = 5            # pages per board per scan
MAX_JOBS = 200            # jobs kept per board per scan
INDIA = re.compile(r"\b(india|bengaluru|bangalore|hyderabad|pune|mumbai|delhi|gurugram|gurgaon|noida|chennai|kolkata|"
                   r"ahmedabad|kochi|thiruvananthapuram|trivandrum|jaipur|indore|coimbatore|chandigarh|guwahati|"
                   r"bhubaneswar|nagpur|vadodara|mysuru|mysore|visakhapatnam|lucknow)\b", re.I)


@dataclass(frozen=True)
class Board:
    ats: str
    tenant: str
    name: str = ""
    careers_url: str = ""

    @property
    def platform(self) -> str:
        return f"{self.ats}:{self.tenant}"


@dataclass
class ReadResult:
    jobs: list[dict[str, Any]] = field(default_factory=list)
    state: str = SourceState.NO_RESULTS
    error: str | None = None
    pages: int = 0
    total: int | None = None

    @property
    def ok(self) -> bool:
        return self.state in SourceState.SUCCESS or self.state == SourceState.NO_RESULTS


def is_india(location: Any, country: Any = None) -> bool:
    return str(country or "").strip().upper() in {"IN", "IND", "INDIA"} or bool(INDIA.search(str(location or "")))


def _iso(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) or str(value).isdigit():
        number = int(value)
        try:
            return datetime.fromtimestamp(number / 1000 if number > 10**11 else number, timezone.utc).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    parsed = parse_date(text) or parse_date(text[:10])
    if parsed is None:
        try:
            from email.utils import parsedate_to_datetime
            parsed = parsedate_to_datetime(text).date()
        except (TypeError, ValueError, IndexError):
            parsed = None
    return parsed.isoformat() if parsed else None


def _job(board: Board, *, title: Any, url: Any, location: Any = None, posted: Any = None, description: Any = "",
         requisition: Any = None, employment_type: Any = None, remote: Any = None, country: Any = None,
         deadline: Any = None, method: str = "") -> dict[str, Any] | None:
    title, url = clean_text(title, 200), str(url or "").strip()
    if not title or not url.startswith("https://"):
        return None
    return {"title": title, "employer": board.name, "location": clean_text(location, 160), "url": url,
            "posted_date": posted, "description": clean_text(description, 12000), "employment_type": employment_type,
            "remote": remote, "requisition_id": (str(requisition)[:60] if requisition else None), "country": country,
            "valid_through": deadline, "source_platform": board.platform, "ats": board.ats,
            "extraction_method": method or f"{board.ats} public job board", "application_url": url}


def _failure(result: Any) -> ReadResult:
    return ReadResult(state=result.state, error=result.error or SourceState.LABELS.get(result.state, result.state), pages=1)


def _json(result: Any) -> Any:
    try:
        return json.loads(result.text)
    except (TypeError, ValueError):
        return None


class Reader:
    key = ""
    name = ""
    interface = ""
    public = True  # False: no public interface; the career-page reader is used instead

    async def enumerate(self, http: Any, board: Board, *, india_only: bool = True) -> ReadResult:
        raise NotImplementedError

    async def detail(self, http: Any, board: Board, job: dict[str, Any]) -> dict[str, Any]:
        return job

    @staticmethod
    def status(item: dict[str, Any]) -> str:
        """A posting returned by a live board is open unless the board says otherwise."""
        return "open"


# ------------------------------------------------------------------------------------------ Workday
class WorkdayReader(Reader):
    """Workday: the public CXS endpoint the career site itself calls
    (``POST https://{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs``)."""
    key, name, interface = "workday", "Workday", "public CXS JSON (POST /wday/cxs/{tenant}/{site}/jobs)"

    @staticmethod
    def parts(board: Board) -> tuple[str, str, str]:
        host, _, site = board.tenant.partition("/")
        return host, host.split(".")[0], site

    @classmethod
    def endpoint(cls, board: Board) -> str:
        host, tenant, site = cls.parts(board)
        return f"https://{host}/wday/cxs/{tenant}/{site}/jobs"

    @staticmethod
    def location(item: dict[str, Any]) -> str:
        text = str(item.get("locationsText") or "")
        if text and not re.fullmatch(r"\d+\s+Locations?", text, re.I):
            return text
        path = re.match(r"/job/([^/]+)/", str(item.get("externalPath") or ""))
        place = path.group(1).replace("---", " - ").replace("-", ", ", 1).replace("-", " ") if path else ""
        return f"{place} (+ other locations)" if place and text else (place or text)

    @staticmethod
    def posting_date(item: dict[str, Any], today: date | None = None) -> str | None:
        text = str(item.get("postedOn") or "")
        found = parse_relative_date(text.replace("Posted", "").replace("+", ""), today)
        return found.isoformat() if found else None

    @classmethod
    def apply_url(cls, item: dict[str, Any], board: Board) -> str:
        host, _, site = cls.parts(board)
        return f"https://{host}/{site}{item.get('externalPath') or ''}"

    @classmethod
    def parse(cls, payload: Any, board: Board, today: date | None = None) -> list[dict[str, Any]]:
        jobs = []
        for item in (payload or {}).get("jobPostings") or []:
            if not item.get("externalPath"):
                continue
            job = _job(board, title=item.get("title"), url=cls.apply_url(item, board), location=cls.location(item),
                       posted=cls.posting_date(item, today), requisition=(item.get("bulletFields") or [None])[0],
                       method="Workday public CXS API")
            if job:
                job["date_source"] = "employer job board (relative date)" if job["posted_date"] else None
                jobs.append(job)
        return jobs

    @staticmethod
    def india_facet(payload: Any) -> dict[str, list[str]] | None:
        """The board's own facet for India, read from its response (facet ids differ per tenant)."""
        def walk(facets: Any) -> dict[str, list[str]] | None:
            for facet in facets or []:
                parameter = facet.get("facetParameter")
                for value in facet.get("values") or []:
                    if parameter and str(value.get("descriptor") or "").strip().casefold() == "india" and value.get("id"):
                        return {parameter: [value["id"]]}
                    nested = walk([value]) if value.get("values") else None
                    if nested:
                        return nested
            return None
        return walk((payload or {}).get("facets"))

    async def enumerate(self, http: Any, board: Board, *, india_only: bool = True) -> ReadResult:
        url = self.endpoint(board)
        body: dict[str, Any] = {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}
        first = await http.post_json(url, body)
        payload = _json(first) if first.ok else None
        if payload is None:
            return _failure(first) if not first.ok else ReadResult(state=SourceState.EXTRACT_FAILED, error="unexpected response", pages=1)
        pages = 1
        if india_only:
            facet = self.india_facet(payload)
            body = {**body, "appliedFacets": facet} if facet else {**body, "searchText": "India"}
            filtered = await http.post_json(url, body)
            pages += 1
            payload = _json(filtered) if filtered.ok else None
            if payload is None:
                return _failure(filtered)
        jobs = self.parse(payload, board)
        total = int(payload.get("total") or 0)
        offset = 20
        while offset < total and pages < PAGE_LIMIT + 1 and len(jobs) < MAX_JOBS:
            page = await http.post_json(url, {**body, "offset": offset})
            pages += 1
            more = _json(page) if page.ok else None
            if more is None:
                return ReadResult(jobs, SourceState.PARTIAL, f"stopped at offset {offset}: {page.error}", pages, total)
            jobs += self.parse(more, board)
            offset += 20
        return ReadResult(jobs[:MAX_JOBS], SourceState.EXTRACT_OK if jobs else SourceState.NO_RESULTS, None, pages, total)

    async def detail(self, http: Any, board: Board, job: dict[str, Any]) -> dict[str, Any]:
        host, tenant, site = self.parts(board)
        path = urlsplit(job["url"]).path
        path = path[len(f"/{site}"):] if path.startswith(f"/{site}") else path
        result = await http.get(f"https://{host}/wday/cxs/{tenant}/{site}{path}", accept_json=True)
        info = ((_json(result) or {}).get("jobPostingInfo") or {}) if result.ok else {}
        if info:
            job["description"] = clean_text(info.get("jobDescription"), 12000) or job.get("description")
            job["posted_date"] = _iso(info.get("startDate")) or job.get("posted_date")
            if info.get("startDate"):
                job["date_source"] = "employer job board"
            job["valid_through"] = _iso(info.get("endDate")) or job.get("valid_through")
            job["location"] = clean_text(info.get("location"), 160) or job.get("location")
            job["employment_type"] = info.get("timeType") or job.get("employment_type")
        return job


# ------------------------------------------------------------------------------------------ Oracle
class OracleReader(Reader):
    """Oracle Recruiting Cloud: ``recruitingCEJobRequisitions`` REST resource behind the public candidate site."""
    key, name, interface = "oracle", "Oracle Recruiting Cloud", "public REST (hcmRestApi recruitingCEJobRequisitions)"

    @staticmethod
    def endpoint(board: Board, offset: int = 0, keyword: str = "") -> str:
        host, _, site = board.tenant.partition("/")
        finder = f"findReqs;siteNumber={quote(site)},limit=25,offset={offset},sortBy=POSTING_DATES_DESC"
        if keyword:
            finder += f",keyword={quote(keyword)}"
        return (f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true"
                f"&expand=requisitionList.secondaryLocations&finder={finder}")

    @staticmethod
    def location(item: dict[str, Any]) -> str:
        places = [item.get("PrimaryLocation")] + [s.get("Name") for s in item.get("secondaryLocations") or []]
        return "; ".join(dict.fromkeys(str(p) for p in places if p))

    @staticmethod
    def posting_date(item: dict[str, Any]) -> str | None:
        return _iso(item.get("PostedDate"))

    @staticmethod
    def apply_url(item: dict[str, Any], board: Board) -> str:
        host, _, site = board.tenant.partition("/")
        return f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{item.get('Id')}"

    @classmethod
    def parse(cls, payload: Any, board: Board) -> tuple[list[dict[str, Any]], int]:
        jobs, total = [], 0
        for search in (payload or {}).get("items") or []:
            total = int(search.get("TotalJobsCount") or total or 0)
            for item in search.get("requisitionList") or []:
                job = _job(board, title=item.get("Title"), url=cls.apply_url(item, board), location=cls.location(item),
                           posted=cls.posting_date(item), description=item.get("ShortDescriptionStr"),
                           requisition=item.get("Id"), country=item.get("PrimaryLocationCountry"),
                           deadline=_iso(item.get("PostingEndDate")), remote=item.get("WorkplaceTypeCode"),
                           method="Oracle Recruiting Cloud REST")
                if job:
                    job["date_source"] = "employer job board"
                    jobs.append(job)
        return jobs, total

    async def enumerate(self, http: Any, board: Board, *, india_only: bool = True) -> ReadResult:
        jobs: list[dict[str, Any]] = []
        total, pages, offset = None, 0, 0
        while pages < PAGE_LIMIT:
            result = await http.get(self.endpoint(board, offset, "India" if india_only else ""), accept_json=True)
            pages += 1
            payload = _json(result) if result.ok else None
            if payload is None:
                return _failure(result) if not jobs else ReadResult(jobs, SourceState.PARTIAL, result.error, pages, total)
            page, total = self.parse(payload, board)
            jobs += page
            offset += 25
            if len(page) < 25 or (total is not None and offset >= total):
                break
        if india_only:
            jobs = [j for j in jobs if is_india(j.get("location"), j.get("country"))]
        return ReadResult(jobs[:MAX_JOBS], SourceState.EXTRACT_OK if jobs else SourceState.NO_RESULTS, None, pages, total)


# ------------------------------------------------------------------------------------------ Eightfold
class EightfoldReader(Reader):
    """Eightfold: the public position search of the career site (``/api/apply/v2/jobs``)."""
    key, name, interface = "eightfold", "Eightfold", "public JSON (/api/apply/v2/jobs)"

    @staticmethod
    def endpoint(board: Board, start: int = 0, location: str = "") -> str:
        host, _, domain = board.tenant.partition("|")
        url = f"https://{host}/api/apply/v2/jobs?domain={quote(domain)}&start={start}&num=10&sort_by=timestamp"
        return url + (f"&location={quote(location)}" if location else "")

    @staticmethod
    def location(item: dict[str, Any]) -> str:
        places = item.get("locations") if isinstance(item.get("locations"), list) else [item.get("location")]
        return "; ".join(dict.fromkeys(str(p).replace(",", ", ") for p in places if p))

    @staticmethod
    def posting_date(item: dict[str, Any]) -> str | None:
        return _iso(item.get("t_create") or item.get("t_update"))

    @staticmethod
    def apply_url(item: dict[str, Any], board: Board) -> str:
        host = board.tenant.partition("|")[0]
        return str(item.get("canonicalPositionUrl") or f"https://{host}/careers/job/{item.get('id')}")

    @classmethod
    def parse(cls, payload: Any, board: Board) -> list[dict[str, Any]]:
        jobs = []
        for item in (payload or {}).get("positions") or []:
            job = _job(board, title=item.get("name"), url=cls.apply_url(item, board), location=cls.location(item),
                       posted=cls.posting_date(item), description=item.get("job_description"),
                       requisition=item.get("display_job_id") or item.get("id"),
                       remote=item.get("work_location_option"), method="Eightfold public position search")
            if job:
                job["date_source"] = "employer job board"
                jobs.append(job)
        return jobs

    async def enumerate(self, http: Any, board: Board, *, india_only: bool = True) -> ReadResult:
        jobs: list[dict[str, Any]] = []
        total, pages, start = None, 0, 0
        while pages < PAGE_LIMIT * 2:
            result = await http.get(self.endpoint(board, start, "India" if india_only else ""), accept_json=True)
            pages += 1
            payload = _json(result) if result.ok else None
            if payload is None:
                return _failure(result) if not jobs else ReadResult(jobs, SourceState.PARTIAL, result.error, pages, total)
            page = self.parse(payload, board)
            total = int(payload.get("count") or 0)
            jobs += page
            start += 10
            if len(page) < 10 or start >= total:
                break
        if india_only:
            jobs = [j for j in jobs if is_india(j.get("location"))]
        return ReadResult(jobs[:MAX_JOBS], SourceState.EXTRACT_OK if jobs else SourceState.NO_RESULTS, None, pages, total)


# ------------------------------------------------------------------------------------------ SuccessFactors
class SuccessFactorsReader(Reader):
    """SAP SuccessFactors Career Site Builder: the public search page (``/search/?q=&locationsearch=``)."""
    key, name, interface = "successfactors", "SAP SuccessFactors", "public career-site search HTML (/search/)"

    @staticmethod
    def endpoint(board: Board, start: int = 0, location: str = "") -> str:
        base = board.tenant if board.tenant.startswith("http") else f"https://{board.tenant}"
        return f"{base.rstrip('/')}/search/?q=&locationsearch={quote(location)}&startrow={start}"

    @classmethod
    def parse(cls, html: str, board: Board, base_url: str) -> list[dict[str, Any]]:
        doc = _doc(html)
        if doc is None:
            return []
        jobs = []
        rows = doc.xpath("//tr[contains(@class,'data-row')]") or doc.xpath("//li[contains(@class,'job-tile')]")
        for row in rows:
            link = (row.xpath(".//a[contains(@class,'jobTitle-link')]") or row.xpath(".//a[contains(@href,'/job/')]") or [None])[0]
            if link is None:
                continue
            location = " ".join(" ".join(row.xpath(".//*[contains(@class,'jobLocation')]//text()")).split())
            posted = " ".join(" ".join(row.xpath(".//*[contains(@class,'jobDate')]//text()")).split())
            requisition = re.search(r"/(\d{5,})/?$", str(link.get("href") or ""))
            job = _job(board, title=link.text_content(), url=urljoin(base_url, str(link.get("href") or "")),
                       location=cls.location({"location": location}), posted=cls.posting_date({"date": posted}),
                       requisition=requisition.group(1) if requisition else None, method="SuccessFactors career-site search")
            if job:
                job["date_source"] = "employer job board" if job["posted_date"] else None
                jobs.append(job)
        return jobs

    @staticmethod
    def location(item: dict[str, Any]) -> str:
        return re.sub(r"\s*,\s*", ", ", str(item.get("location") or "")).strip(" ,")

    @staticmethod
    def posting_date(item: dict[str, Any]) -> str | None:
        return _iso(item.get("date"))

    @staticmethod
    def apply_url(item: dict[str, Any], board: Board) -> str:
        return str(item.get("url") or "")

    async def enumerate(self, http: Any, board: Board, *, india_only: bool = True) -> ReadResult:
        jobs: list[dict[str, Any]] = []
        pages, start = 0, 0
        while pages < PAGE_LIMIT:
            url = self.endpoint(board, start, "India" if india_only else "")
            result = await http.get(url)
            pages += 1
            if not result.ok:
                return _failure(result) if not jobs else ReadResult(jobs, SourceState.PARTIAL, result.error, pages)
            page = self.parse(result.text, board, result.final_url or url)
            new = [j for j in page if j["url"] not in {x["url"] for x in jobs}]
            jobs += new
            start += 25
            if len(page) < 25 or not new:
                break
        return ReadResult(jobs[:MAX_JOBS], SourceState.EXTRACT_OK if jobs else SourceState.NO_RESULTS, None, pages)


# ------------------------------------------------------------------------------------------ iCIMS
class ICIMSReader(Reader):
    """iCIMS: the public job search of a ``careers-<tenant>.icims.com`` portal (iframe view, plain HTML)."""
    key, name, interface = "icims", "iCIMS", "public job-search HTML (/jobs/search?in_iframe=1)"

    @staticmethod
    def endpoint(board: Board, page: int = 0, location: str = "") -> str:
        url = f"https://{board.tenant}/jobs/search?ss=1&in_iframe=1&pr={page}"
        return url + (f"&searchKeyword={quote(location)}" if location else "")

    @classmethod
    def parse(cls, html: str, board: Board, base_url: str) -> list[dict[str, Any]]:
        doc = _doc(html)
        if doc is None:
            return []
        jobs, seen = [], set()
        for link in doc.xpath("//a[contains(@href,'/jobs/')]"):
            href = str(link.get("href") or "")
            found = re.search(r"/jobs/(\d+)/[^/?#]+/job", href)
            if not found or found.group(1) in seen:
                continue
            seen.add(found.group(1))
            title = " ".join(" ".join(link.xpath(".//h2//text()|.//h3//text()")).split()) or \
                re.sub(r"^\s*(?:Job\s+)?Title\s*", "", " ".join(link.text_content().split()))
            row = link
            for _ in range(4):
                if row.getparent() is None:
                    break
                row = row.getparent()
                if "row" in str(row.get("class") or ""):
                    break
            text = " ".join(row.text_content().split())
            location = re.search(r"(?:Job\s+)?Locations?\s*:?\s*([A-Z]{2}-[A-Za-z .'-]+(?:-[A-Za-z .'-]+)?(?:\s*\|\s*[A-Z]{2}-[A-Za-z .'-]+)*)", text)
            posted = re.search(r"(?:Posted\s+Date|Date\s+Posted)\s*:?\s*(\d{1,2}/\d{1,2}/\d{4}|\d+\s+\w+\s+ago)", text, re.I)
            job = _job(board, title=title, url=urljoin(base_url, href.split("?")[0]),
                       location=cls.location({"location": location.group(1) if location else ""}),
                       posted=cls.posting_date({"date": posted.group(1) if posted else ""}), requisition=found.group(1),
                       method="iCIMS public job search")
            if job:
                jobs.append(job)
        return jobs

    @staticmethod
    def location(item: dict[str, Any]) -> str:
        parts = [" ".join(reversed([p.strip() for p in place.split("-") if p.strip()]))
                 for place in str(item.get("location") or "").split("|")]
        return "; ".join(p.replace("IN", "India", 1) if p.endswith(" IN") or p == "IN" else p for p in parts if p)

    @staticmethod
    def posting_date(item: dict[str, Any], today: date | None = None) -> str | None:
        text = str(item.get("date") or "")
        found = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
        if found:  # iCIMS portals print US dates (month/day/year)
            try:
                return date(int(found.group(3)), int(found.group(1)), int(found.group(2))).isoformat()
            except ValueError:
                return None
        relative = parse_relative_date(text, today)
        return relative.isoformat() if relative else None

    @staticmethod
    def apply_url(item: dict[str, Any], board: Board) -> str:
        return str(item.get("url") or "")

    async def enumerate(self, http: Any, board: Board, *, india_only: bool = True) -> ReadResult:
        jobs: list[dict[str, Any]] = []
        pages = 0
        while pages < PAGE_LIMIT:
            url = self.endpoint(board, pages, "India" if india_only else "")
            result = await http.get(url)
            pages += 1
            if not result.ok:
                return _failure(result) if not jobs else ReadResult(jobs, SourceState.PARTIAL, result.error, pages)
            page = self.parse(result.text, board, result.final_url or url)
            new = [j for j in page if j["url"] not in {x["url"] for x in jobs}]
            jobs += new
            if not new:
                break
        if india_only:
            located = [j for j in jobs if j.get("location")]
            jobs = [j for j in jobs if is_india(j.get("location"))] if located else jobs
        return ReadResult(jobs[:MAX_JOBS], SourceState.EXTRACT_OK if jobs else SourceState.NO_RESULTS, None, pages)


# ------------------------------------------------------------------------------------------ Phenom
class PhenomReader(Reader):
    """Phenom People: the job data embedded in the public search page (``phApp.ddo``)."""
    key, name, interface = "phenom", "Phenom", "job data embedded in the public search page (phApp.ddo)"

    @staticmethod
    def endpoint(board: Board, start: int = 0, location: str = "") -> str:
        base = board.tenant if board.tenant.startswith("http") else f"https://{board.tenant}"
        return f"{base.rstrip('/')}/search-results?from={start}&s=1" + (f"&location={quote(location)}" if location else "")

    @staticmethod
    def embedded(html: str) -> dict[str, Any]:
        found = re.search(r"phApp\.ddo\s*=\s*(\{.*?\})\s*;\s*(?:phApp\.|</script>)", html or "", re.S)
        if not found:
            return {}
        try:
            return json.loads(found.group(1))
        except ValueError:
            return {}

    @classmethod
    def parse(cls, html: str, board: Board, base_url: str) -> tuple[list[dict[str, Any]], int]:
        data = ((cls.embedded(html).get("eagerLoadRefineSearch") or {}).get("data") or {})
        jobs = []
        for item in data.get("jobs") or []:
            job = _job(board, title=item.get("title"), url=cls.apply_url(item, board) or base_url, location=cls.location(item),
                       posted=cls.posting_date(item), description=item.get("descriptionTeaser"),
                       requisition=item.get("reqId") or item.get("jobId"), country=item.get("country"),
                       employment_type=item.get("type"), method="Phenom embedded job data")
            if job:
                job["date_source"] = "employer job board" if job["posted_date"] else None
                jobs.append(job)
        return jobs, int(data.get("totalHits") or len(jobs))

    @staticmethod
    def location(item: dict[str, Any]) -> str:
        if item.get("multi_location"):
            return "; ".join(dict.fromkeys(str(p) for p in item["multi_location"] if p))
        return ", ".join(str(p) for p in (item.get("city"), item.get("state"), item.get("country")) if p) or str(item.get("location") or "")

    @staticmethod
    def posting_date(item: dict[str, Any]) -> str | None:
        return _iso(item.get("postedDate") or item.get("dateCreated"))

    @staticmethod
    def apply_url(item: dict[str, Any], board: Board) -> str:
        base = board.tenant if board.tenant.startswith("http") else f"https://{board.tenant}"
        if item.get("jobSeqNo"):
            return f"{base.rstrip('/')}/job/{item['jobSeqNo']}"
        return str(item.get("applyUrl") or "").split("/apply")[0]

    async def enumerate(self, http: Any, board: Board, *, india_only: bool = True) -> ReadResult:
        jobs: list[dict[str, Any]] = []
        pages, start, total = 0, 0, None
        while pages < PAGE_LIMIT:
            url = self.endpoint(board, start, "India" if india_only else "")
            result = await http.get(url)
            pages += 1
            if not result.ok:
                return _failure(result) if not jobs else ReadResult(jobs, SourceState.PARTIAL, result.error, pages, total)
            page, total = self.parse(result.text, board, result.final_url or url)
            new = [j for j in page if j["url"] not in {x["url"] for x in jobs}]
            jobs += new
            start += max(10, len(page))
            if not new or start >= (total or 0):
                break
        if india_only:
            jobs = [j for j in jobs if is_india(j.get("location"), j.get("country"))]
        if not jobs and pages == 1 and total in (None, 0):
            return ReadResult(state=SourceState.NO_RESULTS, pages=pages, total=total,
                              error="no embedded job data (the page may need rendering)")
        return ReadResult(jobs[:MAX_JOBS], SourceState.EXTRACT_OK if jobs else SourceState.NO_RESULTS, None, pages, total)


# ------------------------------------------------------------------------------------------ feeds
class TeamtailorReader(Reader):
    """Teamtailor: the public RSS feed every career site publishes (``/jobs.rss``)."""
    key, name, interface = "teamtailor", "Teamtailor", "public RSS feed (/jobs.rss)"

    @staticmethod
    def endpoint(board: Board) -> str:
        host = board.tenant if "." in board.tenant else f"{board.tenant}.teamtailor.com"
        return f"https://{host}/jobs.rss"

    @classmethod
    def parse(cls, xml_text: str, board: Board) -> list[dict[str, Any]]:
        try:
            root = ET.fromstring((xml_text or "").encode("utf-8", "replace"))
        except ET.ParseError:
            return []
        jobs = []
        for node in root.iter("item"):
            values: dict[str, Any] = {"places": []}
            for child in node:
                tag = child.tag.rsplit("}", 1)[-1]
                if tag == "locations":
                    for place in child:
                        parts = {p.tag.rsplit("}", 1)[-1]: (p.text or "").strip() for p in place}
                        values["places"].append(", ".join(v for v in (parts.get("city") or parts.get("name"), parts.get("country")) if v))
                elif tag in {"title", "link", "pubDate", "description", "remoteStatus", "guid"}:
                    values[tag] = (child.text or "").strip()
            job = _job(board, title=values.get("title"), url=values.get("link"), location=cls.location(values),
                       posted=cls.posting_date(values), description=values.get("description"),
                       remote="remote" if "fully" in str(values.get("remoteStatus") or "") else values.get("remoteStatus"),
                       method="Teamtailor public RSS")
            if job:
                job["date_source"] = "employer job board"
                jobs.append(job)
        return jobs

    @staticmethod
    def location(item: dict[str, Any]) -> str:
        return "; ".join(dict.fromkeys(p for p in item.get("places") or [] if p))

    @staticmethod
    def posting_date(item: dict[str, Any]) -> str | None:
        return _iso(item.get("pubDate"))

    @staticmethod
    def apply_url(item: dict[str, Any], board: Board) -> str:
        return str(item.get("link") or "")

    async def enumerate(self, http: Any, board: Board, *, india_only: bool = True) -> ReadResult:
        result = await http.get(self.endpoint(board), accept_json=True)
        if not result.ok:
            return _failure(result)
        jobs = self.parse(result.text, board)
        if india_only:
            jobs = [j for j in jobs if is_india(j.get("location")) or (j.get("remote") == "remote" and not j.get("location"))]
        return ReadResult(jobs[:MAX_JOBS], SourceState.EXTRACT_OK if jobs else SourceState.NO_RESULTS, None, 1, len(jobs))


class PersonioReader(Reader):
    """Personio: the documented public XML feed (``https://{slug}.jobs.personio.de/xml``)."""
    key, name, interface = "personio", "Personio", "public XML feed (/xml)"

    @staticmethod
    def host(board: Board) -> str:
        return board.tenant if "." in board.tenant else f"{board.tenant}.jobs.personio.de"

    @classmethod
    def endpoint(cls, board: Board) -> str:
        return f"https://{cls.host(board)}/xml"

    @classmethod
    def parse(cls, xml_text: str, board: Board) -> list[dict[str, Any]]:
        try:
            root = ET.fromstring((xml_text or "").encode("utf-8", "replace"))
        except ET.ParseError:
            return []
        jobs = []
        for node in root.iter("position"):
            item = {child.tag: (child.text or "").strip() for child in node if not len(child)}
            description = " ".join((value.text or "") for value in node.iter("value"))
            job = _job(board, title=item.get("name"), url=cls.apply_url(item, board), location=cls.location(item),
                       posted=cls.posting_date(item), description=description, requisition=item.get("id"),
                       employment_type=item.get("schedule") or item.get("employmentType"), method="Personio public XML feed")
            if job:
                job["date_source"] = "employer job board"
                jobs.append(job)
        return jobs

    @staticmethod
    def location(item: dict[str, Any]) -> str:
        return str(item.get("office") or "")

    @staticmethod
    def posting_date(item: dict[str, Any]) -> str | None:
        return _iso(item.get("createdAt"))

    @classmethod
    def apply_url(cls, item: dict[str, Any], board: Board) -> str:
        return f"https://{cls.host(board)}/job/{item.get('id')}" if item.get("id") else ""

    async def enumerate(self, http: Any, board: Board, *, india_only: bool = True) -> ReadResult:
        result = await http.get(self.endpoint(board), accept_json=True)
        if not result.ok:
            return _failure(result)
        jobs = self.parse(result.text, board)
        if india_only:
            jobs = [j for j in jobs if is_india(j.get("location"))]
        return ReadResult(jobs[:MAX_JOBS], SourceState.EXTRACT_OK if jobs else SourceState.NO_RESULTS, None, 1, len(jobs))


class KulaReader(Reader):
    """Kula (Indian ATS): the server-rendered public careers page ``https://careers.kula.ai/{slug}``."""
    key, name, interface = "kula", "Kula", "public careers page HTML (careers.kula.ai/{slug})"

    @staticmethod
    def endpoint(board: Board) -> str:
        return f"https://careers.kula.ai/{quote(board.tenant)}"

    @classmethod
    def parse(cls, html: str, board: Board) -> list[dict[str, Any]]:
        doc = _doc(html)
        if doc is None:
            return []
        jobs, seen = [], set()
        pattern = re.compile(rf"^/{re.escape(board.tenant)}/(\d+)(?:-[^/?#]*)?$", re.I)
        for link in doc.xpath("//a[@href]"):
            href = str(link.get("href") or "")
            found = pattern.match(href)
            if not found or found.group(1) in seen:
                continue
            seen.add(found.group(1))
            card = link.getparent()
            for _ in range(3):
                if card is None or card.xpath(".//p"):
                    break
                card = card.getparent()
            paragraphs = [" ".join(p.text_content().split()) for p in (card.xpath(".//p") if card is not None else [])]
            title = next((p for p in paragraphs if p and "•" not in p), "") or \
                found.group(0).rsplit("/", 1)[-1].split("-", 1)[-1].replace("-", " ").title()
            meta = next((p for p in paragraphs if "•" in p), "")
            item = {"meta": meta, "href": href}
            parts = [part.strip() for part in meta.split("•")]
            job = _job(board, title=title, url=cls.apply_url(item, board), location=cls.location(item),
                       requisition=found.group(1), method="Kula public careers page",
                       employment_type=next((p for p in parts if re.search(r"full|part|intern|contract", p, re.I)), None),
                       remote=next((p for p in parts if re.search(r"remote|hybrid|on-?site", p, re.I)), None))
            if job:
                jobs.append(job)
        return jobs

    @staticmethod
    def location(item: dict[str, Any]) -> str:
        parts = [part.strip() for part in str(item.get("meta") or "").split("•")]
        return next((p for p in parts if "," in p or INDIA.search(p)), "")

    @staticmethod
    def posting_date(item: dict[str, Any]) -> str | None:
        return None  # the public page does not state one

    @staticmethod
    def apply_url(item: dict[str, Any], board: Board) -> str:
        return f"https://careers.kula.ai{item.get('href') or ''}"

    async def enumerate(self, http: Any, board: Board, *, india_only: bool = True) -> ReadResult:
        result = await http.get(self.endpoint(board))
        if not result.ok:
            return _failure(result)
        jobs = self.parse(result.text, board)
        if india_only:
            jobs = [j for j in jobs if is_india(j.get("location")) or not j.get("location")]
        return ReadResult(jobs[:MAX_JOBS], SourceState.EXTRACT_OK if jobs else SourceState.NO_RESULTS, None, 1, len(jobs))


# ------------------------------------------------------------------------------------------ existing public APIs
class BoardAPIReader(Reader):
    """Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Recruitee: documented public job-board APIs,
    read by ``app.services.ats_sources`` (complete boards, paginated)."""

    def __init__(self, key: str, name: str, interface: str) -> None:
        self.key, self.name, self.interface = key, name, interface

    async def enumerate(self, http: Any, board: Board, *, india_only: bool = True, fetcher: Any | None = None) -> ReadResult:
        from app.services import ats_sources
        fetch = fetcher or ats_sources.fetch_company_jobs
        jobs, coverage = await fetch([{"name": board.name or board.tenant, "ats": board.ats, "slug": board.tenant}])
        status = str((coverage[0] if coverage else {}).get("status") or "")
        for job in jobs:
            job.setdefault("extraction_method", f"{self.name} public API")
        if india_only:
            jobs = [j for j in jobs if is_india(j.get("location"), j.get("country")) or
                    (str(j.get("remote") or "").casefold() == "remote" and not j.get("location"))]
        if status.startswith("ok"):
            return ReadResult(jobs[:MAX_JOBS * 3], SourceState.EXTRACT_OK if jobs else SourceState.NO_RESULTS, None,
                              int((coverage[0] or {}).get("pages") or 1))
        if status.startswith("partial"):
            return ReadResult(jobs, SourceState.PARTIAL, status, int((coverage[0] or {}).get("pages") or 1))
        state = SourceState.NOT_FOUND if "404" in status else SourceState.ACCESS_DENIED if "blocked" in status else SourceState.UNAVAILABLE
        return ReadResult(state=state, error=status or "no response", pages=1)


class CareerPageOnly(Reader):
    """An ATS without a public job-board interface: its tenant pages are read as an ordinary career page."""
    public = False

    def __init__(self, key: str, name: str, reason: str) -> None:
        self.key, self.name, self.interface = key, name, f"career page ({reason})"

    async def enumerate(self, http: Any, board: Board, *, india_only: bool = True) -> ReadResult:
        return ReadResult(state="career_page", error=self.interface)


READERS: dict[str, Reader] = {reader.key: reader for reader in [
    WorkdayReader(), OracleReader(), EightfoldReader(), SuccessFactorsReader(), ICIMSReader(), PhenomReader(),
    TeamtailorReader(), PersonioReader(), KulaReader(),
    BoardAPIReader("greenhouse", "Greenhouse", "Greenhouse Job Board API (public)"),
    BoardAPIReader("lever", "Lever", "Lever Postings API (public)"),
    BoardAPIReader("ashby", "Ashby", "Ashby Job Posting API (public)"),
    BoardAPIReader("workable", "Workable", "Workable public widget API"),
    BoardAPIReader("smartrecruiters", "SmartRecruiters", "SmartRecruiters Posting API (public)"),
    BoardAPIReader("recruitee", "Recruitee", "Recruitee Careers Site API (public)"),
    CareerPageOnly("taleo", "Taleo", "no public feed; search is a private endpoint"),
    CareerPageOnly("darwinbox", "Darwinbox", "JavaScript portal with no public feed"),
    CareerPageOnly("keka", "Keka", "JavaScript portal; pages are marked noindex and robots.txt disallows them"),
    CareerPageOnly("zoho_recruit", "Zoho Recruit", "JavaScript portal with no public feed"),
    CareerPageOnly("freshteam", "Freshteam", "robots.txt disallows the job pages"),
    CareerPageOnly("turbohire", "TurboHire", "JavaScript portal with no public feed"),
]}
PUBLIC_READERS = sorted(key for key, reader in READERS.items() if reader.public)

_DETECTORS: list[tuple[str, re.Pattern[str]]] = [
    ("workday", re.compile(r"https?://([a-z0-9-]+\.wd\d+\.myworkday(?:jobs|site)\.com)/(?:wday/cxs/[^/]+/|[a-z]{2}-[A-Z]{2}/|recruiting/[^/]+/)?"
                           r"([A-Za-z0-9_-]+)", re.I)),
    ("oracle", re.compile(r"https?://([a-z0-9-]+\.fa\.[a-z0-9-]+\.oraclecloud\.com)/hcmUI/CandidateExperience/[a-z-]+/sites/([A-Za-z0-9_-]+)", re.I)),
    ("eightfold", re.compile(r"https?://([a-z0-9.-]+\.eightfold\.ai)/careers[^\"'\s]*?[?&]domain=([a-z0-9.-]+)", re.I)),
    ("icims", re.compile(r"https?://((?:careers|jobs)-[a-z0-9-]+\.icims\.com)()", re.I)),
    ("teamtailor", re.compile(r"https?://([a-z0-9-]+)\.teamtailor\.com()", re.I)),
    ("personio", re.compile(r"https?://([a-z0-9-]+)\.jobs\.personio\.(?:de|com)()", re.I)),
    ("kula", re.compile(r"https?://careers\.kula\.ai/([A-Za-z0-9_-]+)()", re.I)),
    ("greenhouse", re.compile(r"https?://(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board(?:/js)?\?for=)?([A-Za-z0-9_-]+)()", re.I)),
    ("lever", re.compile(r"https?://jobs\.(?:eu\.)?lever\.co/([A-Za-z0-9_.-]+)()", re.I)),
    ("ashby", re.compile(r"https?://jobs\.ashbyhq\.com/([A-Za-z0-9_.%-]+)()", re.I)),
    ("workable", re.compile(r"https?://apply\.workable\.com/(?!api\b|j/)([A-Za-z0-9_-]+)()", re.I)),
    ("smartrecruiters", re.compile(r"https?://(?:careers|jobs)\.smartrecruiters\.com/([A-Za-z0-9_-]+)()", re.I)),
    ("recruitee", re.compile(r"https?://([a-z0-9-]+)\.recruitee\.com()", re.I)),
    ("successfactors", re.compile(r"https?://(career\d*\.successfactors\.(?:com|eu))/[^\"'\s]*?company=([A-Za-z0-9_-]+)", re.I)),
    ("taleo", re.compile(r"https?://([a-z0-9-]+\.taleo\.net)()", re.I)),
    ("darwinbox", re.compile(r"https?://([a-z0-9-]+\.darwinbox\.(?:in|com))()", re.I)),
    ("keka", re.compile(r"https?://([a-z0-9-]+)\.keka\.com/careers()", re.I)),
    ("zoho_recruit", re.compile(r"https?://([a-z0-9-]+\.zohorecruit\.(?:com|in|eu))()", re.I)),
    ("freshteam", re.compile(r"https?://([a-z0-9-]+)\.freshteam\.com()", re.I)),
    ("turbohire", re.compile(r"https?://([a-z0-9-]+)\.turbohire\.co()", re.I)),
]
_RESERVED = {"embed", "api", "www", "jobs", "careers", "job", "search", "login", "apply", "en", "boards", "static", "assets",
             "wday", "recruiting", "j", "o", "app", "cdn", "assets-cdn"}


def detect_board(text: str, *, name: str = "", page_url: str = "") -> Board | None:
    """The ATS board referenced by a careers page (its URL, anchors, iframes, scripts). Never guesses a tenant.

    ``page_url`` is the careers page itself: a SuccessFactors or Phenom career site lives on the company's own
    domain and is recognised by markers in its HTML, in which case the page's own origin is the tenant."""
    haystack = f"{page_url}\n{text or ''}"[:600_000].replace("\\/", "/").replace("\\u002F", "/")
    for key, pattern in _DETECTORS:
        for match in pattern.finditer(haystack):
            first, second = match.group(1), match.group(2)
            if key == "workday":
                if second.casefold() in _RESERVED:
                    continue
                tenant = f"{first.casefold()}/{second}"
            elif key == "oracle":
                tenant = f"{first.casefold()}/{second}"
            elif key == "eightfold":
                tenant = f"{first.casefold()}|{second.casefold()}"
            elif key == "successfactors":
                continue  # the legacy career{N} host is only a marker; the Career Site Builder origin is the tenant
            else:
                tenant = first if key in {"greenhouse", "lever", "ashby", "workable", "smartrecruiters", "kula"} else first.casefold()
                if tenant.casefold() in _RESERVED:
                    continue
            return Board(key, tenant, name, page_url)
    origin = ""
    if page_url:
        parts = urlsplit(page_url)
        origin = f"{parts.scheme}://{parts.netloc}" if parts.scheme in {"http", "https"} and parts.netloc else ""
    if origin:
        if re.search(r"phApp\.ddo\s*=|cdn\.phenompeople\.com|phenompeople", haystack):
            return Board("phenom", origin, name, page_url)
        if re.search(r"successfactors\.(?:com|eu)|rmkcdn\.successfactors|jobs2web|class=\"[^\"]*jobTitle-link", haystack):
            return Board("successfactors", origin, name, page_url)
        if re.search(r"eightfold\.ai|/api/apply/v2/jobs", haystack) and re.search(r"/careers", page_url):
            domain = re.search(r"domain[\"'=:\s]+([a-z0-9.-]+\.[a-z]{2,})", haystack)
            if domain:
                return Board("eightfold", f"{urlsplit(page_url).netloc.casefold()}|{domain.group(1).casefold()}", name, page_url)
    return None


def summary() -> list[dict[str, Any]]:
    return [{"key": reader.key, "name": reader.name, "interface": reader.interface, "public": reader.public}
            for reader in READERS.values()]
