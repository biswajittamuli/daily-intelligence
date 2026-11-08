"""Explainable, deterministic job-to-preference matching."""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.services.freshness import parse_date


STOP = {"the", "and", "for", "with", "from", "that", "this", "job", "role", "hiring",
        "apply", "india", "remote", "full", "time", "level", "entry"}


def terms(value: Any) -> set[str]:
    text = value if isinstance(value, str) else " ".join(map(str, value or []))
    output = set()
    for token in re.findall(r"[a-z0-9+#.]+", text.lower()):
        token = token.strip(".")
        if len(token) < 2 or token in STOP:
            continue
        output.add(token)
    return output


def _experience_years(listing: dict[str, Any]) -> int | None:
    text = " ".join(str(listing.get(key) or "") for key in ("experience", "title", "raw_text"))
    matches = [int(value) for value in re.findall(r"(\d+)\s*(?:\+|-|to)?\s*years?", text, re.I)]
    return min(matches) if matches else None


def score_job(listing: dict[str, Any], preferences: dict[str, Any],
              profile: dict[str, Any] | None = None, today: date | None = None) -> dict[str, Any]:
    """Return a 0-100 score only when there is enough evidence to justify it."""
    today = today or date.today()
    jobs = preferences.get("jobs", {})
    roles = jobs.get("roles") or []
    skills = jobs.get("skills") or []
    profile = profile or {}
    profile_skills = profile.get("skills") or []
    wanted_roles = terms(roles)
    wanted_skills = terms(skills) | terms(profile_skills)

    title_terms = terms(listing.get("title"))
    body_terms = terms(listing.get("skills")) | terms(listing.get("experience")) | terms(listing.get("raw_text"))
    if not title_terms and not body_terms:
        return {"score": None, "confidence": "insufficient_evidence",
                "reasons": ["No title or requirement text was extracted; match cannot be scored."],
                "reasons_text": "Needs review — insufficient evidence to score."}

    score = 0
    reasons: list[str] = []
    max_score = 0

    max_score += 30
    role_hits = wanted_roles & (title_terms | body_terms)
    if role_hits:
        score += 30
        reasons.append(f"Role match: {', '.join(sorted(role_hits)[:4])}.")
    elif wanted_roles:
        reasons.append("Role not explicitly matched in the listing title or requirements.")

    max_score += 25
    skill_hits = wanted_skills & (title_terms | body_terms)
    if skill_hits:
        score += min(25, 6 + 4 * len(skill_hits))
        reasons.append(f"Skill overlap: {', '.join(sorted(skill_hits)[:5])}.")
    elif wanted_skills:
        reasons.append("Preferred skills were not found in the extracted text.")

    max_score += 15
    years = _experience_years(listing)
    preference_experience = str(jobs.get("experience") or "any").casefold()
    fresher_wanted = preference_experience in {"fresher", "internship", "0-1 years", "0-1", "entry"}
    if years is not None:
        if fresher_wanted and years <= 1:
            score += 15
            reasons.append(f"Experience fits entry-level preference ({years} year minimum).")
        elif years <= 2:
            score += 10
            reasons.append(f"Junior-compatible experience requirement ({years} years).")
        else:
            reasons.append(f"Requires about {years} years of experience.")
    elif fresher_wanted:
        reasons.append("No explicit experience requirement was extracted; verify eligibility.")

    max_score += 15
    locations = jobs.get("locations") or []
    listing_location = str(listing.get("location") or "")
    remote_pref = str(jobs.get("remote") or "any")
    listing_remote = str(listing.get("remote") or "").casefold()
    if locations and any(term in listing_location.casefold() for term in
                         [loc.casefold() for loc in locations]):
        score += 15
        reasons.append("Location preference matches.")
    elif remote_pref == "remote" and "remote" in listing_remote:
        score += 15
        reasons.append("Remote preference matches.")
    elif not locations and remote_pref == "any":
        score += 8
        reasons.append("No location restriction configured.")

    max_score += 10
    employment = jobs.get("employment_types") or []
    listing_type = str(listing.get("employment_type") or "")
    if employment and any(item.casefold() in listing_type.casefold() for item in employment):
        score += 10
        reasons.append("Employment type matches.")
    elif not employment:
        score += 5

    max_score += 5
    published = parse_date(listing.get("posted_date"))
    if published:
        age = (today - published).days
        if age <= 7:
            score += 5
            reasons.append("Posted within the last week.")
        elif age <= 30:
            score += 3
            reasons.append("Posted within the last month.")
        else:
            reasons.append(f"Posting is {age} days old.")

    percent = round(100 * score / max_score) if max_score else None
    confidence = "high" if percent and percent >= 70 else "medium" if percent and percent >= 45 else "low"
    return {
        "score": percent,
        "confidence": confidence,
        "reasons": reasons,
        "reasons_text": " ".join(reasons) if reasons else "Limited evidence available.",
    }


