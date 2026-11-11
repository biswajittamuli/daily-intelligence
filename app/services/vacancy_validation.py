"""Vacancy validation gate (v4.3).

Every record passes the same deterministic stages before it may be ranked or published:

    extraction (normalise) -> document classification -> vacancy validation -> freshness
    -> geography -> (eligibility, done by assessment) -> dedup -> matching -> ranking -> publication

Each stage returns a result and, when it rejects, a reason. Nothing here performs I/O, so the same
functions run during discovery (before ranking), when stored listings are re-scored, and when the feed
is built, so older rows are judged by the same rules as new ones.

Principles:
- A first-discovered time is never a publication date. ``published_at`` stays ``None`` unless a source
  stated it; freshness comes only from a stated date.
- Geography fails closed. "Remote" alone is not evidence that India is eligible, and a place that is not
  in the target country is outside it even when this module does not recognise its name.
- A talent network, candidate registration page, search page or article is never a vacancy, whatever its
  skill overlap.
"""
from __future__ import annotations

import html
import re
from datetime import date, datetime, timezone
from typing import Any

from app.services.freshness import date_confidence, parse_date

# ------------------------------------------------------------------ normalisation
_ENTITY = re.compile(r"&(?:[a-zA-Z]{2,8}|#\d{2,6}|#x[0-9a-fA-F]{2,5});")
_TRAILING_CTA = re.compile(r"(?:\s*[-–|·•]?\s*(?:view\s*(?:&|and)\s*apply|apply\s*now|apply|learn\s*more|"
                           r"view\s*details|details|read\s*more))+\s*$", re.I)


def clean_text(value: Any) -> str | None:
    """Decode HTML entities (twice, for double-escaped feeds) and collapse whitespace. URLs are not passed here."""
    if value is None:
        return None
    text = str(value)
    for _ in range(2):
        if not _ENTITY.search(text):
            break
        text = html.unescape(text)
    text = " ".join(text.replace(" ", " ").split())
    return text or None


def clean_title(value: Any) -> str | None:
    """Entity-decoded title without trailing call-to-action words or a repeated trailing phrase."""
    text = clean_text(value)
    if not text:
        return text
    text = _TRAILING_CTA.sub("", text).strip(" -–|·•")
    text = re.sub(r"\s+job details?\s*(?:[|–-].*)?$", "", text, flags=re.I).strip(" -–|·•") or text
    words = text.split()
    # "AI Platform Engineer San Francisco San Francisco" -> drop the duplicated tail once.
    for size in (3, 2, 1):
        if len(words) > size * 2 + 1 and words[-size:] == words[-2 * size:-size]:
            words = words[:-size]
            break
    return " ".join(words) or text


# ------------------------------------------------------------------ document classification
DOCUMENT_TYPES = {
    "vacancy": "Individual job vacancy",
    "internship": "Internship vacancy",
    "graduate": "Graduate or fresher recruitment",
    "government": "Government recruitment notification",
    "psu": "PSU recruitment notification",
    "talent_network": "Talent network",
    "candidate_registration": "Candidate registration",
    "agency_profile": "Recruitment agency profile",
    "careers_home": "Employer careers homepage",
    "search_results": "Job-search results page",
    "category_page": "Job category page",
    "article": "Recruitment article",
    "company_news": "Funding or company news",
    "other": "Other",
}
VACANCY_TYPES = {"vacancy", "internship", "graduate", "government", "psu"}
SEPARATE_SECTION_TYPES = {"talent_network", "candidate_registration"}

TALENT = re.compile(
    r"\b(talent (?:network|community|pool|pipeline|cloud|collective)|matching network|ai matching|"
    r"join our (?:talent|network|community|pool|bench)|general application|open application|"
    r"spontaneous application|expression of interest|future (?:opportunities|openings|roles)|"
    r"all industries\s*(?:&|and)\s*skill levels|all (?:skill|experience) levels|"
    r"professionals\s*(?:&|and)\s*specialists|(?:freelance|expert) (?:network|marketplace)|"
    r"ai (?:training|tutor|trainer) community|\(ai community\))\b", re.I)
REGISTRATION = re.compile(
    r"\b(register (?:your|as an?|now as) (?:profile|candidate|freelancer|expert|contractor)|candidate registration|"
    r"create (?:your|a) (?:candidate )?profile|submit your (?:cv|resume) for (?:future|upcoming)|"
    r"sign up to (?:get|receive) (?:matched|job alerts)|upload your (?:cv|resume) and get matched)\b", re.I)
