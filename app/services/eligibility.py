"""Deterministic candidate eligibility for public recruitment (government, PSU, examinations).

Two inputs, one verdict:

    candidate eligibility profile  (facts the user declared; unknown stays unknown)
  + structured notice requirements (``requirements.extract_notice_requirements``: the notification's own clauses)
  -> ``evaluate`` -> eligible | likely_eligible | uncertain | not_eligible, with the rules that passed and
     failed, the candidate facts that are missing, and the quoted clauses used as evidence.

Rules of the engine
- Every rule is a pure function of the two inputs. A language model may help *extract* requirements; it never
  takes part in the decision.
- A fact the candidate has not declared is never guessed (age, category, percentage, GATE score, …). A rule
  that needs a missing fact yields "uncertain" and names the fact; it can never yield "eligible".
- A relaxation applies only when the notification states it for the candidate's declared category.
- A requirement the notification does not state is not invented. When the qualification clause could not be
  read at all, the best possible verdict is "likely_eligible".

Assumptions (documented in docs/V5_SOURCE_FIRST_DISCOVERY.md)
- Age limits are inclusive: "maximum 30 as on D" is met by a candidate who is exactly 30 years old on D (date
  of birth on or after D minus 30 years) and failed by one who is 30 years and one day old.
- A GATE score is valid for three years. Without a declared validity end date it is taken to end on
  31 March of (GATE year + 3).
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from app.services.requirements import (BRANCH_LABEL, BRANCHES, DEGREE_LABEL, GATE_PAPERS, STATES,
                                       extract_notice_requirements, parse_notice_date)

SCHEMA_VERSION = 1
CATEGORIES = ["General", "OBC-NCL", "OBC-CL", "SC", "ST", "EWS"]
GENDERS = ["female", "male", "other"]
SECTORS = ["psu", "government", "private"]
STATUS_LABEL = {"eligible": "Eligible", "likely_eligible": "Likely eligible", "uncertain": "Uncertain",
                "not_eligible": "Not eligible"}
WINDOW_LABEL = {"open": "Applications open", "closing_soon": "Closing soon", "opening_soon": "Opening soon",
                "closed": "Applications closed", "unknown": "Application dates not stated"}

# Candidate degree -> family used by notices. Rank orders families for "minimum qualification" checks.
_DEGREE_FAMILY: list[tuple[str, re.Pattern[str]]] = [
    ("phd", re.compile(r"\bph\.?\s?d\b|doctorate", re.I)),
    ("pg_engineering", re.compile(r"\bm\.?\s?tech\b|\bm\.?\s?e\b\.?$|\bm\.e\.|master\s+of\s+(?:engineering|technology)|\bm\.?\s?s\b.*(?:engineering|research)", re.I)),
    ("pg", re.compile(r"\bmca\b|\bm\.?\s?sc\b|\bmba\b|\bm\.?\s?com\b|\bm\.?\s?a\b\.?$|master|post\s?graduat", re.I)),
    ("engineering", re.compile(r"\bb\.?\s?tech\b|\bb\.?\s?e\b\.?$|\bb\.e\.|\bb\.?\s?sc\.?\s*\(?\s*engg|bachelor\s+of\s+(?:engineering|technology)", re.I)),
    ("graduate", re.compile(r"\bb\.?\s?sc\b|\bbca\b|\bb\.?\s?com\b|\bb\.?\s?a\b\.?$|\bbba\b|bachelor|graduate", re.I)),
    ("diploma", re.compile(r"diploma", re.I)),
    ("iti", re.compile(r"\biti\b", re.I)),
    ("class12", re.compile(r"\b12th\b|10\s*\+\s*2|intermediate|higher\s+secondary|\bhsc\b", re.I)),
    ("class10", re.compile(r"\b10th\b|matric|sslc", re.I)),
]
# What each candidate degree family also satisfies (a B.Tech holder is a graduate; an M.Tech is postgraduate).
_SATISFIES = {
    "phd": {"phd", "pg", "graduate", "class12", "class10"},
    "pg_engineering": {"pg_engineering", "pg", "graduate", "class12", "class10"},
    "pg": {"pg", "graduate", "class12", "class10"},
    "engineering": {"engineering", "graduate", "class12", "class10"},
    "graduate": {"graduate", "class12", "class10"},
    "diploma": {"diploma", "class10"},
    "iti": {"iti", "class10"},
    "class12": {"class12", "class10"},
    "class10": {"class10"},
}
# Branch codes treated as the same discipline when a notice lists one of them.
_BRANCH_EQUIVALENTS = {"cs": {"cs"}, "it": {"it"}, "software": {"software"}}


def degree_family(degree: Any) -> str | None:
    text = " ".join(str(degree or "").split())
    if not text:
        return None
    for family, pattern in _DEGREE_FAMILY:
        if pattern.search(text):
            return family
    return None


def branch_codes(branch: Any) -> list[str]:
    """Canonical branch codes named in a free-text branch ("Computer Science and Engineering" -> ["cs"])."""
    text = " ".join(str(branch or "").split())
    return [code for code, pattern in BRANCHES.items() if pattern.search(text)] if text else []


# ------------------------------------------------------------------------------------------ profile
def _text(value: Any, limit: int = 120) -> str | None:
    text = " ".join(str(value or "").split())[:limit]
    return text or None


def _number(value: Any, low: float, high: float) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Expected a number, got {value!r}") from None
    if not low <= number <= high:
        raise ValueError(f"Value {number:g} must be between {low:g} and {high:g}")
    return number


def _whole(value: Any, low: int, high: int) -> int | None:
    number = _number(value, low, high)
    return None if number is None else int(number)


def _day(value: Any) -> str | None:
    if value in (None, ""):
        return None
    parsed = parse_notice_date(value)
    if parsed is None:
        raise ValueError(f"Not a valid date: {value!r} (use YYYY-MM-DD)")
    return parsed.isoformat()


def _flag(value: Any) -> bool | None:
    """Tri-state: True / False / None (not declared)."""
    if value in (None, "", "unknown"):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().casefold()
    if text in {"yes", "true", "1", "on"}:
        return True
    if text in {"no", "false", "0", "off"}:
        return False
    raise ValueError(f"Expected yes, no or unknown, got {value!r}")


def _choice(value: Any, allowed: list[str]) -> str | None:
    if value in (None, "", "unknown"):
        return None
    for option in allowed:
        if str(value).strip().casefold() == option.casefold():
            return option
    raise ValueError(f"{value!r} is not one of: {', '.join(allowed)}")


def _strings(value: Any, limit: int = 12) -> list[str]:
    if isinstance(value, str):
        value = re.split(r"[,\n]", value)
    return [text for text in (_text(item, 60) for item in (value or [])) if text][:limit]


def empty_profile() -> dict[str, Any]:
    return clean_profile({})


def clean_profile(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Validate and normalise a candidate eligibility profile. Unknown facts stay ``None`` — never defaulted."""
    data = payload if isinstance(payload, dict) else {}
    education = data.get("education") if isinstance(data.get("education"), dict) else {}
    experience = data.get("experience") if isinstance(data.get("experience"), dict) else {}
    gate = data.get("gate") if isinstance(data.get("gate"), dict) else {}
    preferences = data.get("preferences") if isinstance(data.get("preferences"), dict) else {}
    dob = _day(data.get("date_of_birth"))
    if dob and not date(1940, 1, 1) <= date.fromisoformat(dob) <= date.today():
        raise ValueError("Date of birth must be a past date")
    paper = _text(gate.get("paper"), 4)
    if paper:
        paper = paper.upper()
        if paper not in GATE_PAPERS:
            raise ValueError(f"Unknown GATE paper code {paper!r}")
    state = _text(data.get("domicile_state"), 40)
    if state:
        state = next((s for s in STATES if s.casefold() == state.casefold()), state)
    exams = []
    for item in data.get("other_exams") or []:
        if isinstance(item, dict) and _text(item.get("name"), 40):
            exams.append({"name": _text(item.get("name"), 40), "year": _whole(item.get("year"), 1990, 2100),
                          "score": _number(item.get("score"), 0, 100000), "valid_until": _day(item.get("valid_until"))})
    sectors = [s for s in (str(x).strip().casefold() for x in _strings(preferences.get("sectors"))) if s in SECTORS]
    return {
        "schema": SCHEMA_VERSION,
        "date_of_birth": dob,
        "age": None if dob else _whole(data.get("age"), 14, 80),
        "age_as_of": None if dob else (_day(data.get("age_as_of")) if data.get("age") not in (None, "") else None),
        "category": _choice(data.get("category"), CATEGORIES),
        "gender": _choice(data.get("gender"), GENDERS),
        "pwd": _flag(data.get("pwd")),
        "ex_serviceman": _flag(data.get("ex_serviceman")),
        "nationality": _text(data.get("nationality"), 40),
        "domicile_state": state,
        "education": {
            "degree": _text(education.get("degree"), 60), "branch": _text(education.get("branch"), 100),
            "university": _text(education.get("university"), 120),
            "graduation_year": _whole(education.get("graduation_year"), 1970, 2100),
            "final_year": _flag(education.get("final_year")),
            "percentage": _number(education.get("percentage"), 0, 100),
            "cgpa": _number(education.get("cgpa"), 0, 10),
            "cgpa_scale": _whole(education.get("cgpa_scale"), 4, 10) if education.get("cgpa") not in (None, "") else None,
            "backlogs": _whole(education.get("backlogs"), 0, 60),
        },
        "experience": {"full_time_months": _whole(experience.get("full_time_months"), 0, 720),
                       "internship_months": _whole(experience.get("internship_months"), 0, 240)},
        "gate": {"appeared": _flag(gate.get("appeared")), "paper": paper, "year": _whole(gate.get("year"), 2000, 2100),
                 "score": _number(gate.get("score"), 0, 1000), "rank": _whole(gate.get("rank"), 1, 2_000_000),
                 "valid_until": _day(gate.get("valid_until"))},
        "other_exams": exams[:6],
        "preferences": {"sectors": sectors, "locations": _strings(preferences.get("locations")),
                        "min_salary": _number(preferences.get("min_salary"), 0, 1e9),
                        "employment_types": _strings(preferences.get("employment_types"), 6)},
        "provenance": {"source": "user_declared"},
    }


