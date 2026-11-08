"""Explainable job assessment in four independent dimensions.

1. Profile match (0-100): configurable weighted components, computed only from evidence.
2. Eligibility gate: eligible / uncertain / not_eligible, from hard requirements
   (experience, degree, graduation batch, work authorization, location, deadline, seniority).
3. Freshness: new / fresh / recent / aging / stale / unknown (posting age).
4. Evidence confidence (0-100): how much of the listing could actually be read and verified.

Every requirement is classified satisfied / not_satisfied / partial / unknown / not_applicable
with the sentence it came from. Skills are compared on canonical names only: a skill counts
as *satisfied* when the resume lists it explicitly, *partial* when it only appears in project
or keyword text, and is never inferred from a different skill.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.services.freshness import parse_date
from app.services.requirements import DEGREE_RANK, DEGREES, extract_requirements
from app.services.skills_taxonomy import canonical, canonical_set, detect_skills

DEFAULT_WEIGHTS = {"role": 20, "mandatory_skills": 25, "preferred_skills": 15, "experience": 15,
                   "education": 10, "location_employment": 10, "freshness": 5}

SENIOR_TITLE = re.compile(r"\b(senior|sr\.?|staff|principal|distinguished|director|head of|vp|vice president|chief|"
                          r"manager|lead\b(?! to)|tech lead|architect)\b", re.I)
JUNIOR_TITLE = re.compile(r"\b(intern(ship)?|graduate|trainee|junior|jr\.?|associate|entry|fresher|new grad|apprentice)\b",
                          re.I)
MID_TITLE = re.compile(r"\b(ii|iii|iv|sde\s?2|sde\s?3|sde-?2|sde-?3|l4|l5|level [345])\b", re.I)


def _freshness(posted: Any, today: date) -> dict[str, Any]:
    value = parse_date(posted)
    if value is None:
        return {"label": "unknown", "age_days": None, "factor": 0.85, "score": 0.4}
    age = (today - value).days
    for limit, label, factor, score in ((3, "new", 1.0, 1.0), (14, "fresh", 0.97, 0.9), (30, "recent", 0.93, 0.75),
                                        (60, "aging", 0.8, 0.4)):
        if age <= limit:
            return {"label": label, "age_days": max(age, 0), "factor": factor, "score": score}
    return {"label": "stale", "age_days": age, "factor": 0.6, "score": 0.1}


def candidate_from_profile(profile: dict[str, Any] | None, preferences: dict[str, Any]) -> dict[str, Any]:
    profile = profile or {}
    explicit_raw = [item for key in ("skills", "languages", "frameworks") for item in profile.get(key) or []]
    explicit = canonical_set(explicit_raw)
    context_text = " ".join(str(item) for key in ("projects", "keywords", "certifications")
                            for item in profile.get(key) or [])
    inferred = canonical_set(detect_skills(context_text)) - explicit
    degree_rank, degree_name, field_cs = 0, None, False
    for line in profile.get("education") or []:
        for name, pattern in DEGREES:
            if pattern.search(str(line)) and DEGREE_RANK[name] > degree_rank:
                degree_rank, degree_name = DEGREE_RANK[name], name
        if re.search(r"computer|cse|information technology|software|\bcs\b|\bit\b", str(line), re.I):
            field_cs = True
    try:
        years = float(profile.get("experience_years") or 0)
    except (TypeError, ValueError):
        years = 0.0
    try:
        grad = int(profile.get("graduation_year")) if profile.get("graduation_year") else None
    except (TypeError, ValueError):
        grad = None
    jobs = preferences.get("jobs", {})
    return {"explicit": explicit, "inferred": inferred, "years": years, "degree_rank": degree_rank,
            "degree": degree_name, "field_cs": field_cs, "graduation_year": grad,
            "has_profile": bool(explicit), "skill_count": len(explicit),
            "authorization": [str(item).casefold() for item in jobs.get("work_authorization") or ["India"]],
            "titles": [str(item) for item in profile.get("job_titles") or []]}


def _skill_status(skill: str, candidate: dict[str, Any]) -> str:
    key = canonical(skill).casefold()
    if key in candidate["explicit"]:
        return "satisfied"
    if key in candidate["inferred"]:
        return "partial"
    return "not_satisfied" if candidate["has_profile"] else "unknown"


def assess(listing: dict[str, Any], profile: dict[str, Any] | None, preferences: dict[str, Any], *,
           role_score: float, role_reason: str, location_ok: bool | None, location_reason: str | None,
           today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    title = str(listing.get("title") or "")
    text = str(listing.get("raw_text") or listing.get("description") or "")
    reqs = listing.get("_requirements") or extract_requirements(text, title=title, today=today)
    candidate = candidate_from_profile(profile, preferences)
    weights = {**DEFAULT_WEIGHTS, **((preferences.get("scoring") or {}).get("weights") or {})}
    requirements: list[dict[str, Any]] = []
    gates: list[str] = []
    warnings: list[str] = []

    def add(kind, name, priority, status, evidence=None, detail=None):
        requirements.append({"type": kind, "name": name, "priority": priority, "status": status,
                             "evidence": evidence, "detail": detail})

    # --- skills
    def skill_block(items: list[dict[str, Any]], priority: str) -> tuple[float, int, list[str], list[str], list[str]]:
        score, missing, matched, partial = 0.0, [], [], []
        for item in items:
            status = _skill_status(item["name"], candidate)
            add("skill", item["name"], priority, status, item.get("evidence"),
                "inferred from your projects, not listed as a skill" if status == "partial" else None)
            if status == "satisfied":
                score += 1
                matched.append(item["name"])
            elif status == "partial":
                score += 0.5
                partial.append(item["name"])
            elif status == "not_satisfied":
                missing.append(item["name"])
        return score, len(items), matched, partial, missing

    m_score, m_total, m_matched, m_partial, m_missing = skill_block(reqs["mandatory_skills"], "mandatory")
    l_score, l_total, l_matched, l_partial, l_missing = skill_block(reqs["listed_skills"], "listed")
    p_score, p_total, p_matched, p_partial, p_missing = skill_block(reqs["preferred_skills"], "preferred")
    # "listed" = priority not stated: counts toward mandatory with half weight.
    mandatory_den = m_total + 0.5 * l_total
    mandatory_cov = ((m_score + 0.5 * l_score) / mandatory_den) if mandatory_den else None
    preferred_cov = (p_score / p_total) if p_total else None

    # --- experience
    exp_min, exp_max = reqs.get("experience_min"), reqs.get("experience_max")
    years = candidate["years"]
    experience_cov = None
    if exp_min is None:
        add("experience", "Minimum experience", None, "unknown", None, "not stated")
    elif years >= exp_min:
        experience_cov = 1.0
        add("experience", f"{exp_min}+ years", reqs.get("experience_priority"), "satisfied",
            reqs.get("experience_evidence"), f"you have {years:g}")
    else:
        gap = exp_min - years
        experience_cov = max(0.0, 1 - gap / 3)
        status = "not_satisfied"
        add("experience", f"{exp_min}+ years", reqs.get("experience_priority"), status,
            reqs.get("experience_evidence"), f"you have {years:g}; short by {gap:g}")
        if reqs.get("experience_priority") == "mandatory":
            gates.append(f"Experience: requires {exp_min}+ years, you have {years:g}")
        else:
            warnings.append(f"Prefers {exp_min}+ years of experience; you have {years:g}.")
    fresher = years <= 1
    if fresher and SENIOR_TITLE.search(title) and not JUNIOR_TITLE.search(title):
        gates.append("Seniority: the title is a senior/lead role")
        add("seniority", title, "mandatory", "not_satisfied", None, "senior title for an early-career profile")
    elif fresher and MID_TITLE.search(title) and (exp_min is None):
        warnings.append("Title suggests a mid-level role and no experience range is stated.")

    # --- education
    education_cov = None
    for edu in reqs.get("education") or []:
        need = DEGREE_RANK.get(edu["degree"], 0)
        if not candidate["degree_rank"]:
            status = "unknown"
        elif candidate["degree_rank"] >= need:
            status = "satisfied"
        else:
            status = "not_satisfied"
        if status == "satisfied" and edu.get("field_cs") and not candidate["field_cs"]:
            status = "partial"
        detail = f"you have {candidate['degree'] or 'no degree recorded'}"
        if status == "satisfied" and candidate["graduation_year"] and candidate["graduation_year"] >= today.year:
            detail += f" (expected {candidate['graduation_year']})"
        add("education", edu["degree"] + (" (CS/IT or related)" if edu.get("field_cs") else ""), edu["priority"],
            status, edu.get("evidence"), detail)
        value = {"satisfied": 1.0, "partial": 0.6, "not_satisfied": 0.0}.get(status)
        if value is not None:
            education_cov = value if education_cov is None else min(education_cov, value)
        if status == "not_satisfied" and edu["priority"] == "mandatory":
            gates.append(f"Education: requires {edu['degree']}, you have {candidate['degree'] or 'none recorded'}")
    if not reqs.get("education"):
        add("education", "Degree", None, "unknown", None, "not stated")

    # --- graduation batch
    if reqs.get("batches"):
        grad = candidate["graduation_year"]
        if grad is None:
            add("batch", "/".join(map(str, reqs["batches"])) + " batch", "mandatory", "unknown")
        elif grad in reqs["batches"]:
            add("batch", "/".join(map(str, reqs["batches"])) + " batch", "mandatory", "satisfied", None, f"you: {grad}")
        else:
            add("batch", "/".join(map(str, reqs["batches"])) + " batch", "mandatory", "not_satisfied", None, f"you: {grad}")
            gates.append(f"Graduation batch: open to {', '.join(map(str, reqs['batches']))}; yours is {grad}")

    # --- work authorization
    for auth in reqs.get("work_authorization") or []:
        country = (auth.get("country") or "").casefold()
        if country and country in candidate["authorization"]:
            add("authorization", auth["requirement"], "mandatory", "satisfied")
        elif country or "sponsorship" in auth["requirement"].casefold() or "citizen" in auth["requirement"].casefold():
            add("authorization", auth["requirement"], "mandatory", "not_satisfied")
            gates.append(f"Work authorization: {auth['requirement']}")
        else:
            add("authorization", auth["requirement"], "mandatory", "unknown")

    # --- location / employment
    if location_ok is False:
        add("location", listing.get("location") or "Location", "mandatory", "not_satisfied", None, location_reason)
        gates.append(location_reason or "Location outside your preferences")
    elif location_ok is True:
        add("location", listing.get("location") or "Location", "mandatory", "satisfied")
    else:
        add("location", "Location", None, "unknown", None, "not stated")
    employment_wanted = [str(item).casefold() for item in preferences.get("jobs", {}).get("employment_types") or []]
    employment = str(listing.get("employment_type") or reqs.get("employment_type") or "")
    if employment_wanted and employment:
        emp_ok = any(item in employment.casefold() for item in employment_wanted)
        add("employment", employment, "preferred", "satisfied" if emp_ok else "not_satisfied")
    else:
        emp_ok = None
    loc_emp_cov = None
    if location_ok is not None or emp_ok is not None:
        parts = [1.0 if location_ok else 0.0] if location_ok is not None else []
        if emp_ok is not None:
            parts.append(1.0 if emp_ok else 0.3)
        loc_emp_cov = sum(parts) / len(parts)

    # --- deadline
    deadline = parse_date(listing.get("deadline") or reqs.get("deadline"))
    if deadline:
        if deadline < today:
            add("deadline", deadline.isoformat(), "mandatory", "not_satisfied", None, "deadline has passed")
            gates.append(f"Deadline passed ({deadline.isoformat()})")
        else:
            add("deadline", deadline.isoformat(), "mandatory", "satisfied", None, f"{(deadline - today).days} days left")

    freshness = _freshness(listing.get("posted_date"), today)

    # --- profile match: weighted mean over components that have evidence
    components = {"role": role_score, "mandatory_skills": mandatory_cov, "preferred_skills": preferred_cov,
                  "experience": experience_cov, "education": education_cov,
                  "location_employment": loc_emp_cov, "freshness": freshness["score"]}
    used = {key: value for key, value in components.items() if value is not None and weights.get(key, 0) > 0}
    weight_sum = sum(weights[key] for key in used)
    match = round(100 * sum(weights[key] * value for key, value in used.items()) / weight_sum) if weight_sum else 0
    if mandatory_cov is None:
        match = min(match, 69)  # never "strong" without readable requirements
    breakdown = [{"component": key, "weight": weights.get(key, 0),
                  "value": None if value is None else round(value * 100)} for key, value in components.items()]

    # --- eligibility gate
    unknowns = [r for r in requirements if r["status"] == "unknown" and r["type"] in {"experience", "education", "location"}]
    if gates:
        eligibility = "not_eligible"
    elif len(unknowns) >= 2 or (exp_min is None and not reqs.get("fresher_friendly") and not JUNIOR_TITLE.search(title)):
        eligibility = "uncertain"
    else:
        eligibility = "eligible"

    # --- evidence confidence
    confidence = 100
    notes = []
    for condition, penalty, note in (
            (len(text) < 800, 25, "short or truncated description"),
            (not reqs.get("structured"), 15, "no requirements section found"),
            (not listing.get("posted_date"), 15, "posting date not stated"),
            (not listing.get("employer"), 10, "employer not stated"),
            (not listing.get("location"), 10, "location not stated"),
            (listing.get("source_kind") in {"harvested"} or listing.get("discovered_via") in {"web search", "index page"}, 10,
             "found via search/index page, not the employer's own system"),
            (not candidate["has_profile"], 20, "no active resume profile")):
        if condition:
            confidence -= penalty
            notes.append(note)
    confidence = max(5, confidence)
    confidence_label = "high" if confidence >= 70 else "medium" if confidence >= 45 else "low"

    mandatory_missing = m_missing + l_missing
    if eligibility == "not_eligible":
        tier = "ineligible"
    elif (match >= 70 and eligibility == "eligible" and (mandatory_cov or 0) >= 0.75 and not m_missing
          and freshness["label"] not in {"aging", "stale"} and confidence_label != "low"):
        tier = "strong"
    elif match >= 45:
        tier = "possible"
    else:
        tier = "low"
    composite = round(match * {"eligible": 1.0, "uncertain": 0.85, "not_eligible": 0.4}[eligibility]
                      * freshness["factor"] * (0.85 + 0.15 * confidence / 100), 1)

    why = []
    if role_reason:
        why.append(role_reason)
    if m_total or l_total:
        why.append(f"Mandatory skills: {len(m_matched) + len(l_matched)} of {m_total + l_total} on your resume"
                   + (f", {len(m_partial) + len(l_partial)} only in projects" if m_partial or l_partial else "") + ".")
    if p_total:
        why.append(f"Preferred skills: {len(p_matched)} of {p_total}.")
    if exp_min is not None:
        why.append(f"Experience: needs {exp_min}{'-' + str(exp_max) if exp_max else '+'} yrs, you have {years:g}.")
    if tier != "strong" and eligibility == "eligible" and m_missing:
        why.append(f"Not strong: mandatory skills missing ({', '.join(m_missing[:4])}).")
    if freshness["label"] in {"aging", "stale"}:
        why.append(f"Posted {freshness['age_days']} days ago.")
    return {
        "match": match, "tier": tier, "composite": composite,
        "eligibility": eligibility, "gates": gates, "warnings": warnings,
        "freshness": {k: v for k, v in freshness.items() if k != "factor"},
        "confidence": confidence, "confidence_label": confidence_label, "confidence_notes": notes,
        "requirements": requirements, "breakdown": breakdown, "weights": weights,
        "matched": m_matched + l_matched + p_matched, "partial": m_partial + l_partial + p_partial,
        "missing_mandatory": mandatory_missing, "missing_preferred": p_missing,
        "experience": {"required_min": exp_min, "required_max": exp_max, "candidate": years,
                       "difference": None if exp_min is None else round(years - exp_min, 1)},
        "why": " ".join(why),
        "requisition_id": reqs.get("requisition_id"), "deadline": reqs.get("deadline"),
        "employment_type": reqs.get("employment_type"),
        "skills_extracted": [s["name"] for s in reqs["mandatory_skills"] + reqs["listed_skills"] + reqs["preferred_skills"]],
        "structured": reqs.get("structured"),
    }