AGENCY = re.compile(r"^(?:about|our services|services|clients|why choose us)\b|"
                    r"\b(?:staffing|placement|manpower|recruitment) (?:agency|consultancy|consultants|services|firm)\s*$",
                    re.I)
ARTICLE = re.compile(r"\b(how to|guide to|tips for|salary (?:guide|trends|in)|interview questions|top \d+|best \d+|"
                     r"what is|career path|roadmap|explained|vs\.?)\b", re.I)
NEWS = re.compile(r"\b(raises|raised|funding round|series [a-e]\b|seed round|pre-seed|acquires|acquired by|"
                  r"valuation|ipo|layoffs?|announces|launches)\b", re.I)
PSU = re.compile(r"\b(ongc|ntpc|bhel|gail|iocl|indian oil|isro|drdo|barc|bel|hal|sail|coal india|power ?grid|"
                 r"nhpc|bpcl|hpcl|nlc|ecil|cdac|c-dac|nic|rites|ircon|bsnl|mtnl)\b", re.I)
GOVT = re.compile(r"\b(ssc|upsc|ibps|rrb|psc|government of|govt\.?|ministry of|public service commission|"
                  r"sarkari|central government)\b", re.I)
NOTIFICATION = re.compile(r"\b(recruitment(?: \d{4})?|notification|advertisement|advt\.?)\b", re.I)
INTERN = re.compile(r"\b(intern(?:ship)?s?|trainee|apprentice(?:ship)?)\b", re.I)
GRADUATE = re.compile(r"\b(new grad(?:uate)?|graduate (?:engineer|trainee|program(?:me)?|developer|software)|"
                      r"fresher|freshers|campus (?:hiring|recruitment|drive)|early career|entry[- ]level)\b", re.I)
ROLE_NOUN = re.compile(r"\b(engineer|developer|scientist|analyst|architect|manager|designer|specialist|consultant|"
                       r"lead|administrator|programmer|researcher|associate|executive|officer|technician|"
                       r"intern|trainee|sde|swe|devops|sre|tester|qa|head|director|writer|coordinator|"
                       r"representative|support|operator|accountant|member of technical staff|mts)(?:s|es)?\b", re.I)
JOB_COUNT_TITLE = re.compile(r"^\s*[\d,]+\+?\s+.*\b(jobs|vacancies|openings|positions)\b", re.I)
JOBS_IN_TITLE = re.compile(r"\b(jobs|vacancies|openings|job openings)\s+(?:in|for|at|near)\b", re.I)
CATEGORY_PATH = re.compile(r"/(?:category|categories|browse|tag|tags|skills?|job-category|function|industry)/", re.I)
CAREERS_TITLE = re.compile(r"^\s*(?:careers?|jobs|work with us|join (?:us|our team)|open (?:positions|roles)|"
                           r"current openings|life at)\b|\b(?:careers?|jobs) (?:at|@)\s+\S+\s*$|^\S+(?:\s+\S+)?\s+careers?\s*$",
                           re.I)
CAREERS_PATH = re.compile(r"^/?(?:[a-z]{2}(?:-[a-z]{2})?/)?(?:careers?|jobs|join-us|work-with-us|opportunities)/?$", re.I)