# Facts that decide most public-recruitment notices; listed so the UI can say what is still unknown.
KEY_FACTS = [
    ("date_of_birth", "Date of birth"), ("category", "Category"), ("education.degree", "Degree"),
    ("education.branch", "Branch"), ("education.graduation_year", "Graduation year"),
    ("education.percentage", "Percentage or CGPA"), ("gate.appeared", "Whether you appeared in GATE"),
    ("nationality", "Nationality"), ("experience.full_time_months", "Full-time experience (months)"),
]


def _get(profile: dict[str, Any], path: str) -> Any:
    value: Any = profile
    for part in path.split("."):
        value = (value or {}).get(part) if isinstance(value, dict) else None
    return value


def unknown_facts(profile: dict[str, Any]) -> list[str]:
    missing = []
    for path, label in KEY_FACTS:
        value = _get(profile, path)
        if path == "date_of_birth" and (profile.get("age") is not None and profile.get("age_as_of")):
            continue
        if path == "education.percentage" and _get(profile, "education.cgpa") is not None:
            continue
        if value is None:
            missing.append(label)
    return missing


def profile_from_resume(resume_profile: dict[str, Any] | None) -> dict[str, Any]:
    """Suggestions a resume can support (degree, branch, graduation year). Never age, category, marks or scores.

    Returned separately from the stored profile: the user confirms them in the form before they count."""
    resume_profile = resume_profile or {}
    suggestion: dict[str, Any] = {}
    education = " ; ".join(str(item) for item in resume_profile.get("education") or [])
    family = degree_family(education)
    if family:
        found = re.search(r"\bB\.?\s?Tech\b|\bB\.?\s?E\b\.?|\bM\.?\s?Tech\b|\bMCA\b|\bBCA\b|\bB\.?\s?Sc\b|\bM\.?\s?Sc\b|\bDiploma\b|\bPh\.?\s?D\b",
                          education, re.I)
        suggestion["degree"] = found.group(0) if found else DEGREE_LABEL.get(family)
    codes = branch_codes(education)
    if codes:
        suggestion["branch"] = BRANCH_LABEL[codes[0]]
    year = resume_profile.get("graduation_year")
    if isinstance(year, int) and 1970 <= year <= 2100:
        suggestion["graduation_year"] = year
    return suggestion