def _skill_set(values: Any) -> set[str]:
    if isinstance(values, str):
        values = [values]
    return {" ".join(str(item).split()).casefold() for item in values or [] if str(item).strip()}


def resume_fit(listing: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """Explainable resume-vs-listing fit, independent of search preferences.

    Skill coverage (60%): share of the listing's skills the resume names.
    Title overlap (30%): listing title terms found in resume skills/keywords/projects.
    Experience (10%): resume years vs. the listing's stated minimum.
    Returns matched/missing skills for tailoring hints.
    """
    profile = profile or {}
    resume_skills = _skill_set(profile.get("skills")) | _skill_set(profile.get("frameworks")) \
        | _skill_set(profile.get("languages")) | _skill_set(profile.get("keywords"))
    resume_terms = terms(list(resume_skills)) | terms(profile.get("projects")) | terms(profile.get("keywords"))
    listing_skills = list(dict.fromkeys(str(item) for item in listing.get("skills") or [] if str(item).strip()))
    matched = [skill for skill in listing_skills
               if skill.casefold() in resume_skills or terms(skill) <= resume_terms]
    missing = [skill for skill in listing_skills if skill not in matched]

    coverage = (len(matched) / len(listing_skills)) if listing_skills else None
    title_terms = terms(listing.get("title")) - {"senior", "junior", "lead", "intern", "engineer",
                                                  "developer", "jobs", "job", "india", "remote"}
    title_overlap = (len(title_terms & resume_terms) / len(title_terms)) if title_terms else None
    years_needed = _experience_years(listing)
    try:
        years_have = int(profile.get("experience_years") or 0)
    except (TypeError, ValueError):
        years_have = 0
    experience = None if years_needed is None else (1.0 if years_have >= years_needed
                                                    else max(0.0, 1 - (years_needed - years_have) / 4))
    parts = [(coverage, 60), (title_overlap, 30), (experience, 10)]
    weight = sum(w for value, w in parts if value is not None)
    if not weight:
        return {"score": None, "matched": [], "missing": [], "evidence": "insufficient"}
    score = round(sum((value or 0) * w for value, w in parts if value is not None) / weight * 100)
    return {"score": score, "matched": matched[:12], "missing": missing[:12],
            "evidence": "skills" if coverage is not None else "title"}


def best_resume_match(listing: dict[str, Any], preferences: dict[str, Any],
                      resumes: list[dict[str, Any]], today: date | None = None) -> dict[str, Any]:
    """Score a listing against every stored resume and pick the best one.

    The overall match score blends preference fit (score_job with that resume) and
    the resume's own fit, so the chosen resume is the one that best evidences the role.
    """
    if not resumes:
        result = score_job(listing, preferences, None, today)
        return {"match_score": result["score"], "match_reason": result["reasons_text"],
                "best_resume_id": None, "best_resume_label": None, "resume_scores": []}
    scored = []
    for resume in resumes:
        profile = resume.get("profile") or {}
        base = score_job(listing, preferences, profile, today)
        fit = resume_fit(listing, profile)
        values = [value for value in (base["score"], fit["score"]) if value is not None]
        combined = round(sum(values) / len(values)) if values else None
        scored.append({
            "resume_id": resume.get("id"), "label": resume.get("label") or resume.get("filename"),
            "score": combined, "fit": fit["score"], "matched": fit["matched"],
            "missing": fit["missing"], "reasons": base["reasons_text"],
            "is_default": bool(resume.get("is_default")),
        })
    scored.sort(key=lambda item: (item["score"] is not None, item["score"] or 0, item["is_default"]),
                reverse=True)
    best = scored[0]
    reason = best["reasons"]
    if best["matched"]:
        reason += f" Resume covers: {', '.join(best['matched'][:5])}."
    if best["missing"]:
        reason += f" Missing: {', '.join(best['missing'][:4])}."
    return {"match_score": best["score"], "match_reason": reason.strip(),
            "best_resume_id": best["resume_id"], "best_resume_label": best["label"],
            "resume_scores": [{key: item[key] for key in ("resume_id", "label", "score", "fit",
                                                          "matched", "missing")} for item in scored]}


# --------------------------------------------------------------------------
# V3.1: active-resume ranking with explicit eligibility and relevance checks
# --------------------------------------------------------------------------
import re as _re

NON_TECH_TITLE = _re.compile(
    r"\b(sales|account (executive|manager|director)|business development|bdr|sdr|marketing|"
    r"recruit\w*|talent acquisition|legal|counsel|paralegal|attorney|financ\w*|accountant|"
    r"accounting|audit\w*|tax|payroll|hr|human resources|people (partner|operations)|"
    r"customer success|customer support|support specialist|office manager|executive assistant|"
    r"facilities|procurement|compliance|risk analyst|copywriter|content writer|brand|"
    r"public relations|communications manager|events?|partnerships?|growth marketing|"
    r"collections|underwriter|merchandis\w*|store|warehouse|driver|nurse|teacher|gtm|go-to-market|"
    r"strategy|strategic|operations|ops manager|program manager|product marketing|designer)\b", _re.I)
TECH_TITLE = _re.compile(
    r"\b(engineer\w*|developer|programmer|sde|swe|scientist|data|ml|ai|machine learning|"
    r"devops|sre|platform|backend|back-end|frontend|front-end|full[- ]?stack|software|"
    r"analyst|architect|security|qa|test|automation|cloud|infrastructure|mobile|android|ios|"
    r"research|intern(ship)?|graduate|trainee|fresher)\b", _re.I)
STRONG_TECH = _re.compile(r"\b(engineer\w*|developer|programmer|scientist|sde|swe|devops|sre)\b", _re.I)
SENIOR_HARD = _re.compile(r"\b(senior|sr\.?|staff|principal|distinguished|director|head of|vp|"
                          r"vice president|chief|manager|lead\b(?! to)|tech lead)\b", _re.I)
SENIOR_SOFT = _re.compile(r"\b(architect|ii|iii|iv|level 3|l4|l5)\b", _re.I)
YEARS_REQUIRED = _re.compile(
    r"(?:minimum|min\.?|at least|over|more than)?\s*(\d{1,2})\s*(?:\+|plus)?\s*(?:-\s*\d{1,2}\s*)?"
    r"(?:years?|yrs?)\s*(?:of)?\s*(?:\w+\s){0,3}?(?:experience|exp\b)", _re.I)
INDIA_PLACES = {
    "india", "bengaluru", "bangalore", "karnataka", "mysore", "mysuru", "hyderabad", "telangana",
    "pune", "mumbai", "navi mumbai", "thane", "maharashtra", "nagpur", "delhi", "new delhi", "ncr",
    "gurgaon", "gurugram", "haryana", "sonipat", "noida", "greater noida", "uttar pradesh", "lucknow",
    "aligarh", "deoria", "chennai", "tamil nadu", "coimbatore", "kolkata", "west bengal", "ahmedabad",
    "gujarat", "surat", "vadodara", "kochi", "cochin", "kerala", "trivandrum", "thiruvananthapuram",
    "jaipur", "rajasthan", "chandigarh", "punjab", "ludhiana", "mohali", "indore", "madhya pradesh",
    "bhopal", "guwahati", "assam", "dibrugarh", "bhubaneswar", "odisha", "patna", "bihar",
    "visakhapatnam", "vizag", "andhra pradesh", "goa",
}
PLACE_ALIASES = [{"bengaluru", "bangalore"}, {"gurgaon", "gurugram"}, {"mumbai", "bombay"},
                 {"chennai", "madras"}, {"kolkata", "calcutta"}, {"kochi", "cochin"},
                 {"delhi", "new delhi", "ncr"}]
FOREIGN_PLACES = _re.compile(
    r"\b(united states|usa|us|u\.s\.|us-remote|amer|americas|north america|latam|canada|toronto|vancouver|"
    r"new york|nyc|san francisco|seattle|california|austin|boston|chicago|denver|atlanta|"
    r"united kingdom|uk|london|ireland|dublin|europe|emea|eu|germany|berlin|munich|france|paris|"
    r"netherlands|amsterdam|spain|madrid|barcelona|poland|portugal|lisbon|sweden|stockholm|"
    r"switzerland|zurich|italy|japan|tokyo|korea|seoul|singapore|australia|sydney|melbourne|"
    r"brazil|são paulo|sao paulo|mexico|israel|tel aviv|uae|dubai|china|beijing|shanghai|"
    r"philippines|vietnam|indonesia)\b", _re.I)
REMOTE_WORDS = _re.compile(r"\b(remote|anywhere|worldwide|global|distributed|work from home|wfh)\b", _re.I)


def _expand_places(preferences: list[str]) -> set[str]:
    places: set[str] = set()
    for item in preferences:
        value = " ".join(str(item).split()).casefold()
        if not value:
            continue
        places.add(value)
        if value == "india":
            places |= INDIA_PLACES
        for group in PLACE_ALIASES:
            if value in group:
                places |= group
    return places


def location_fit(location: str, remote: str, preferred: list[str]) -> tuple[bool | None, str | None]:
    """(fits, exclusion reason). None when no location preference or no location stated."""
    places = _expand_places(preferred)
    if not places:
        return None, None
    lowered = " ".join(str(location or "").split()).casefold()
    remote_flag = bool(REMOTE_WORDS.search(lowered)) or "remote" in str(remote or "").casefold()
    if not lowered:
        return (True if remote_flag else None), None
    if any(_re.search(r"(?<![a-z])" + _re.escape(place) + r"(?![a-z])", lowered) for place in places):
        return True, None
    if remote_flag:
        if FOREIGN_PLACES.search(lowered):
            return False, "Remote role restricted to another country or region"
        return True, None
    return False, "Outside your preferred locations"


REMOTE_RESTRICTED = _re.compile(r"\b(remote|anywhere)\b[^,;]*\b(us|usa|united states|canada|uk|"
                                r"united kingdom|europe|emea|eu|germany|latam|americas|apac)\b", _re.I)

ROLE_TITLE_HINTS: list[tuple[str, set[str]]] = [
    ("AI Engineer", {"pytorch", "tensorflow", "rag", "llm", "llms", "transformers", "deep learning",
                     "machine learning", "langchain", "nlp", "computer vision", "vector indexing & search",
                     "generative ai", "agentic ai", "mcp"}),
    ("Machine Learning Engineer", {"pytorch", "tensorflow", "scikit-learn", "machine learning",
                                   "deep learning", "mlops"}),
    ("Backend Developer", {"fastapi", "django", "flask", "spring", "spring boot", "node.js", "postgresql",
                           "mysql", "redis", "kafka", "rest", "rest apis", "microservices", "mongodb"}),
    ("Full Stack Developer", {"react", "next.js", "node.js", "typescript", "javascript"}),
    ("Frontend Developer", {"react", "angular", "vue", "html5", "css3", "html", "css", "typescript"}),
    ("Data Engineer", {"spark", "airflow", "kafka", "snowflake", "databricks", "dbt", "bigquery"}),
    ("Data Analyst", {"sql", "tableau", "power bi", "excel", "pandas", "statistics"}),
    ("DevOps Engineer", {"docker", "kubernetes", "terraform", "ci/cd", "ci/cd pipelines", "aws", "ansible"}),
    ("Software Engineer", {"data structures & algorithms", "data structures", "algorithms", "dsa",
                           "system design", "java", "c++", "python", "object-oriented design"}),
]


def infer_job_titles(profile: dict[str, Any], limit: int = 4) -> list[str]:
    """Deterministically infer target job titles from a resume profile's skills."""
    explicit = [str(item).strip() for item in profile.get("job_titles") or [] if str(item).strip()]
    skills = {str(item).casefold() for key in ("skills", "frameworks", "languages", "keywords")
              for item in profile.get(key) or []}
    scored = []
    for title, hints in ROLE_TITLE_HINTS:
        hits = len(skills & hints)
        if hits:
            scored.append((hits, title))
    scored.sort(reverse=True)
    inferred = [title for hits, title in scored if hits >= 2] or [title for _, title in scored[:2]]
    output: list[str] = []
    for title in explicit + inferred:
        if title.casefold() not in {item.casefold() for item in output}:
            output.append(title)
    return output[:limit] or ["Software Engineer"]


def _required_years(text: str) -> int | None:
    values = [int(match.group(1)) for match in YEARS_REQUIRED.finditer(text[:6000])]
    values = [value for value in values if 0 < value <= 20]
    return min(values) if values else None


def rank_listing(listing: dict[str, Any], profile: dict[str, Any] | None,
                 preferences: dict[str, Any], *, targets: list[str] | None = None,
                 today: date | None = None) -> dict[str, Any]:
    """Score one listing against the ACTIVE resume profile (or preferences when none).

    Returns score (0-100), tier (strong/possible/low/excluded), reasons, warnings,
    excluded_reason, matched and missing skills. Deterministic and explainable.
    """
    today = today or date.today()
    profile = profile or {}
    jobs_pref = preferences.get("jobs", {})
    title = str(listing.get("title") or "")
    body = " ".join(str(listing.get(key) or "") for key in ("raw_text", "description", "experience"))
    if not body.strip() and isinstance(listing.get("raw"), dict):
        body = str(listing["raw"].get("raw_text") or "")
    years_have = int(profile.get("experience_years") or 0) if str(profile.get("experience_years") or "0").isdigit() else 0
    experience_pref = str(jobs_pref.get("experience") or "any").casefold()
    fresher = years_have <= 1 or experience_pref in {"fresher", "internship", "0-1 years"}
    reasons: list[str] = []
    warnings: list[str] = []
    excluded = None

    from app.services.listing_links import is_listing_url, looks_like_index
    url = str(listing.get("original_url") or listing.get("url") or "")
    if (looks_like_index(url, title) and not is_listing_url(url)) or _re.search(
            r"^\s*[\d,]+\+?\s+.*\bjobs\b", title, _re.I):
        excluded = "Job search page, not a single vacancy"
    elif NON_TECH_TITLE.search(title) and not STRONG_TECH.search(title):
        excluded = "Not a technical role for your profile"
    elif fresher and SENIOR_HARD.search(title) and not _re.search(r"\bintern|graduate|trainee|junior\b", title, _re.I):
        excluded = "Seniority too high for your experience"

    required = _required_years(body) if not excluded else None
    if required is not None and not excluded:
        if required > years_have + 2:
            excluded = "Requires more experience than you have"
            warnings.append(f"Asks for {required}+ years of experience; you have {years_have}.")
        elif required > years_have:
            warnings.append(f"Asks for {required} years of experience; you have {years_have}.")
    if not excluded and fresher and SENIOR_SOFT.search(title):
        warnings.append("Title suggests a mid-level role; check the experience requirement.")

    location = str(listing.get("location") or "")
    remote = str(listing.get("remote") or "").casefold()
    locations = [str(item) for item in jobs_pref.get("locations") or [] if str(item).strip()]
    location_ok, location_reason = location_fit(location, remote, locations)
    if location_ok is False and not excluded:
        excluded = location_reason
    elif location_ok is None and locations and not location:
        warnings.append("Location not stated; check it on the listing.")

    # Role relevance against target titles (from active resume + preferences + request).
    target_titles = list(targets or []) + list(jobs_pref.get("roles") or []) + infer_job_titles(profile)
    target_terms = terms(target_titles) - {"engineer", "developer", "senior", "junior"}
    title_terms = terms(title)
    role_hits = target_terms & title_terms
    from app.services.insights import role_family
    listing_family = role_family(title)
    family_match = listing_family != "Other" and listing_family in {role_family(item) for item in target_titles}
    role_score = 1.0 if role_hits or family_match else (0.4 if TECH_TITLE.search(title) else 0.0)
    if role_hits:
        reasons.append(f"Title matches your target roles ({', '.join(sorted(role_hits)[:3])}).")
    elif family_match:
        reasons.append(f"Same role family as your targets ({listing_family}).")
    elif not excluded and not TECH_TITLE.search(title):
        excluded = "Role does not match your target roles"

    fit = resume_fit({**listing, "skills": listing.get("skills") or []}, profile) if profile else \
        {"score": None, "matched": [], "missing": []}
    display = {" ".join(str(item).split()).casefold(): " ".join(str(item).split())
               for key in ("skills", "frameworks", "languages") for item in profile.get(key) or []}
    resume_skills = set(display)
    if not (listing.get("skills") or []) and body and resume_skills:
        lowered_body = body.casefold()
        mentioned = [skill for skill in resume_skills
                     if len(skill) > 2 and _re.search(r"(?<![a-z0-9])" + _re.escape(skill) + r"(?![a-z0-9])", lowered_body)]
        skill_score = min(1.0, len(mentioned) / 5)
        matched = sorted(display[skill] for skill in mentioned)[:8]
        missing: list[str] = []
    else:
        listing_skills = listing.get("skills") or []
        skill_score = (len(fit["matched"]) / max(4, len(listing_skills))) if listing_skills else 0.3
        matched, missing = fit["matched"], fit["missing"]
    if matched:
        reasons.append(f"Your resume covers {', '.join(matched[:5])}.")
    if missing:
        warnings.append(f"Not on your resume: {', '.join(missing[:4])}.")

    experience_score = 1.0 if required is None or required <= years_have else (0.5 if required <= years_have + 2 else 0)
    if required is not None and required <= years_have:
        reasons.append(f"Experience requirement ({required} yrs) fits.")
    location_score = 1.0 if location_ok or not locations else 0.5 if location_ok is None else 0.0
    if location_ok:
        reasons.append(f"Location fits ({location}).")
    employment = [str(item).casefold() for item in jobs_pref.get("employment_types") or []]
    employment_score = 1.0 if not employment or any(item in str(listing.get("employment_type") or "").casefold()
                                                     for item in employment) else 0.5
    posted = parse_date(listing.get("posted_date"))
    age = (today - posted).days if posted else None
    freshness_score = 0.4 if age is None else (1.0 if age <= 7 else 0.8 if age <= 21 else 0.5 if age <= 45 else 0.1)
    if age is not None and age <= 7:
        reasons.append("Posted this week.")
    elif age is not None and age > 45:
        warnings.append(f"Posted {age} days ago; it may be filled.")

    score = round(100 * (0.30 * role_score + 0.30 * skill_score + 0.15 * experience_score
                         + 0.10 * location_score + 0.05 * employment_score + 0.10 * freshness_score))
    if excluded:
        tier = "excluded"
    elif score >= 70:
        tier = "strong"
    elif score >= 50:
        tier = "possible"
    else:
        tier = "low"
    return {"score": score, "tier": tier, "reasons": reasons, "warnings": warnings,
            "excluded_reason": excluded, "matched": matched[:10], "missing": missing[:10],
            "required_years": required}


def active_resume_match(listing: dict[str, Any], preferences: dict[str, Any],
                        resumes: list[dict[str, Any]], *, targets: list[str] | None = None,
                        today: date | None = None) -> dict[str, Any]:
    """Rank against the active resume; record other resumes' scores for comparison."""
    usable = [resume for resume in resumes if resume.get("status", "processed") == "processed"]
    active = next((resume for resume in usable if resume.get("is_default")), None)
    result = rank_listing(listing, (active or {}).get("profile"), preferences, targets=targets, today=today)
    others = []
    for resume in usable:
        if active and resume.get("id") == active.get("id"):
            continue
        other = rank_listing(listing, resume.get("profile"), preferences, targets=targets, today=today)
        others.append({"resume_id": resume.get("id"), "label": resume.get("label"), "score": other["score"],
                       "tier": other["tier"]})
    reason = " ".join(result["reasons"]) or "Limited evidence; open the listing to review."
    if result["excluded_reason"]:
        reason = f"Excluded: {result['excluded_reason']}. " + reason
    return {
        "match_score": None if result["tier"] == "excluded" else result["score"],
        "match_reason": reason.strip(),
        "best_resume_id": (active or {}).get("id"),
        "best_resume_label": (active or {}).get("label"),
        "resume_scores": ([{"resume_id": (active or {}).get("id"), "label": (active or {}).get("label"),
                            "score": result["score"], "tier": result["tier"],
                            "matched": result["matched"], "missing": result["missing"], "active": True}]
                          if active else []) + others,
        "eligibility": {"tier": result["tier"], "warnings": result["warnings"],
                        "excluded_reason": result["excluded_reason"],
                        "required_years": result["required_years"],
                        "resume": (active or {}).get("label")},
    }