def classify_document(record: dict[str, Any]) -> dict[str, Any]:
    """Return {type, label, is_vacancy, reason, flags}. Uses title, URL, source kind and leading text only."""
    from urllib.parse import urlsplit

    from app.services.job_sources.ats_registry import is_ats_listing
    from app.services.listing_links import is_listing_url, looks_like_index

    title = clean_title(record.get("title")) or ""
    url = str(record.get("original_url") or record.get("url") or "")
    text = str(record.get("raw_text") or record.get("description") or "")[:1500]
    kind = str(record.get("source_kind") or ((record.get("raw") or {}).get("source_kind")) or "")
    via = str(record.get("discovered_via") or "")
    path = urlsplit(url).path if url else ""
    employer_owned = via in {"company career board", "company career page"} or is_ats_listing(url)
    flags: list[str] = []
    if not str(record.get("employer") or "").strip():
        flags.append("employer_missing")

    def result(kind_: str, reason: str) -> dict[str, Any]:
        return {"type": kind_, "label": DOCUMENT_TYPES[kind_], "is_vacancy": kind_ in VACANCY_TYPES,
                "separate_section": kind_ in SEPARATE_SECTION_TYPES, "reason": reason, "flags": flags}

    head = f"{title} {text[:400]}"
    if TALENT.search(title) or (TALENT.search(text[:600]) and not ROLE_NOUN.search(title)):
        return result("talent_network", "Talent network / matching pool, not one vacancy: "
                      f"“{(TALENT.search(title) or TALENT.search(text[:600])).group(0)}”")
    if REGISTRATION.search(head):
        return result("candidate_registration", f"Candidate registration page: “{REGISTRATION.search(head).group(0)}”")
    if kind in {"search_page", "index_page"}:
        return result("search_results", "Recorded as a search or index page")
    if not employer_owned:
        if JOB_COUNT_TITLE.search(title) or JOBS_IN_TITLE.search(title):
            return result("search_results", "Title lists many jobs")
        if CATEGORY_PATH.search(path) and not is_listing_url(url):
            return result("category_page", "Category or browse page")
        if looks_like_index(url, title) and not is_listing_url(url):
            return result("search_results", "Search or index page URL")
    if (CAREERS_TITLE.search(title) and not ROLE_NOUN.search(re.sub(r"\b(careers?|jobs)\b", "", title, flags=re.I))) \
            or (CAREERS_PATH.match(path) and not ROLE_NOUN.search(title)):
        return result("careers_home", "Employer careers homepage, not a single opening")
    if kind in {"job_news", "article", "news"} or (ARTICLE.search(title) and not ROLE_NOUN.search(title)):
        return result("article", "Article or guide about jobs")
    if NEWS.search(title) and not ROLE_NOUN.search(title):
        return result("company_news", "Funding or company news")
    if AGENCY.search(title) and not ROLE_NOUN.search(title):
        return result("agency_profile", "Recruitment agency page")
    if NOTIFICATION.search(title) and (PSU.search(title) or GOVT.search(title)):
        return result("psu" if PSU.search(title) else "government", "Official recruitment notification")
    if INTERN.search(title):
        return result("internship", "Internship title")
    if GRADUATE.search(title):
        return result("graduate", "Graduate / fresher recruitment title")
    if ROLE_NOUN.search(title):
        return result("vacancy", "Single role title")
    if employer_owned and title:
        return result("vacancy", "Listed on the employer's own job board")
    return result("other", "No role named in the title")


# ------------------------------------------------------------------ geography
GEO_LABELS = {
    "india": "India-based",
    "remote_india": "Remote — India explicitly eligible",
    "remote_unknown": "Remote — location restrictions unknown",
    "remote_not_india": "Remote — India not eligible",
    "relocation": "Relocation possible",
    "outside": "Outside target geography",
    "unknown": "Location not stated",
}
GEO_ELIGIBLE = {"india", "remote_india"}
GEO_UNCERTAIN = {"remote_unknown", "unknown", "relocation"}
GEO_EXCLUDED = {"remote_not_india", "outside"}

REMOTE = re.compile(r"\b(remote|work from home|wfh|work from anywhere|telecommute|distributed|anywhere)\b", re.I)
WORLDWIDE = re.compile(r"\b(worldwide|world ?wide|anywhere in the world|any country|global(?:ly)?|"
                       r"all countries|international|location independent)\b", re.I)
REGION_INCLUDING = re.compile(r"\b(apac|asia(?:[- ]pacific)?|south asia|emea and apac|ist time ?zone|"
                              r"gmt\s*\+\s*5:?30|utc\s*\+\s*5:?30)\b", re.I)
RELOCATION = re.compile(r"\b(relocation (?:assistance|support|package|provided|offered|available)|"
                        r"visa sponsorship (?:is )?(?:available|provided|offered)|we (?:will )?sponsor visas?|"
                        r"willing to relocate)\b", re.I)
ARRANGEMENT = re.compile(r"\b(remote|hybrid|distributed|in[- ]office|on[- ]?site|onsite|office|flexible|anywhere|"
                         r"work from home|wfh|multiple locations|various locations|tbd|n/?a|location|locations|"
                         r"global|worldwide|full[- ]time|part[- ]time|first|based|in|or|and|the)\b", re.I)