# ------------------------------------------------------------------------------------------ rules
def _years_before(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:  # 29 February
        return day.replace(year=day.year - years, day=28)


class _Verdict:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []
        self.missing: list[str] = []
        self.unclear: list[str] = []
        self.evidence: list[str] = []
        self.decided: set[str] = set()

    def ok(self, rule: str, message: str) -> None:
        self.passed.append(message)
        self.decided.add(rule)

    def fail(self, rule: str, message: str) -> None:
        self.failed.append(message)
        self.decided.add(rule)

    def need(self, fact: str) -> None:
        if fact not in self.missing:
            self.missing.append(fact)

    def vague(self, message: str) -> None:
        if message not in self.unclear:
            self.unclear.append(message)

    def quote(self, clause: Any) -> None:
        text = " ".join(str((clause or {}).get("evidence") if isinstance(clause, dict) else clause or "").split())
        if text and text not in self.evidence:
            self.evidence.append(text[:520])


def _reservation_keys(profile: dict[str, Any]) -> list[str]:
    keys = []
    if profile.get("category") in {"SC", "ST", "OBC-NCL", "EWS"}:
        keys.append(profile["category"])
    if profile.get("pwd") is True:
        keys.append("PwD")
    if profile.get("ex_serviceman") is True:
        keys.append("Ex-Serviceman")
    return keys


def _undeclared_groups(profile: dict[str, Any], stated: dict[str, Any]) -> list[str]:
    """Reservation facts the candidate has not declared that a stated relaxation depends on."""
    missing = []
    if profile.get("category") is None and any(k in stated for k in ("SC", "ST", "OBC-NCL", "EWS")):
        missing.append("Category not set")
    if profile.get("pwd") is None and "PwD" in stated:
        missing.append("PwD status not set")
    if profile.get("ex_serviceman") is None and "Ex-Serviceman" in stated:
        missing.append("Ex-serviceman status not set")
    return missing


def _age_rule(v: _Verdict, profile: dict[str, Any], req: dict[str, Any], as_of: date, as_of_source: str) -> None:
    age = req.get("age") or {}
    if age.get("min") is None and age.get("max") is None:
        return
    v.quote(age)
    dob = parse_notice_date(profile.get("date_of_birth"))
    bounds: list[date] = []  # possible dates of birth
    if dob:
        bounds = [dob]
    elif profile.get("age") is not None and profile.get("age_as_of"):
        declared = date.fromisoformat(profile["age_as_of"])
        bounds = [_years_before(declared, int(profile["age"]) + 1) + timedelta(days=1), _years_before(declared, int(profile["age"]))]
    else:
        v.need("Date of birth not set")
        return
    relaxation = (req.get("age_relaxation") or {}).get("years") or {}
    applied = max((int(relaxation[k]) for k in _reservation_keys(profile) if k in relaxation), default=0)
    label_on = f"as on {as_of.isoformat()}" + ("" if as_of_source == "notice" else f" ({as_of_source})")
    if age.get("max") is not None:
        limit = int(age["max"])
        earliest = _years_before(as_of, limit + applied)  # born on/after this date -> within the limit
        results = [b >= earliest for b in bounds]
        suffix = f" (includes {applied} years' relaxation stated for {', '.join(k for k in _reservation_keys(profile) if k in relaxation)})" if applied else ""
        if all(results):
            v.ok("age", f"Age: maximum {limit + applied} {label_on}{suffix}")
        elif not any(results):
            undeclared = _undeclared_groups(profile, relaxation)
            best = max((int(x) for x in relaxation.values()), default=0)
            if undeclared and all(b >= _years_before(as_of, limit + best) for b in bounds):
                for fact in undeclared:
                    v.need(fact)  # a stated relaxation could apply; never assumed
                v.quote(req.get("age_relaxation"))
            else:
                v.fail("age", f"Age: maximum {limit + applied} {label_on}{suffix}")
        else:
            v.need("Exact date of birth not set (declared age is too close to the limit)")
        if applied:
            v.quote(req.get("age_relaxation"))
    if age.get("min") is not None:
        limit = int(age["min"])
        latest = _years_before(as_of, limit)  # born on/before this date -> old enough
        results = [b <= latest for b in bounds]
        if all(results):
            v.ok("age_min", f"Age: minimum {limit} {label_on}")
        elif not any(results):
            v.fail("age_min", f"Age: minimum {limit} {label_on}")
        else:
            v.need("Exact date of birth not set (declared age is too close to the limit)")


def _qualification_rule(v: _Verdict, profile: dict[str, Any], req: dict[str, Any]) -> None:
    q = req.get("qualification")
    if not q:
        return
    v.quote(q)
    education = profile.get("education") or {}
    family = degree_family(education.get("degree"))
    if not education.get("degree"):
        v.need("Degree not set")
        return
    if family is None:
        v.vague(f"Your degree “{education['degree']}” could not be matched to the notice's qualification list")
        return
    wanted = [d for d in q.get("degrees") or []]
    satisfied = _SATISFIES.get(family, {family})
    if wanted and not (set(wanted) & satisfied):
        labels = ", ".join(DEGREE_LABEL.get(d, d) for d in wanted)
        v.fail("degree", f"Degree: {education['degree']} is not among the accepted qualifications ({labels})")
        return
    accepted = next((d for d in wanted if d in satisfied), family)
    v.ok("degree", f"Degree: {education['degree']} accepted ({DEGREE_LABEL.get(accepted, accepted)})")
    # Branch applies when the matched qualification is a technical one or the notice lists branches at all.
    branches = q.get("branches") or []
    if q.get("any_branch") or q.get("any_degree") and not branches:
        v.ok("branch", "Branch: any discipline accepted")
        return
    if not branches:
        if accepted in {"engineering", "pg_engineering", "diploma"}:
            v.vague("The notice does not state which branches are accepted")
        return
    if not education.get("branch"):
        v.need("Branch not set")
        return
    mine = branch_codes(education.get("branch"))
    if not mine:
        v.vague(f"Your branch “{education['branch']}” could not be matched to the notice's branch list")
        return
    listed = ", ".join(BRANCH_LABEL.get(b, b) for b in branches)
    if set(mine) & set(branches):
        hit = next(b for b in mine if b in branches)
        v.ok("branch", f"Branch: {BRANCH_LABEL.get(hit, hit)} accepted")
    elif q.get("equivalent_allowed"):
        v.vague(f"Branch: {education['branch']} is not listed ({listed}); the notice also accepts equivalent disciplines")
    else:
        v.fail("branch", f"Branch: {education['branch']} is not among the listed branches ({listed})")


def _marks_rule(v: _Verdict, profile: dict[str, Any], req: dict[str, Any]) -> None:
    education = profile.get("education") or {}
    percentage, cgpa_req = req.get("percentage"), req.get("cgpa")
    if percentage:
        v.quote(percentage)
        minimum = float(percentage["min"])
        relaxed = percentage.get("relaxed") or {}
        mine = [float(relaxed[k]) for k in _reservation_keys(profile) if k in relaxed]
        applied = min(mine) if mine else minimum
        note = f" (relaxed minimum stated for {', '.join(k for k in _reservation_keys(profile) if k in relaxed)})" if mine else ""
        if education.get("percentage") is None:
            v.need("Percentage not set" + (" (a CGPA is declared; conversion varies by university)"
                                           if education.get("cgpa") is not None and not cgpa_req else ""))
        elif education["percentage"] >= applied:
            v.ok("percentage", f"Marks: {education['percentage']:g}% meets the minimum {applied:g}%{note}")
        else:
            undeclared = _undeclared_groups(profile, relaxed)
            if undeclared and relaxed and education["percentage"] >= min(float(x) for x in relaxed.values()):
                for fact in undeclared:
                    v.need(fact)
            else:
                v.fail("percentage", f"Marks: {education['percentage']:g}% is below the minimum {applied:g}%{note}")
    if cgpa_req and not (percentage and education.get("percentage") is not None):
        v.quote(cgpa_req)
        scale = int(cgpa_req.get("scale") or 10)
        if education.get("cgpa") is None:
            v.need("CGPA not set")
        elif int(education.get("cgpa_scale") or 10) != scale:
            v.vague(f"CGPA scales differ (yours is out of {education.get('cgpa_scale') or 10}, the notice uses {scale})")
        elif education["cgpa"] >= float(cgpa_req["min"]):
            v.ok("cgpa", f"CGPA: {education['cgpa']:g} meets the minimum {float(cgpa_req['min']):g}")
        else:
            v.fail("cgpa", f"CGPA: {education['cgpa']:g} is below the minimum {float(cgpa_req['min']):g}")


def _graduation_rule(v: _Verdict, profile: dict[str, Any], req: dict[str, Any], as_of: date) -> None:
    education = profile.get("education") or {}
    batches = (req.get("batches") or {}).get("years") or []
    if batches:
        v.quote(req.get("batches"))
        if education.get("graduation_year") is None:
            v.need("Graduation year not set")
        elif education["graduation_year"] in batches:
            v.ok("batch", f"Batch: {education['graduation_year']} is an accepted graduation year")
        else:
            v.fail("batch", f"Batch: only {', '.join(map(str, batches))} graduates may apply (yours: {education['graduation_year']})")
    final = req.get("final_year")
    studying = education.get("final_year")
    if studying is None and education.get("graduation_year") is not None:
        studying = education["graduation_year"] > as_of.year  # later calendar year: degree certainly not complete
        if education["graduation_year"] == as_of.year:
            studying = None
    if final is not None:
        v.quote(final)
        if studying is True:
            if final.get("allowed"):
                v.ok("final_year", "Final-year students may apply")
            else:
                v.fail("final_year", "Final-year / result-awaited candidates may not apply")
        elif studying is None and not final.get("allowed") and req.get("qualification"):
            v.need("Whether your degree is complete (final-year status not set)")
    elif studying is True and req.get("qualification"):
        v.vague("The notice does not say whether final-year students may apply")


def _gate_rule(v: _Verdict, profile: dict[str, Any], req: dict[str, Any], as_of: date) -> None:
    gate_req = req.get("gate") or {}
    if not gate_req.get("required"):
        return
    v.quote(gate_req)
    gate = profile.get("gate") or {}
    if gate.get("appeared") is False:
        v.fail("gate", "GATE: a GATE score is required and you declared none")
        return
    if gate.get("paper") is None and gate.get("year") is None and gate.get("score") is None:
        v.need("GATE score not set")
        return
    papers, years = gate_req.get("papers") or [], gate_req.get("years") or []
    failed = False
    if papers:
        if gate.get("paper") is None:
            v.need("GATE paper not set")
        elif gate["paper"] not in papers:
            v.fail("gate_paper", f"GATE paper: {gate['paper']} is not accepted (required: {', '.join(papers)})")
            failed = True
        else:
            v.ok("gate_paper", f"GATE paper: {gate['paper']} accepted")
    if gate.get("year") is None:
        v.need("GATE year not set")
    elif years:
        if gate["year"] in years:
            v.ok("gate_year", f"GATE year: {gate['year']} accepted")
        else:
            v.fail("gate_year", f"GATE year: only {', '.join(map(str, years))} scores are accepted (yours: {gate['year']})")
            failed = True
    else:
        until = parse_notice_date(gate.get("valid_until")) or date(gate["year"] + 3, 3, 31)
        if as_of <= until:
            v.ok("gate_validity", f"GATE {gate['year']} score valid until {until.isoformat()}")
        else:
            v.fail("gate_validity", f"GATE {gate['year']} score expired on {until.isoformat()} (three-year validity)")
            failed = True
    minimum = gate_req.get("min_score")
    if minimum is not None and not failed:
        if gate.get("score") is None:
            v.need("GATE score not set")
        elif gate["score"] >= float(minimum):
            v.ok("gate_score", f"GATE score: {gate['score']:g} meets the minimum {float(minimum):g}")
        else:
            v.fail("gate_score", f"GATE score: {gate['score']:g} is below the minimum {float(minimum):g}")


def _experience_rule(v: _Verdict, profile: dict[str, Any], req: dict[str, Any]) -> None:
    exp_req = req.get("experience") or {}
    if exp_req.get("min_months") is None and exp_req.get("max_months") is None:
        return
    v.quote(exp_req)
    exp = profile.get("experience") or {}
    minimum, maximum = exp_req.get("min_months"), exp_req.get("max_months")
    if minimum == 0 and maximum is None:
        v.ok("experience", "Experience: none required")
        return
    if exp.get("full_time_months") is None:
        v.need("Full-time experience (months) not set")
        return
    months = int(exp["full_time_months"])
    counted = "full-time"
    if exp_req.get("internships_count") is True:
        if exp.get("internship_months") is None:
            v.need("Internship experience (months) not set")
            return
        months += int(exp["internship_months"])
        counted = "full-time + internships, which the notice counts"
    if minimum is not None:
        if months >= int(minimum):
            v.ok("experience", f"Experience: {months} months ({counted}) meets the minimum {int(minimum)} months")
        else:
            v.fail("experience", f"Experience: {months} months ({counted}) is below the minimum {int(minimum)} months")
    if maximum is not None:
        if months <= int(maximum):
            v.ok("experience_max", f"Experience: {months} months is within the maximum {int(maximum)} months")
        else:
            v.fail("experience_max", f"Experience: {months} months exceeds the maximum {int(maximum)} months")


def _explicit_rules(v: _Verdict, profile: dict[str, Any], req: dict[str, Any]) -> None:
    nationality = req.get("nationality")
    if nationality:
        v.quote(nationality)
        if not profile.get("nationality"):
            v.need("Nationality not set")
        elif profile["nationality"].casefold() in {"indian", "india"}:
            v.ok("nationality", "Nationality: Indian")
        else:
            v.fail("nationality", f"Nationality: Indian nationals only (yours: {profile['nationality']})")
    domicile = req.get("domicile")
    if domicile:
        v.quote(domicile)
        if not profile.get("domicile_state"):
            v.need("Domicile state not set")
        elif profile["domicile_state"].casefold() == str(domicile["state"]).casefold():
            v.ok("domicile", f"Domicile: {domicile['state']}")
        else:
            v.fail("domicile", f"Domicile: {domicile['state']} required (yours: {profile['domicile_state']})")
    gender = req.get("gender")
    if gender:
        v.quote(gender)
        if not profile.get("gender"):
            v.need("Gender not set")
        elif profile["gender"] == gender["only"]:
            v.ok("gender", f"Open to {gender['only']} candidates")
        else:
            v.fail("gender", f"Open to {gender['only']} candidates only")
    for key, fact, label in (("pwd_only", "pwd", "persons with benchmark disabilities"),
                             ("ex_serviceman_only", "ex_serviceman", "ex-servicemen")):
        clause = req.get(key)
        if clause:
            v.quote(clause)
            if profile.get(fact) is None:
                v.need("PwD status not set" if fact == "pwd" else "Ex-serviceman status not set")
            elif profile[fact]:
                v.ok(key, f"Reserved for {label}: applies to you")
            else:
                v.fail(key, f"Reserved for {label} only")


def application_window(opening: Any, closing: Any, today: date | None = None, *, soon_days: int = 7) -> dict[str, Any]:
    today = today or date.today()
    start, end = parse_notice_date(opening), parse_notice_date(closing)
    if end and end < today:
        state = "closed"
    elif start and start > today:
        state = "opening_soon"
    elif end and (end - today).days <= soon_days:
        state = "closing_soon"
    elif end or start:
        state = "open"
    else:
        state = "unknown"
    return {"state": state, "label": WINDOW_LABEL[state], "opening_date": start.isoformat() if start else None,
            "closing_date": end.isoformat() if end else None,
            "days_left": (end - today).days if end and end >= today else None}


def evaluate(profile: dict[str, Any] | None, requirements: dict[str, Any] | None, *, closing_date: Any = None,
             opening_date: Any = None, today: date | None = None) -> dict[str, Any]:
    """Apply every stated requirement to the declared profile. Pure and deterministic."""
    today = today or date.today()
    profile = profile or empty_profile()
    req = requirements or {}
    age = req.get("age") or {}
    closing = parse_notice_date(closing_date)
    stated = parse_notice_date(age.get("as_on"))
    if stated:
        as_of, source = stated, "notice"
    elif closing:
        as_of, source = closing, "closing date"
    else:
        as_of, source = today, "today; the notice states no reference date"
    v = _Verdict()
    _age_rule(v, profile, req, as_of, source)
    _qualification_rule(v, profile, req)
    _marks_rule(v, profile, req)
    _graduation_rule(v, profile, req, closing or today)
    _gate_rule(v, profile, req, closing or today)
    _experience_rule(v, profile, req)
    _explicit_rules(v, profile, req)
    window = application_window(opening_date, closing_date, today)
    stated_rules = [k for k in ("age", "qualification", "percentage", "cgpa", "gate", "experience", "nationality",
                                "domicile", "gender", "pwd_only", "ex_serviceman_only", "batches", "final_year") if req.get(k)]
    if v.failed:
        status = "not_eligible"
        reasons = list(v.failed)
    elif v.missing:
        status = "uncertain"
        reasons = [f"Cannot be decided until you add: {', '.join(v.missing)}"]
    elif v.unclear:
        status = "uncertain"
        reasons = list(v.unclear)
    elif not stated_rules:
        status = "uncertain"
        reasons = ["No eligibility criteria could be read from the notification text; open the official notice"]
    elif "degree" in v.decided and ("branch" in v.decided or not (req.get("qualification") or {}).get("branches")):
        status = "eligible"
        reasons = ["Every requirement stated in the notification is met"]
    else:
        status = "likely_eligible"
        reasons = ["The stated requirements are met, but the notification's qualification clause could not be read"]
    summary = reasons[0] if reasons else ""
    return {
        "status": status, "status_label": STATUS_LABEL[status], "summary": summary[:300], "reasons": reasons,
        "missing_facts": list(v.missing), "failed_rules": list(v.failed), "passed_rules": list(v.passed),
        "unclear_rules": list(v.unclear), "evidence": v.evidence[:8], "as_of": as_of.isoformat(), "as_of_source": source,
        "stated_requirements": stated_rules, "window": window, "engine": SCHEMA_VERSION,
    }


def filter_bucket(result: dict[str, Any] | None) -> str:
    """UI filter for a stored verdict: eligible | likely | needs_fact | uncertain | not_eligible | undecided."""
    if not result or not result.get("status"):
        return "undecided"
    status = result["status"]
    if status == "eligible":
        return "eligible"
    if status == "likely_eligible":
        return "likely"
    if status == "not_eligible":
        return "not_eligible"
    return "needs_fact" if result.get("missing_facts") else "uncertain"


# ------------------------------------------------------------------------------------------ stored records
def record_requirements(record: dict[str, Any]) -> dict[str, Any]:
    """Requirements of a stored notice/exam: the structured clauses saved with it, else read from its stored text."""
    stored = record.get("requirements")
    if isinstance(stored, dict) and stored:
        return stored
    raw = record.get("raw") if isinstance(record.get("raw"), dict) else {}
    text = "\n".join(str(part) for part in (record.get("notification_text"), raw.get("raw_text"), record.get("qualifications"),
                                            record.get("age_limit") and f"Age limit: {record['age_limit']}") if part)
    return extract_notice_requirements(text) if text.strip() else {}


def evaluate_record(profile: dict[str, Any] | None, record: dict[str, Any], *, today: date | None = None) -> dict[str, Any]:
    closing = record.get("closing_date")
    if closing is None and record.get("event_type") == "application_close":
        closing = record.get("event_date")
    return evaluate(profile, record_requirements(record), closing_date=closing, opening_date=record.get("opening_date"),
                    today=today)


def reevaluate_store(store: Any, *, today: date | None = None) -> dict[str, int]:
    """Recompute the stored verdict of every notice and exam event (after the profile or the rules change)."""
    profile = store.eligibility_profile()
    counts: dict[str, int] = {"notices": 0, "exams": 0}
    for notice in store.notices(limit=500):
        result = evaluate_record(profile, notice, today=today)
        store.set_eligibility("recruitment_notices", notice["id"], result)
        counts["notices"] += 1
        counts[result["status"]] = counts.get(result["status"], 0) + 1
    for exam in store.exams(limit=1000):
        store.set_eligibility("exam_events", exam["id"], evaluate_record(profile, exam, today=today))
        counts["exams"] += 1
    return counts
