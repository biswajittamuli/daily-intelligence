"""Deterministic requirement extraction from a job description.

Splits a description into sections (responsibilities / mandatory / preferred / other)
from common headings and inline cues, then extracts:
skills (mandatory / preferred / listed-without-priority), education, experience range,
location and work-authorization restrictions, employment type, graduation-batch limits
and an application deadline. Every requirement carries the sentence it came from.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.services.freshness import parse_date
from app.services.skills_taxonomy import detect_skills

MANDATORY_HEAD = re.compile(
    r"\b(requirements?|required|must[- ]haves?|minimum qualifications?|basic qualifications?|"
    r"qualifications|what you(?:'|’)?ll need|what we(?:'|’)?re looking for|you (?:should|must) have|"
    r"who you are|about you|you have|you bring|skills required|eligibility(?: criteria)?|"
    r"key skills|technical skills|you might be a good fit if you)\b", re.I)
PREFERRED_HEAD = re.compile(
    r"\b(nice[- ]to[- ]haves?|preferred(?: qualifications?| skills)?|bonus(?: points)?|good[- ]to[- ]haves?|"
    r"pluses|plus points?|extra credit|desired skills|it(?:'|’)?s a plus|would be (?:great|nice))\b", re.I)
OTHER_HEAD = re.compile(
    r"\b(what you(?:'|’)?ll do|responsibilities|the role|about (?:the )?(?:role|team|us|company)|"
    r"what we offer|benefits|perks|why join|our values|compensation|equal opportunity|how to apply|"
    r"interview process|about [A-Z][\w ]+)\b", re.I)
PREFERRED_INLINE = re.compile(r"\b(preferred|nice to have|is a plus|a plus|bonus|good to have|desirable|"
                              r"advantage|ideally|optional)\b", re.I)
MANDATORY_INLINE = re.compile(r"\b(must|required|mandatory|need to have|essential|strong (?:knowledge|experience|"
                              r"proficiency)|proficien\w+|expert(?:ise)?|hands-on|minimum)\b", re.I)
SOFT_PREFIX = re.compile(r"\b(exposure to|familiarity with|familiar with|working knowledge of|basic understanding of|"
                         r"understanding of|awareness of|interest in)\b", re.I)
SOFT_SUFFIX = re.compile(r"\b(or similar|or equivalent|or a strong willingness to learn|willingness to learn|"
                         r"willing to learn|or other)\b", re.I)


def _soft_skills(sentence: str, skills: list[str]) -> set[str]:
    """Skills qualified by softening phrases ("exposure to X", "X or similar", "X, or willingness to learn")."""
    soft: set[str] = set()
    lowered = sentence.casefold()
    positions = sorted((lowered.find(skill.casefold()), skill) for skill in skills if lowered.find(skill.casefold()) >= 0)
    for index, (position, skill) in enumerate(positions):
        end = position + len(skill)
        next_start = positions[index + 1][0] if index + 1 < len(positions) else len(sentence)
        before = sentence[max(0, position - 40):position]
        # A trailing qualifier applies only to the skill directly before it.
        after = sentence[end:min(next_start, end + 30)]
        if SOFT_PREFIX.search(before) or SOFT_SUFFIX.match(after.strip(" ,")) or SOFT_SUFFIX.search(after[:22]):
            soft.add(skill)
    return soft

YEARS_RANGE = re.compile(r"\b(\d{1,2})\s*(?:-|–|to)\s*(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b", re.I)
YEARS_MIN = re.compile(
    r"(?:\b(?:minimum|min\.?|at least|over|more than)\s+(?:of\s+)?)?\b(\d{1,2})\s*\+?\s*(?:plus\s+)?(?:years?|yrs?)\b"
    r"(?!\s*old)", re.I)
FRESHER = re.compile(r"\b(freshers?|fresh graduates?|new grads?|recent graduates?|entry[- ]level|0\s*(?:-|–|to)\s*1\s*"
                     r"(?:years?|yrs?)|no (?:prior )?experience (?:required|needed)|graduate engineer trainee|"
                     r"campus hire|internship|intern\b)", re.I)
EXPERIENCE_CONTEXT = re.compile(r"\b(experience|exp\b|building|working|professional|industry|years? of|in (?:a|an)|"
                                r"hands-on|developing|production|track record)\b", re.I)

DEGREES = [
    ("PhD", re.compile(r"(?i:\bph\.?\s?d\b|\bdoctorate\b|\bdoctoral\b)")),
    ("Master's", re.compile(r"(?i:\bmaster(?:'|’)?s?\b(?:\s+degree)?)|\bM\.?\s?Tech\b|\bM\.E\.|\bM\.?Sc\b|"
                            r"\bMCA\b|\bM\.S\.|\bMS\b(?=\s+in\b)")),
    ("Bachelor's", re.compile(r"(?i:\bbachelor(?:'|’)?s?\b|\bundergraduate degree\b|\bengineering degree\b|"
                              r"\bdegree in (?:computer|cs|it|engineering))|\bB\.?\s?Tech\b|\bB\.E\.?(?=[\s/,(])|"
                              r"\bBE\b(?=\s*(?:/|in\b|\())|\bB\.?Sc\b|\bBCA\b|\bB\.S\.")),
    ("Diploma", re.compile(r"(?i:\bdiploma\b)")),
]
# Bachelor's named explicitly (not just "degree in computer science", which also describes a Master's).
BACHELOR_EXPLICIT = re.compile(r"(?i:\bbachelor(?:'|’)?s?\b|\bundergraduate degree\b)|\bB\.?\s?Tech\b|\bB\.E\.?(?=[\s/,(])|"
                               r"\bBE\b(?=\s*(?:/|in\b|\(|,|or\b))|\bB\.?Sc\b|\bBCA\b|\bB\.S\.")


def _named_degrees(text: str) -> list[str]:
    named = [degree for degree, pattern in DEGREES if pattern.search(text)]
    if "Bachelor's" in named and len(named) > 1 and not BACHELOR_EXPLICIT.search(text):
        named.remove("Bachelor's")
    return named


DEGREE_CONTEXT = re.compile(r"(?i:\b(degree|bachelor|master|ph\.?d|graduate|diploma|qualification|education)\b)|"
                            r"\bB\.?\s?Tech\b|\bM\.?\s?Tech\b|\bB\.E\.|\bMCA\b|\bBCA\b")
DEGREE_RANK = {"Diploma": 1, "Bachelor's": 2, "Master's": 3, "PhD": 4}
EQUIVALENT = re.compile(r"\b(or equivalent|equivalent (?:practical )?experience|or related experience|"
                        r"or similar|not required|preferred)\b", re.I)
FIELD_CS = re.compile(r"\b(computer science|cs\b|cse|information technology|\bit\b|software engineering|"
                      r"computer engineering|ece|electronics|related field|technical field|stem)\b", re.I)
AUTH = re.compile(r"\b(authori[sz]ed to work in (?:the )?([A-Z][A-Za-z ]+?)(?=[.,;]|\s+without|\s+and|$)|"
                  r"(?:no|not able to offer|cannot (?:offer|provide)|unable to (?:offer|provide)) (?:visa )?sponsorship|"
                  r"right to work in (?:the )?([A-Z][A-Za-z ]+?)(?=[.,;]|$)|security clearance|"
                  r"(?:us|u\.s\.) citizens? (?:only|required))", re.I)
ONSITE = re.compile(r"\b(must (?:be|reside|live) (?:based )?in ([A-Z][A-Za-z ,]+?)(?=[.;]|$)|"
                    r"(?:onsite|on-site|in-office|in office)\b[^.]{0,40}\b(?:in|at) ([A-Z][A-Za-z ,]+?)(?=[.;]|$)|"
                    r"willing(?:ness)? to relocate)", re.I)
BATCH = re.compile(r"\b((?:19|20)\d{2})\s*(?:(?:/|,|&|and|or)\s*((?:19|20)\d{2}))?\s*(?:batch|pass[- ]?outs?|graduates?|"
                   r"graduating)\b|\b(?:batch|graduating|graduation year|class) (?:of )?((?:19|20)\d{2})", re.I)
DEADLINE = re.compile(r"\b(?:apply by|last date(?: to apply)?|application deadline|applications close(?:s)? on|"
                      r"deadline)\s*[:\-]?\s*([0-9]{1,2}[ /.-][A-Za-z0-9]{2,9}[ /.-][0-9]{2,4}|[A-Za-z]{3,9}\.? [0-9]{1,2},? "
                      r"[0-9]{4}|[0-9]{4}-[0-9]{2}-[0-9]{2})", re.I)
EMPLOYMENT = [
    ("Internship", re.compile(r"\b(internship|intern\b|apprentice)", re.I)),
    ("Contract", re.compile(r"\b(contract(?:ual)?|freelance|temporary)\b", re.I)),
    ("Part-time", re.compile(r"\bpart[- ]time\b", re.I)),
    ("Full-time", re.compile(r"\bfull[- ]time\b|\bpermanent\b", re.I)),
]
REQUISITION = re.compile(r"\b(?:job|req(?:uisition)?|position|reference|ref)\.?\s*(?:id|no|number|#|code)\s*[:#.]?\s*"
                         r"([A-Z0-9][A-Z0-9-_/]{2,24})\b", re.I)

SECTION_SPLIT = re.compile(r"(?:\n+|(?<=[.!?:])\s+(?=[A-Z])|\s+[-•*●▪]\s+|\s+\d+\.\s+(?=[A-Z]))")


CAPS_HEADING = re.compile(r"(?<![A-Za-z])((?:[A-Z][A-Z'’&/]*\s+){1,8}[A-Z][A-Z'’&/]+)(?=\s|[:\-]|$)")


def _segments(text: str) -> list[tuple[str, str]]:
    """Return (section, sentence) pairs. section: mandatory | preferred | other | unknown."""
    section = "unknown"
    output: list[tuple[str, str]] = []
    # Put ALL-CAPS headings that are glued to running text on their own line.
    text = CAPS_HEADING.sub(lambda m: "\n" + m.group(1) + ":\n" if len(m.group(1)) >= 10 else m.group(1), text or "")
    for raw in SECTION_SPLIT.split(text):
        piece = " ".join(raw.split())
        if not piece:
            continue
        # "Heading: content" -> switch section, then process the content.
        colon = re.match(r"^([A-Za-z][^:]{2,60}):\s*(\S.*)$", piece)
        if colon and (MANDATORY_HEAD.search(colon.group(1)) or PREFERRED_HEAD.search(colon.group(1))
                      or OTHER_HEAD.search(colon.group(1))) and len(colon.group(1).split()) <= 7:
            label = colon.group(1)
            section = ("preferred" if PREFERRED_HEAD.search(label) else
                       "mandatory" if MANDATORY_HEAD.search(label) else "other")
            piece = colon.group(2)
        head = piece[:90]
        # A heading-like fragment switches the section for following lines.
        is_heading = len(piece) <= 90 and (piece.endswith(":") or piece.isupper()
                                           or (len(piece.split()) <= 6 and not re.search(r"\d", piece)))
        if PREFERRED_HEAD.search(head) and (is_heading or head.lower().startswith(("preferred", "nice", "bonus", "good to"))):
            section = "preferred"
            rest = PREFERRED_HEAD.split(piece, maxsplit=1)[-1] if not is_heading else ""
            if rest.strip(" :-"):
                output.append((section, rest.strip(" :-")))
            continue
        if MANDATORY_HEAD.search(head) and is_heading:
            section = "mandatory"
            continue
        if OTHER_HEAD.search(head) and is_heading:
            section = "other"
            continue
        # Inline headings inside long text, e.g. "WHAT WE'RE LOOKING FOR - 3+ years ..."
        inline = re.match(r"^([A-Z][A-Z' ’]{6,60})\s+[-:]\s*(.+)$", piece)
        if inline:
            label, rest = inline.group(1), inline.group(2)
            if PREFERRED_HEAD.search(label):
                section = "preferred"
            elif MANDATORY_HEAD.search(label):
                section = "mandatory"
            elif OTHER_HEAD.search(label):
                section = "other"
            piece = rest
        output.append((section, piece))
    return output


def _priority(section: str, sentence: str) -> str:
    if PREFERRED_INLINE.search(sentence):
        return "preferred"
    if section == "preferred":
        return "preferred"
    if section == "mandatory":
        return "mandatory"
    if MANDATORY_INLINE.search(sentence):
        return "mandatory"
    return "listed"


def extract_requirements(text: str, *, title: str = "", today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    text = text or ""
    segments = _segments(text)
    has_structure = any(section in {"mandatory", "preferred"} for section, _ in segments)
    skills: dict[str, dict[str, Any]] = {}
    rank = {"mandatory": 3, "listed": 2, "preferred": 1}
    exp_min: tuple[int, str] | None = None
    exp_max: int | None = None
    exp_priority = "listed"
    fresher_ok = bool(FRESHER.search(f"{title} {text[:4000]}"))
    education: list[dict[str, Any]] = []
    for section, sentence in segments:
        if section == "other" and has_structure:
            # Responsibilities name technologies used on the job, not requirements.
            for skill in detect_skills(sentence):
                skills.setdefault(skill, {"name": skill, "priority": "context", "evidence": sentence[:220]})
            continue
        priority = _priority(section, sentence)
        found = detect_skills(sentence)
        soft = _soft_skills(sentence, found)
        for skill in found:
            entry = {"name": skill, "priority": "preferred" if skill in soft and priority in {"mandatory", "listed"}
                     else priority, "evidence": sentence[:220]}
            current = skills.get(skill)
            if current is None or rank.get(entry["priority"], 0) > rank.get(current["priority"], 0):
                skills[skill] = entry
        # experience
        if EXPERIENCE_CONTEXT.search(sentence) or section == "mandatory":
            match = YEARS_RANGE.search(sentence)
            low = high = None
            if match and int(match.group(1)) <= int(match.group(2)) <= 30:
                low, high = int(match.group(1)), int(match.group(2))
            else:
                match = YEARS_MIN.search(sentence)
                if match and 0 < int(match.group(1)) <= 25 and not re.search(r"\b(company|founded|old|history|anniversary)\b",
                                                                              sentence, re.I):
                    low = int(match.group(1))
            if low is not None:
                this_priority = "preferred" if priority == "preferred" else "mandatory"
                if exp_min is None or (this_priority == "mandatory" and exp_priority != "mandatory") or \
                        (this_priority == exp_priority and low < exp_min[0]):
                    exp_min, exp_max, exp_priority = (low, sentence[:220]), high, this_priority
        # education
        # Alternatives in one sentence ("B.Tech, BE or M.Tech") mean the lowest listed degree qualifies.
        named = _named_degrees(sentence)
        if named and DEGREE_CONTEXT.search(sentence):
            degree = min(named, key=lambda name: DEGREE_RANK[name])
            education.append({"degree": degree, "priority": "preferred" if (priority == "preferred" or
                                                                             EQUIVALENT.search(sentence)) else "mandatory",
                              "field_cs": bool(FIELD_CS.search(sentence)), "evidence": sentence[:220]})
    if not education:
        found = []
        for degree, pattern in DEGREES:
            match = pattern.search(text)
            if match and DEGREE_CONTEXT.search(text[max(0, match.start() - 80):match.end() + 80]):
                found.append((match.start(), degree, match))
        if found:
            # The first-mentioned degree and any alternatives within the same short span: keep the lowest.
            found.sort()
            first = found[0][0]
            near = [item for item in found if item[0] - first <= 60]
            if len(near) > 1 and not BACHELOR_EXPLICIT.search(text[max(0, first - 20):first + 80]):
                near = [item for item in near if item[1] != "Bachelor's"] or near
            _, degree, match = min(near, key=lambda item: DEGREE_RANK[item[1]])
            education.append({"degree": degree, "priority": "listed", "field_cs": bool(FIELD_CS.search(text)),
                              "evidence": text[max(0, match.start() - 80):match.end() + 80].strip()})
    auth = []
    for match in AUTH.finditer(text):
        country = (match.group(2) or match.group(3) or "").strip()
        auth.append({"requirement": " ".join(match.group(0).split())[:140], "country": country or None})
    location_rules = [" ".join(match.group(0).split())[:140] for match in ONSITE.finditer(text)][:3]
    batches: list[int] = []
    for match in BATCH.finditer(text):
        for group in match.groups():
            if group and 2000 <= int(group) <= 2100:
                batches.append(int(group))
    deadline = None
    match = DEADLINE.search(text)
    if match:
        parsed = parse_date(match.group(1)) or parse_date(match.group(1).replace(",", ""))
        deadline = parsed.isoformat() if parsed else None
    employment = next((name for name, pattern in EMPLOYMENT if pattern.search(f"{title} {text[:3000]}")), None)
    requisition = None
    match = REQUISITION.search(text)
    if match:
        requisition = match.group(1)
    mandatory = [s for s in skills.values() if s["priority"] == "mandatory"]
    preferred = [s for s in skills.values() if s["priority"] == "preferred"]
    listed = [s for s in skills.values() if s["priority"] == "listed"]
    context = [s for s in skills.values() if s["priority"] == "context"]
    return {
        "structured": has_structure,
        "mandatory_skills": mandatory, "preferred_skills": preferred, "listed_skills": listed,
        "context_skills": context,
        "experience_min": exp_min[0] if exp_min else (0 if fresher_ok else None),
        "experience_max": exp_max,
        "experience_priority": exp_priority if exp_min else ("listed" if fresher_ok else None),
        "experience_evidence": exp_min[1] if exp_min else None,
        "fresher_friendly": fresher_ok,
        "education": education[:3],
        "work_authorization": auth[:3],
        "location_rules": location_rules,
        "batches": sorted(set(batches))[:4],
        "deadline": deadline,
        "employment_type": employment,
        "requisition_id": requisition,
        "text_chars": len(text),
    }