FOREIGN = re.compile(
    r"\b(united states|usa|u\.s\.a?\.?|us-remote|amer|americas|north america|latam|canada|toronto|vancouver|"
    r"new york|nyc|san francisco|bay area|seattle|california|austin|boston|chicago|denver|atlanta|los angeles|"
    r"united kingdom|uk|london|ireland|dublin|europe|emea|eu|germany|berlin|munich|france|paris|"
    r"netherlands|amsterdam|spain|madrid|barcelona|poland|warsaw|portugal|lisbon|sweden|stockholm|"
    r"switzerland|zurich|italy|austria|vienna|belgium|luxembourg|denmark|norway|finland|czech|romania|"
    r"japan|tokyo|korea|seoul|singapore|australia|sydney|melbourne|new zealand|hong kong|taiwan|taipei|"
    r"malaysia|kuala lumpur|thailand|bangkok|vietnam|indonesia|jakarta|philippines|manila|china|beijing|"
    r"shanghai|brazil|são paulo|sao paulo|mexico|argentina|colombia|chile|israel|tel aviv|uae|dubai|"
    r"saudi|riyadh|qatar|egypt|nigeria|kenya|south africa|pakistan|bangladesh|sri lanka|nepal)\b", re.I)
NOT_ELIGIBLE = re.compile(
    r"\b(?:must|should|need to|required to) (?:be )?(?:currently )?(?:reside|residing|located|based|live|living) "
    r"(?:in|within) (?:the )?(?!india\b)(?:united states|us|u\.s\.|usa|canada|uk|united kingdom|europe|eu|"
    r"[a-z]+ time ?zones?|north america|latam|americas|germany|australia)|"
    r"\b(?:us|u\.s\.|usa|united states|uk|eu|canada|europe)[- ](?:only|based only|residents only)\b|"
    r"\bonly (?:open|available) to (?:candidates|applicants|residents|people) (?:in|of|from|based in) "
    r"(?:the )?(?!india\b)[a-z]+|"
    r"\b(?:legally )?authori[sz]ed to work in (?:the )?(?:us|u\.s\.|united states|uk|eu|canada|europe)\b|"
    r"\b(?:us|u\.s\.) (?:citizenship|citizens? only|work authori[sz]ation) (?:is )?required\b|"
    r"\bwe (?:are )?(?:not|unable to) (?:hire|hiring|consider) (?:candidates )?(?:outside|from outside) (?:the )?"
    r"(?!india\b)[a-z]+", re.I)


def _target_places(target: str) -> set[str]:
    from app.services.job_matching import INDIA_PLACES
    value = " ".join(str(target or "India").split()).casefold()
    if value == "india":
        return set(INDIA_PLACES) | {"india", "blr", "ncr", "delhi ncr"}
    return {value}


def target_country(preferences: dict[str, Any] | None) -> str:
    """Configured target country: ``jobs.target_country``; otherwise India when any preferred place is Indian."""
    jobs = (preferences or {}).get("jobs") or {}
    explicit = str(jobs.get("target_country") or "").strip()
    if explicit:
        return explicit
    india = _target_places("India")
    for place in jobs.get("locations") or []:
        value = " ".join(str(place).split()).casefold()
        if value in {"any", "anywhere", "remote", ""}:
            continue
        if value in india:
            return "India"
        return str(place).strip()
    return "India"


def _names(text: str, places: set[str]) -> str | None:
    lowered = f" {text.casefold()} "
    # "IN-Bengaluru" / "India - Pune" style prefixes
    lowered = re.sub(r"\bin[-_](?=[a-z])", " india ", lowered)
    for place in sorted(places, key=len, reverse=True):
        if re.search(r"(?<![a-z])" + re.escape(place) + r"(?![a-z])", lowered):
            return place
    return None


