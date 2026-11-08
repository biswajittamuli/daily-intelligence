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
