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