def classify_geography(*, location: Any = None, remote: Any = None, title: Any = None, text: Any = None,
                       restrictions: list[str] | None = None, target: str = "India",
                       accept_relocation: bool = False) -> dict[str, Any]:
    """Classify where a vacancy can be done from, relative to ``target``, with the evidence used."""
    loc = clean_text(location) or ""
    ttl = clean_title(title) or ""
    body = str(text or "")[:5000]
    places = _target_places(target)
    remote_flag = bool(REMOTE.search(loc)) or "remote" in str(remote or "").casefold() or \
        bool(re.search(r"[(\[]\s*remote\b|\bremote\s*[)\]]|^remote\b", ttl, re.I))

    def out(kind: str, evidence: str, scope: str | None = None) -> dict[str, Any]:
        return {"kind": kind, "label": GEO_LABELS[kind] + (f" ({scope})" if scope else ""), "evidence": evidence,
                "target": target, "eligible": kind in GEO_ELIGIBLE,
                "uncertain": kind in GEO_UNCERTAIN and not (kind == "relocation" and not accept_relocation),
                # Relocation abroad is outside the default preference unless the user opts in (jobs.accept_relocation).
                "excluded": kind in GEO_EXCLUDED or (kind == "relocation" and not accept_relocation)}

    # 1) Structured restrictions from the source (e.g. Himalayas locationRestrictions) are the strongest evidence.
    if restrictions is not None:
        named = [str(item) for item in restrictions if str(item).strip()]
        if not named:
            return out("remote_india", "source lists no location restriction (open worldwide)", "worldwide")
        hit = next((item for item in named if _names(item, places)), None)
        if hit:
            return out("remote_india" if remote_flag or not _names(loc, places) else "india",
                       f"source restricts applicants to: {', '.join(named)[:120]}")
        return out("remote_not_india", f"source restricts applicants to: {', '.join(named)[:120]}")

    denial = NOT_ELIGIBLE.search(body)
    in_loc = _names(loc, places)
    in_title = _names(ttl, places)
    if in_loc:
        if remote_flag and not re.search(r"[;|]", loc):
            return out("remote_india", f"location “{loc[:80]}”")
        return out("india", f"location “{loc[:80]}”")
    residual = re.sub(r"[\s,;/|()\-–:]+", " ", ARRANGEMENT.sub(" ", loc)).strip()
    foreign_loc = FOREIGN.search(loc)
    foreign_title = next((m for m in FOREIGN.finditer(ttl) if m.group(0) != "us"), None)
    if remote_flag:
        if in_title and not foreign_loc:
            return out("remote_india", f"title “{ttl[:80]}”")
        if denial:
            return out("remote_not_india", f"description: “{denial.group(0)[:100]}”")
        eligible = re.search(r"(?:remote|work from home|wfh)[^.\n]{0,80}\b(?:india|indian)\b|"
                             r"\b(?:candidates|applicants|engineers|people) (?:based|located|residing) in india\b|"
                             r"\bopen to (?:candidates|applicants) (?:in|from) india\b", body, re.I)
        if eligible and not foreign_loc:
            return out("remote_india", f"description: “{eligible.group(0)[:100]}”")
        if foreign_loc or foreign_title:
            match = foreign_loc or foreign_title
            return out("remote_not_india", f"remote restricted to “{match.group(0)}”")
        if WORLDWIDE.search(loc) or re.search(r"\b(anywhere in the world|work from anywhere|worldwide)\b", body[:2000], re.I):
            return out("remote_india", f"location “{loc[:80] or 'worldwide'}”", "worldwide")
        if REGION_INCLUDING.search(loc) or REGION_INCLUDING.search(body[:2000]):
            return out("remote_unknown", f"region “{(REGION_INCLUDING.search(loc) or REGION_INCLUDING.search(body[:2000])).group(0)}” "
                       "may include India but does not name it")
        if residual:
            # A place this module does not recognise and that is not in the target country: fail closed.
            return out("remote_not_india", f"remote restricted to “{residual[:60]}”")
        return out("remote_unknown", f"location “{loc[:60] or 'Remote'}” states no country")
    if in_title and not foreign_loc:
        return out("india", f"title “{ttl[:80]}”")
    if foreign_loc or foreign_title or residual:
        place = (foreign_loc or foreign_title).group(0) if (foreign_loc or foreign_title) else residual[:60]
        if RELOCATION.search(body):
            return out("relocation", f"based in “{place}”; {RELOCATION.search(body).group(0)}")
        return out("outside", f"based in “{place}”")
    if WORLDWIDE.search(loc):
        return out("remote_unknown", f"location “{loc[:60]}” (no work arrangement stated)")
    return out("unknown", "no location in the listing")


# ------------------------------------------------------------------ freshness (publication-based only)
PUBLICATION_WINDOWS = [(1, "24h", "Published within 24 hours"), (3, "3d", "Published within 3 days"),
                       (7, "7d", "Published within 7 days"), (14, "14d", "Published within 14 days"),
                       (30, "30d", "Published within 30 days")]


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        day = parse_date(value)
        return datetime(day.year, day.month, day.day, tzinfo=timezone.utc) if day else None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _ago(days: int) -> str:
    return "today" if days <= 0 else "yesterday" if days == 1 else f"{days} days ago"


def publication_freshness(job: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """Freshness from the stated publication date only. first_seen is reported separately, never as a substitute."""
    now = now or datetime.now(timezone.utc)
    today = now.date()
    published = parse_date(job.get("posted_date") or job.get("published_at"))
    confidence = job.get("posting_date_confidence") or date_confidence(job.get("posted_date_source"), published)
    first_seen = _parse_dt(job.get("first_seen") or job.get("first_seen_at"))
    seen_days = (today - first_seen.date()).days if first_seen else None
    discovered = f"First discovered {_ago(seen_days)}" if seen_days is not None else "Discovery time unknown"
    trusted = bool(published) and confidence in {"high", "medium"}
    if published and published > today:
        trusted = False  # a future "publication" date is an extraction error, not evidence
    if not trusted:
        note = "Publication date not disclosed" if not published else \
            f"Unconfirmed date {published.isoformat()} ({job.get('posted_date_source') or 'low-confidence source'})"
        return {"window": "unknown", "window_label": "Publication date unknown", "published_at": None,
                "age_days": None, "label": f"{note} · {discovered}", "first_discovered": discovered,
                "newly_published": False,
                "newly_discovered": seen_days is not None and seen_days <= 1, "date_confidence": confidence}
    age = (today - published).days
    window, window_label = next(((key, label) for limit, key, label in PUBLICATION_WINDOWS if age <= limit),
                                ("older", "Older than 30 days"))
    return {"window": window, "window_label": window_label, "published_at": published.isoformat(), "age_days": age,
            "label": f"Published {_ago(age)}", "first_discovered": discovered, "newly_published": age <= 3,
            "newly_discovered": seen_days is not None and seen_days <= 1, "date_confidence": confidence}


# ------------------------------------------------------------------ vacancy status / verification level
VACANCY_STATUS = {
    "open_employer_verified": "Open — employer verified",
    "open_source_verified": "Open — source verified",
    "possibly_open": "Possibly open — verification pending",
    "closed": "Closed",
    "expired": "Expired",
    "removed": "Removed from source",
    "unknown": "Unknown",
}


def vacancy_status(job: dict[str, Any], lifecycle_state: str) -> str:
    if lifecycle_state == "expired":
        return "expired"
    if lifecycle_state == "closed":
        evidence = str(job.get("status_evidence") or "")
        return "removed" if re.search(r"\bnot (?:on|listed)\b|not found|returned http 404|removed", evidence, re.I) \
            else "closed"
    if lifecycle_state == "open_verified":
        return "open_employer_verified"
    if lifecycle_state == "open_page_checked":
        return "open_source_verified"
    if lifecycle_state in {"open_not_recent", "pending_verification", "unverified", "reposted", "inaccessible",
                           "recheck_pending"}:
        return "possibly_open"
    return "unknown"


def verification_level(status: str) -> str:
    return {"open_employer_verified": "employer", "open_source_verified": "source"}.get(status, "none")


# ------------------------------------------------------------------ the gate
GROUP_LABELS = {
    "verified_strong": "Verified strong matches",
    "verified_good": "Verified good matches",
    "verified_low": "Verified · weaker matches",
    "stretch": "Stretch opportunities",
    "pending": "Verification pending",
    "outside_geography": "Outside geography",
    "not_vacancy": "Not a vacancy",
    "closed": "Closed or expired",
}


def validate(job: dict[str, Any], *, lifecycle_state: str | None = None, preferences: dict[str, Any] | None = None,
             now: datetime | None = None, target: str | None = None) -> dict[str, Any]:
    """Run every validation stage for one listing and decide its result group.

    ``job`` may be a stored row or a discovery candidate. The resume match (eligibility tier) is read from
    ``job['eligibility']['tier']`` when present; it can lower a group but never lift one past a failed stage.
    """
    from app.services.verification import lifecycle as _lifecycle

    target = target or target_country(preferences)
    raw = job.get("raw") or {}
    text = str(job.get("raw_text") or raw.get("raw_text") or "")
    stages: list[dict[str, Any]] = []
    document = classify_document({**job, "raw_text": text})
    stages.append({"stage": "document_classification", "result": document["type"],
                   "passed": document["is_vacancy"], "reason": document["reason"]})
    employer_ok = bool(str(job.get("employer") or "").strip())
    url_ok = bool(job.get("original_url") or job.get("url"))
    stages.append({"stage": "vacancy_validation", "passed": document["is_vacancy"] and url_ok,
                   "result": "single vacancy" if document["is_vacancy"] else document["label"],
                   "reason": None if employer_ok else "Employer not identified (flagged)"})
    fresh = publication_freshness(job, now=now)
    stages.append({"stage": "freshness_validation", "passed": True, "result": fresh["window"], "reason": fresh["label"]})
    restrictions = raw.get("location_restrictions") if isinstance(raw, dict) else None
    if restrictions is None:
        restrictions = job.get("location_restrictions")
    geo = classify_geography(location=job.get("location"), remote=job.get("remote"), title=job.get("title"),
                             text=text, restrictions=restrictions, target=target,
                             accept_relocation=bool(((preferences or {}).get("jobs") or {}).get("accept_relocation")))
    stages.append({"stage": "geography_validation", "passed": not geo["excluded"], "result": geo["kind"],
                   "reason": geo["evidence"]})
    state = lifecycle_state or _lifecycle(job)["state"]
    status = vacancy_status(job, state)
    level = verification_level(status)
    eligibility = job.get("eligibility") or {}
    tier = eligibility.get("tier")
    stages.append({"stage": "eligibility_validation", "passed": tier not in {"ineligible", "excluded"},
                   "result": tier or "not assessed",
                   "reason": "; ".join(eligibility.get("gates") or []) or eligibility.get("excluded_reason")})
    if not document["is_vacancy"]:
        group, reason = "not_vacancy", document["reason"]
    elif status in {"closed", "expired", "removed"}:
        group, reason = "closed", VACANCY_STATUS[status]
    elif geo["excluded"]:
        group, reason = "outside_geography", geo["label"] + " — " + geo["evidence"]
    elif tier in {"excluded"}:
        group, reason = "not_vacancy" if "search page" in str(eligibility.get("excluded_reason") or "").casefold() \
            else "stretch", eligibility.get("excluded_reason") or "Excluded by relevance gate"
    elif tier == "ineligible":
        group, reason = "stretch", "Eligibility gate: " + "; ".join(eligibility.get("gates") or [])[:200]
    elif level == "none" or geo["uncertain"] or not employer_ok:
        why = [] if level != "none" else [VACANCY_STATUS[status]]
        if geo["uncertain"]:
            why.append(geo["label"])
        if not employer_ok:
            why.append("employer not identified")
        group, reason = "pending", "; ".join(why)
    elif tier == "strong":
        group, reason = "verified_strong", "Verified open, in target geography, strong match"
    elif tier == "possible":
        group, reason = "verified_good", "Verified open, in target geography, good match"
    else:
        group, reason = "verified_low", "Verified open, weaker match"
    return {"group": group, "group_label": GROUP_LABELS[group], "reason": reason, "document": document,
            "geography": geo, "freshness": fresh, "vacancy_status": status,
            "vacancy_status_label": VACANCY_STATUS[status], "verification_level": level,
            "employer_identified": employer_ok, "stages": stages}


# ------------------------------------------------------------------ employer-owned pages
AGGREGATOR_HOSTS = ("himalayas.app", "adzuna.", "jooble.", "google.", "serpapi.com", "talent.com", "simplyhired.",
                    "careerjet.", "jobrapido.", "glassdoor.", "ziprecruiter.", "monster.", "hasjob.co",
                    "findwork.dev", "remoteok.com", "aidevboard.com", "artificialintelligencejobs.co")


def employer_owned_url(url: str, employer: str | None) -> bool:
    """True when ``url`` is on the employer's own site (or its public ATS board), not a portal or aggregator."""
    from urllib.parse import urlsplit

    from app.services.job_sources import portals as portal_policy
    from app.services.job_sources.ats_registry import is_ats_listing

    if not url or portal_policy.portal_for(url) is not None:
        return False
    host = (urlsplit(url).hostname or "").casefold().removeprefix("www.")
    if not host or any(marker in host for marker in AGGREGATOR_HOSTS):
        return False
    if is_ats_listing(url):
        return True
    tokens = [t for t in re.split(r"[^a-z0-9]+", str(employer or "").casefold())
              if len(t) >= 4 and t not in {"inc", "corp", "limited", "private", "technologies", "technology", "labs",
                                           "solutions", "systems", "software", "group", "india", "global", "services"}]
    labels = host.split(".")
    return any(token in label for token in tokens for label in labels[:-1])
