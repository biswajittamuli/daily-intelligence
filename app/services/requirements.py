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


# ====================================================================== public-recruitment notices (v5)
# Deterministic clause extraction for government / PSU / examination notifications. Nothing here decides
# eligibility: it only turns the notification's own wording into structured requirements, each with the
# sentence it came from. ``app.services.eligibility`` applies them to the candidate's declared facts.

_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november",
     "december"], 1)}
_MONTHS.update({m[:3]: i for m, i in list(_MONTHS.items())})
_MONTHS["sept"] = 9
_MONTH_RE = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
             r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)")
# Day-first numeric dates (Indian notices), ISO dates and "1st January 2027" / "January 1, 2027".
DATE_RE = (r"(?:\d{4}-\d{2}-\d{2}|\d{1,2}\s*[./-]\s*\d{1,2}\s*[./-]\s*(?:19|20)\d{2}|"
           rf"\d{{1,2}}(?:st|nd|rd|th)?[\s.,-]*{_MONTH_RE}[\s.,'-]*(?:19|20)\d{{2}}|"
           rf"{_MONTH_RE}\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+(?:19|20)\d{{2}})")
_DATE = re.compile(DATE_RE, re.I)


def parse_notice_date(value: Any) -> date | None:
    """Parse a date as written in Indian notifications (day first). Returns None when it is not a real date."""
    text = " ".join(str(value or "").split())
    if not text:
        return None
    try:
        found = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
        if found:
            return date(int(found.group(1)), int(found.group(2)), int(found.group(3)))
        found = re.fullmatch(r"(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{4})", text)
        if found:
            return date(int(found.group(3)), int(found.group(2)), int(found.group(1)))
        found = re.fullmatch(rf"(\d{{1,2}})(?:st|nd|rd|th)?[\s.,-]*({_MONTH_RE})[\s.,'-]*(\d{{4}})", text, re.I)
        if found:
            return date(int(found.group(3)), _MONTHS[found.group(2).casefold()], int(found.group(1)))
        found = re.fullmatch(rf"({_MONTH_RE})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})", text, re.I)
        if found:
            return date(int(found.group(3)), _MONTHS[found.group(1).casefold()], int(found.group(2)))
    except (ValueError, KeyError):
        return None
    return None


def _iso(value: Any) -> str | None:
    parsed = parse_notice_date(value)
    return parsed.isoformat() if parsed else None


def _sentences(text: str) -> list[str]:
    """Clauses of a notification: lines, table cells and sentences (dates like 01.01.2027 are not split)."""
    pieces = re.split(r"\n+|\s*\|\s*|(?<=[a-z)%])\.\s+(?=[A-Z(])|(?<=[12]\d{3})\.\s+(?=[A-Z(])|;\s+|\s+[•●▪]\s+", text or "")
    return [" ".join(piece.split()) for piece in pieces if piece and piece.strip()]


def _quote(sentence: str, limit: int = 260) -> str:
    return sentence[:limit].strip()


# Branch groups. A notice names branches in many spellings; the candidate's branch is mapped to the same codes.
BRANCHES: dict[str, re.Pattern[str]] = {
    "cs": re.compile(r"computer\s*science|computer\s*engineering|computer\s*(?:&|and)\s*(?:engineering|it\b)|\bcse\b|"
                     r"\bcs\s*(?:&|and|/)\s*it\b|\bc\.?s\.?e\b|computer\s+technology|\bcs\b(?=\s*[/,)&]|\s+and\b|\s+engg)", re.I),
    "it": re.compile(r"information\s+technology|\bi\.?t\.?\b(?=\s*[/,)&]|\s+engg|\s+engineering|\s*$)|\binfo(?:rmation)?\s*tech\b|"
                     r"information\s+science", re.I),
    "software": re.compile(r"software\s+engineering|software\s+engg", re.I),
    "ai_ds": re.compile(r"artificial\s+intelligence|data\s+science|machine\s+learning|\bai\s*(?:&|and)\s*(?:ml|ds)\b", re.I),
    "ece": re.compile(r"electronics\s*(?:&|and)\s*(?:tele)?communication|\bece\b|\be\s*&\s*c\b|\betc\b|telecommunication|"
                      r"electronics\s+engineering|\belectronics\b", re.I),
    "ee": re.compile(r"electrical\s*(?:&|and)\s*electronics|\beee\b|electrical\s+engineering|\belectrical\b|power\s+systems?", re.I),
    "instrumentation": re.compile(r"instrumentation|\bcontrol\s+engineering", re.I),
    "mech": re.compile(r"mechanical|production\s+engineering|industrial\s+engineering|\bmechatronics\b", re.I),
    "civil": re.compile(r"\bcivil\b|structural\s+engineering", re.I),
    "chem": re.compile(r"chemical\s+engineering|\bchemical\b|petrochemical|petroleum\s+engineering", re.I),
    "metallurgy": re.compile(r"metallurg|materials?\s+(?:science|engineering)", re.I),
    "mining": re.compile(r"\bmining\b", re.I),
    "mca": re.compile(r"\bm\.?c\.?a\b|computer\s+applications?", re.I),
}
BRANCH_LABEL = {"cs": "Computer Science", "it": "Information Technology", "software": "Software Engineering",
                "ai_ds": "AI / Data Science", "ece": "Electronics & Communication", "ee": "Electrical",
                "instrumentation": "Instrumentation", "mech": "Mechanical", "civil": "Civil", "chem": "Chemical",
                "metallurgy": "Metallurgy", "mining": "Mining", "mca": "Computer Applications"}
ANY_BRANCH = re.compile(r"\b(?:any|all)\s+(?:engineering\s+)?(?:discipline|branch|stream|specialis?ation)s?\b|"
                        r"\b(?:in\s+)?any\s+(?:branch|discipline)\s+of\s+engineering\b|"
                        r"\bengineering\s+(?:graduate|degree)s?\s+in\s+any\b|\bany\s+engineering\b", re.I)
ANY_DEGREE = re.compile(r"\b(?:graduat(?:e|ion)|bachelor(?:'|’)?s?\s+degree|degree)\s+in\s+any\s+(?:discipline|stream|subject)\b|"
                        r"\bany\s+(?:graduate|degree|graduation)\b|\bgraduates?\s+(?:from|of)\s+(?:a\s+)?recogni[sz]ed\s+university\b",
                        re.I)
EQUIVALENT_BRANCH = re.compile(r"\b(?:or\s+)?(?:equivalent|allied|relevant|related|similar)\s+"
                               r"(?:discipline|branch|field|subject|stream|specialis?ation)s?\b|\bor\s+equivalent\b", re.I)

# Degree families: what a qualification clause accepts. Rank is used only for "minimum" comparisons.
NOTICE_DEGREES: list[tuple[str, re.Pattern[str]]] = [
    ("phd", re.compile(r"(?i:\bph\.?\s?d\b|\bdoctorate\b)")),
    ("pg_engineering", re.compile(r"\bM\.?\s?Tech\b|\bM\.\s?E\.?(?=[\s/,(])|\bME\b(?=\s*/\s*M)|(?i:master(?:'|’)?s?\s+(?:degree\s+)?in\s+"
                                  r"(?:engineering|technology))")),
    ("pg", re.compile(r"\bMCA\b|\bM\.?\s?Sc\b|\bMBA\b|\bM\.?\s?Com\b|\bM\.?\s?A\.(?=[\s/,(])|"
                      r"(?i:post[- ]?graduat(?:e|ion)|master(?:'|’)?s?\s+degree)")),
    ("engineering", re.compile(r"\bB\.?\s?Tech\b|\bB\.\s?E\.?(?=[\s/,(])|\bBE\b(?=\s*[/(]|\s+(?:in|or)\b)|\bB\.?\s?Sc\.?\s*\(?\s*Engg|"
                               r"(?i:bachelor(?:'|’)?s?\s+(?:degree\s+)?(?:in|of)\s+(?:engineering|technology)|"
                               r"engineering\s+(?:degree|graduates?)|degree\s+in\s+engineering|graduate\s+engineers?|"
                               r"full[- ]time\s+(?:engineering|B\.?\s?E)|\bAMIE\b)")),
    ("graduate", re.compile(r"\bB\.?\s?Sc\b(?!\.?\s*\(?\s*Engg)|\bBCA\b|\bB\.?\s?Com\b|\bB\.?\s?A\.(?=[\s/,(])|\bBBA\b|"
                            r"(?i:\bgraduat(?:e|ion)\b(?!\s+engineer)|bachelor(?:'|’)?s?\s+degree(?!\s+(?:in|of)\s+"
                            r"(?:engineering|technology)))")),
    ("diploma", re.compile(r"(?i:\bdiploma\b)")),
    ("iti", re.compile(r"\bITI\b|(?i:\bNCVT\b|\btrade\s+certificate\b)")),
    ("class12", re.compile(r"(?i:\b12th\b|\b10\s*\+\s*2\b|\bintermediate\b|higher\s+secondary|\bHSC\b|senior\s+secondary)")),
    ("class10", re.compile(r"(?i:\b10th\b|matriculation|\bSSLC\b|\bSSC\s+pass|high\s+school\s+pass)")),
]
DEGREE_LABEL = {"phd": "PhD", "pg_engineering": "M.Tech / M.E.", "pg": "Postgraduate degree", "engineering": "B.Tech / B.E.",
                "graduate": "Bachelor's degree", "diploma": "Diploma", "iti": "ITI", "class12": "Class 12", "class10": "Class 10"}
QUALIFICATION_CUE = re.compile(r"\b(qualification|educational|eligib|degree|graduat|diploma|b\.?\s?tech|b\.?\s?e\b|"
                               r"discipline|branch|passed|pass\b|engineering)\b", re.I)

_CATEGORY_TOKEN = (r"(SC\s*/\s*ST(?:\s*/\s*(?:PwBD|PwD|PH))?|OBC\s*[\(\-]?\s*(?:NCL|Non[- ]Creamy\s+Layer)?\s*[\)]?|SC|ST|EWS|"
                   r"PwBD|PwD|PH\b|Persons?\s+with\s+(?:Benchmark\s+)?Disabilit(?:y|ies)|Ex[- ]?Service\s?m[ae]n|ExSM|ESM)")
_RELAX_AFTER = re.compile(_CATEGORY_TOKEN + r"(?:\s+(?:candidates?|category|categories|applicants?))?\s*(?:[:\-–]|by|upto|up\s+to|of|is)?\s*"
                          r"(\d{1,2})\s*(?:years?|yrs?)", re.I)
_RELAX_BEFORE = re.compile(r"(\d{1,2})\s*(?:years?|yrs?)\s+(?:for|in\s+(?:the\s+)?case\s+of|in\s+respect\s+of|to)\s+" + _CATEGORY_TOKEN +
                           r"(?:\s*(?:,|/|and|&)\s*" + _CATEGORY_TOKEN + r")?", re.I)
_AGE_RANGE = re.compile(r"(?:between\s+)?(\d{2})\s*(?:-|–|to|and)\s*(\d{2})\s*(?:years?|yrs?)", re.I)
_AGE_MAX = re.compile(r"(?:upper\s+age(?:\s+limit)?|max(?:imum)?\.?\s+age(?:\s+limit)?|age\s+limit|not\s+(?:exceed(?:ing)?|more\s+than|"
                      r"above|over)|should\s+not\s+(?:be\s+)?(?:exceed|more\s+than|above)|below|upto|up\s+to|age\s*[:\-–])"
                      r"[^0-9]{0,40}?(\d{2})\s*(?:years?|yrs?)", re.I)
_AGE_MIN = re.compile(r"(?:lower\s+age(?:\s+limit)?|min(?:imum)?\.?\s+age(?:\s+limit)?|not\s+(?:less|below)\s+than|at\s+least|"
                      r"should\s+have\s+(?:attained|completed))[^0-9]{0,40}?(\d{2})\s*(?:years?|yrs?)", re.I)
_AS_ON = re.compile(r"as\s+on\s+(?:the\s+)?(?:date\s+)?(?:\(?\s*i\.?e\.?\s*\)?\s*)?(" + DATE_RE + r")|(?:reckon(?:ed|ing)|"
                    r"crucial\s+date|cut[- ]?off\s+date)[^0-9]{0,60}(" + DATE_RE + r")", re.I)
_AS_ON_CLOSING = re.compile(r"as\s+on\s+(?:the\s+)?(?:last|closing)\s+date", re.I)
_PERCENT = re.compile(r"(?:min(?:imum)?\.?(?:\s+of)?|at\s+least|not\s+less\s+than|with|securing|aggregate\s+of)?\s*"
                      r"(\d{2}(?:\.\d{1,2})?)\s*(?:%|per\s?cent(?:age)?)\s*(?:marks?|aggregate)?", re.I)
_CGPA = re.compile(r"(?:min(?:imum)?\.?(?:\s+of)?\s+)?(?:CGPA|CPI|OGPA|GPA)(?:\s+of)?\s*(?:[:\-–]|of|not\s+less\s+than)?\s*"
                   r"(\d(?:\.\d{1,2})?)(?:\s*(?:/|on|out\s+of)\s*(?:a\s+)?(10|4)(?:\.0)?(?:[- ]point)?)?|"
                   r"(\d(?:\.\d{1,2})?)\s*(?:CGPA|CPI)", re.I)
GATE_PAPERS = {"AE", "AG", "AR", "BM", "BT", "CE", "CH", "CS", "CY", "DA", "EC", "EE", "ES", "EY", "GE", "GG", "IN",
               "MA", "ME", "MN", "MT", "NM", "PE", "PH", "PI", "ST", "TF", "XE", "XH", "XL"}
_GATE = re.compile(r"\bGATE\b", re.I)
_GATE_YEAR = re.compile(r"GATE\s*[-–]?\s*((?:20)\d{2})(?:\s*(?:/|,|or|and|&)\s*(?:GATE\s*[-–]?\s*)?((?:20)\d{2}))?"
                        r"(?:\s*(?:/|,|or|and|&)\s*(?:GATE\s*[-–]?\s*)?((?:20)\d{2}))?", re.I)
_GATE_SCORE = re.compile(r"(?:min(?:imum)?\.?|qualifying|cut[- ]?off|at\s+least)\s+(?:GATE\s+)?(?:score|marks)\s*(?:of|[:\-–])?\s*"
                         r"(\d{2,4}(?:\.\d{1,2})?)|GATE\s+score\s+of\s+(?:at\s+least\s+)?(\d{2,4}(?:\.\d{1,2})?)", re.I)
_GATE_NOT = re.compile(r"GATE\s+(?:score\s+)?(?:is\s+)?not\s+(?:required|mandatory|necessary)|without\s+GATE", re.I)
_FINAL_YES = re.compile(r"(?:final[- ](?:year|semester)|appearing|result\s+awaited)(?:[^.]|\.\d){0,140}?"
                        r"(?:can|may|are\s+(?:also\s+)?eligible\s+to|are\s+allowed\s+to|eligible)\s*(?:also\s+)?(?:apply|appl)?", re.I)
_FINAL_NO = re.compile(r"(?:final[- ](?:year|semester)|appearing|result(?:s)?\s+(?:is\s+|are\s+)?awaited)(?:[^.]|\.\d){0,120}?"
                       r"(?:not\s+eligible|need\s+not\s+apply|shall\s+not\s+apply|cannot\s+apply|are\s+not\s+allowed|will\s+not\s+be\s+considered)",
                       re.I)
_NATIONALITY = re.compile(r"\b(?:only\s+indian\s+(?:nationals?|citizens?)|indian\s+(?:nationals?|citizens?)\s+(?:only|are\s+eligible)|"
                          r"(?:must|should)\s+be\s+(?:a\s+|an\s+)?(?:citizen\s+of\s+india|indian\s+(?:national|citizen))|"
                          r"nationality\s*[:\-–]\s*indian)\b", re.I)
STATES = ["Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat", "Haryana",
          "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur",
          "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana",
          "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal", "Delhi", "Jammu and Kashmir", "Ladakh", "Puducherry"]
_DOMICILE = re.compile(r"(?:domiciled?|permanent\s+residents?|bonafide\s+residents?|original\s+inhabitants?|"
                       r"permanent\s+resident\s+certificate|\bPRC\b)\s+(?:of|in|from)\s+(?:the\s+)?(?:state\s+of\s+)?(" +
                       "|".join(re.escape(s) for s in STATES) + r")\b", re.I)
_GENDER = re.compile(r"\b(?:only\s+(female|women|male|men)\s+candidates?|(female|women|male|men)\s+candidates?\s+only|"
                     r"(?:open|applicable)\s+(?:only\s+)?(?:to|for)\s+(female|women|male|men)\s+candidates?(?:\s+only)?)\b", re.I)
_PWD_ONLY = re.compile(r"special\s+recruitment\s+drive\s+for\s+(?:PwBD|PwD|persons?\s+with)|only\s+(?:for\s+)?(?:PwBD|PwD)\s+candidates|"
                       r"reserved\s+(?:exclusively\s+)?for\s+(?:PwBD|PwD|persons?\s+with\s+(?:benchmark\s+)?disabilit)", re.I)
_EXSM_ONLY = re.compile(r"only\s+(?:for\s+)?ex[- ]?service\s?m[ae]n|ex[- ]?service\s?m[ae]n\s+only|"
                        r"reserved\s+(?:exclusively\s+)?for\s+ex[- ]?service\s?m[ae]n", re.I)
_EXP_MONTHS = re.compile(r"(\d{1,2})\s*months?(?:'|’)?\s+(?:of\s+)?(?:post[- ]qualification\s+)?(?:work\s+)?experience", re.I)
_EXP_YEARS = re.compile(r"(?:min(?:imum)?\.?(?:\s+of)?|at\s+least|not\s+less\s+than)?\s*(\d{1,2})\s*\+?\s*(?:years?|yrs?)(?:'|’)?\s+"
                        r"(?:of\s+)?(?:post[- ]qualification\s+|relevant\s+|work(?:ing)?\s+|professional\s+|industrial\s+)*experience", re.I)
_EXP_MAX = re.compile(r"(?:max(?:imum)?\.?(?:\s+of)?|not\s+more\s+than|up\s?to|less\s+than)\s*(\d{1,2})\s*(?:years?|yrs?)(?:'|’)?\s+"
                      r"(?:of\s+)?(?:work\s+)?experience", re.I)
_EXP_NONE = re.compile(r"\b(?:no\s+(?:prior\s+|work\s+)?experience\s+(?:is\s+)?(?:required|necessary|needed)|"
                       r"experience\s*[:\-–]\s*(?:nil|not\s+required|none)|fresh(?:ers?)?\s+(?:candidates?\s+)?(?:can|may|are\s+eligible)|"
                       r"freshers?\s+(?:can\s+)?(?:also\s+)?apply)\b", re.I)
_INTERN_COUNT = re.compile(r"(internship|apprentice(?:ship)?|training)[^.]{0,80}?(?:will|shall)\s+(not\s+)?be\s+"
                           r"(?:counted|considered|treated|reckoned)", re.I)
_OPEN_DATE = re.compile(r"(?:opening\s+date|start(?:ing)?\s+date|commencement|date\s+of\s+commencement|online\s+registration\s+"
                        r"(?:starts?|opens?|begins?|from)|applications?\s+(?:opens?|starts?|begins?)|apply\s+online\s+from|"
                        r"from\s+(?=\d))[^0-9]{0,70}(" + DATE_RE + ")", re.I)
_CLOSE_DATE = re.compile(r"(?:last\s+date|closing\s+date|close\s+date|end\s+date|deadline|closes?\s+on|on\s+or\s+before|"
                         r"apply\s+(?:online\s+)?(?:by|before|till|until|upto|up\s+to)|latest\s+by|\bto\s+(?=\d)|\btill\s+(?=\d)|"
                         r"\bupto\s+(?=\d))[^0-9]{0,90}(" + DATE_RE + ")", re.I)
_EXAM_DATE = re.compile(r"(?:date\s+of\s+(?:written\s+|online\s+|computer\s+based\s+)?(?:examination|exam|test|CBT)|"
                        r"(?:exam(?:ination)?|test|CBT)\s+date)[^0-9]{0,60}(" + DATE_RE + ")", re.I)
_ADV = re.compile(r"(?:Advertisement|Advt\.?|Rectt\.?\s*Advt\.?|Recruitment\s+Notice|Employment\s+Notice|Notification|Notice|"
                  r"Ref(?:erence)?\.?)\s*(?:No\.?|Number|#)\s*[:.\-–]?\s*([A-Za-z0-9][A-Za-z0-9./()\-_ ]{1,48}?\d[A-Za-z0-9/()\-_]{0,12})"
                  r"(?=\s|$|[,;:])", re.I)
_VACANCIES = re.compile(r"(?:total\s+)?(?:no\.?\s+of\s+|number\s+of\s+)?(?:vacanc(?:y|ies)|posts?)\s*[:\-–]\s*(\d{1,5})\b|"
                        r"\b(\d{1,5})\s+(?:vacanc(?:y|ies)|posts)\b", re.I)
_PAY = re.compile(r"(?:pay\s+(?:level|scale|matrix)|level)\s*[-–:]?\s*(\d{1,2}[A-Z]?)\b|"
                  r"((?:Rs\.?|₹|INR)\s?[\d,]{4,9}\s*(?:/-)?\s*(?:-|–|to)\s*(?:Rs\.?|₹|INR)?\s?[\d,]{4,9})|"
                  r"\b(E-?\d|S-?\d{1,2}|W-?\d{1,2})\s+grade\b", re.I)
_POST = re.compile(r"(?i:recruitment|engagement|selection|appointment|hiring|applications?\s+(?:are\s+)?invited)\s+"
                   r"(?i:of|to|for)\s+(?i:the\s+)?(?i:posts?\s+of\s+)?([A-Z][A-Za-z0-9&()/.,'\- ]{3,110}?)"
                   r"(?=\s+(?:through|in\s+the|on\s+(?:contract|regular|deputation|direct)|at\b|for\s+the\s+year|against|"
                   r"vide|under|[-–]\s|\(\s*advt)|[.:;]|$)|"
                   r"(?i:for|to)\s+(?i:the\s+)posts?\s+of\s+([A-Z][A-Za-z0-9&()/.,'\- ]{3,110}?)(?=\s+(?:in|on|at|through|against)\b|[.:;]|$)")


def _category_keys(token: str) -> list[str]:
    """Reservation groups named by one token of a relaxation clause."""
    t = re.sub(r"\s+", "", token).casefold()
    keys: list[str] = []
    if "sc/st" in t:
        keys += ["SC", "ST"]
        if any(x in t for x in ("pwbd", "pwd", "ph")):
            keys.append("PwD")
    elif t.startswith("obc"):
        keys.append("OBC-NCL")
    elif t == "sc":
        keys.append("SC")
    elif t == "st":
        keys.append("ST")
    elif t == "ews":
        keys.append("EWS")
    elif t in {"pwbd", "pwd", "ph"} or t.startswith("person"):
        keys.append("PwD")
    elif t.startswith(("ex", "esm")):
        keys.append("Ex-Serviceman")
    return keys


def notice_branches(text: str) -> list[str]:
    return [code for code, pattern in BRANCHES.items() if pattern.search(text or "")]


def notice_degrees(text: str) -> list[str]:
    return [code for code, pattern in NOTICE_DEGREES if pattern.search(text or "")]


def extract_notice_requirements(text: str) -> dict[str, Any]:
    """Structured eligibility clauses of a recruitment/examination notification, each with its evidence quote.

    Absent keys mean "the notification text does not state this" — never "no requirement"."""
    text = str(text or "")
    sentences = _sentences(text)
    out: dict[str, Any] = {}

    # ---- age
    age: dict[str, Any] = {}
    relax: dict[str, int] = {}
    relax_evidence = ""
    for sentence in sentences:
        lowered = sentence.casefold()
        if "relax" in lowered or re.search(r"upper\s+age\s+limit\s+is\s+relax", lowered):
            for match in _RELAX_AFTER.finditer(sentence):
                years = int(match.group(2))
                if 1 <= years <= 20:
                    for key in _category_keys(match.group(1)):
                        relax.setdefault(key, years)
                    relax_evidence = relax_evidence or _quote(sentence)
            for match in _RELAX_BEFORE.finditer(sentence):
                years = int(match.group(1))
                if 1 <= years <= 20:
                    for token in (match.group(2), match.group(3)):
                        for key in _category_keys(token or ""):
                            relax.setdefault(key, years)
                    relax_evidence = relax_evidence or _quote(sentence)
            continue
        if "age" not in lowered and "years old" not in lowered:
            continue
        if re.search(r"\b(experience|service|retire|superannuat)\b", lowered) and "age limit" not in lowered \
                and "upper age" not in lowered:
            continue
        found = _AGE_RANGE.search(sentence)
        if found and 14 <= int(found.group(1)) < int(found.group(2)) <= 70:
            age.setdefault("min", int(found.group(1)))
            age.setdefault("max", int(found.group(2)))
            age.setdefault("evidence", _quote(sentence))
        else:
            found = _AGE_MAX.search(sentence)
            if found and 17 <= int(found.group(1)) <= 70 and not _AGE_MIN.search(sentence[:found.start(1)][-45:]):
                age.setdefault("max", int(found.group(1)))
                age.setdefault("evidence", _quote(sentence))
            found = _AGE_MIN.search(sentence)
            if found and 14 <= int(found.group(1)) <= 60:
                age.setdefault("min", int(found.group(1)))
                age.setdefault("evidence", _quote(sentence))
        if age and "as_on" not in age:
            found = _AS_ON.search(sentence)
            if found:
                as_on = _iso(found.group(1) or found.group(2))
                if as_on:
                    age["as_on"] = as_on
            elif _AS_ON_CLOSING.search(sentence):
                age["as_on_closing"] = True
    if age and "as_on" not in age:
        found = re.search(r"\bage\b[^.]{0,160}?" + _AS_ON.pattern, text, re.I | re.S)
        if found:
            as_on = _iso(found.group(1) or found.group(2))
            if as_on:
                age["as_on"] = as_on
    if age.get("min") is not None or age.get("max") is not None:
        out["age"] = age
        if relax:
            out["age_relaxation"] = {"years": relax, "evidence": relax_evidence}

    # ---- qualification (degree families + branches)
    degrees: list[str] = []
    branches: list[str] = []
    any_branch = any_degree = equivalent = False
    qualification_evidence: list[str] = []
    for sentence in sentences:
        if not QUALIFICATION_CUE.search(sentence) or len(sentence) > 700:
            continue
        found_degrees = notice_degrees(sentence)
        found_branches = notice_branches(sentence)
        sentence_any = bool(ANY_BRANCH.search(sentence))
        sentence_any_degree = bool(ANY_DEGREE.search(sentence))
        if not (found_degrees or sentence_any or sentence_any_degree):
            # A line that only lists branches continues the previous qualification clause ("Discipline: CSE / IT").
            if found_branches and degrees and re.search(r"\b(discipline|branch|stream|speciali[sz]ation|trade)\b", sentence, re.I):
                branches += [b for b in found_branches if b not in branches]
                qualification_evidence.append(_quote(sentence))
            continue
        if re.search(r"\b(desirable|preferable|preferred|additional\s+weightage)\b", sentence, re.I) and degrees:
            continue  # desirable qualifications never tighten the essential ones
        degrees += [d for d in found_degrees if d not in degrees]
        branches += [b for b in found_branches if b not in branches]
        any_branch = any_branch or sentence_any
        any_degree = any_degree or sentence_any_degree
        equivalent = equivalent or bool(EQUIVALENT_BRANCH.search(sentence))
        qualification_evidence.append(_quote(sentence))
    if degrees or any_degree or any_branch:
        if any_degree and "graduate" not in degrees:
            degrees.append("graduate")
        out["qualification"] = {"degrees": degrees, "branches": [] if any_branch else branches, "any_branch": any_branch,
                                "any_degree": any_degree, "equivalent_allowed": equivalent,
                                "evidence": " … ".join(dict.fromkeys(qualification_evidence))[:520]}

    # ---- percentage / CGPA
    for sentence in sentences:
        if not re.search(r"\b(marks?|aggregate|percent|cgpa|cpi|class|division)\b|%", sentence, re.I):
            continue
        if re.search(r"\b(reservation|vacanc|fee|tax|interest|disabilit|hra|da\b|increment)\b", sentence, re.I) and \
                not re.search(r"\bmarks?\b|aggregate|cgpa", sentence, re.I):
            continue
        values = [(float(m.group(1)), m) for m in _PERCENT.finditer(sentence) if 33 <= float(m.group(1)) <= 95]
        if values and re.search(r"\b(marks?|aggregate|degree|graduat|qualif|engineering|b\.?\s?tech|class|division)\b", sentence, re.I):
            minimum, first = values[0]
            entry: dict[str, Any] = {"min": minimum, "evidence": _quote(sentence)}
            relaxed: dict[str, float] = {}
            for value, match in values[1:]:
                tail = sentence[match.end():match.end() + 70]
                token = re.search(_CATEGORY_TOKEN, tail, re.I) or re.search(_CATEGORY_TOKEN, sentence[max(0, match.start() - 60):match.start()], re.I)
                if token and value < minimum:
                    for key in _category_keys(token.group(1)):
                        relaxed[key] = value
                    more = re.findall(_CATEGORY_TOKEN, tail, re.I)
                    for extra in more:
                        for key in _category_keys(extra):
                            relaxed[key] = value
            if relaxed:
                entry["relaxed"] = relaxed
            out.setdefault("percentage", entry)
        found = _CGPA.search(sentence)
        if found and re.search(r"\b(min|at\s+least|not\s+less|with|above|or\s+equivalent|required)\b", sentence, re.I):
            value = float(found.group(1) or found.group(3))
            scale = int(found.group(2) or 10)
            if 0 < value <= scale:
                out.setdefault("cgpa", {"min": value, "scale": scale, "evidence": _quote(sentence)})

    # ---- final-year / batch
    found = _FINAL_NO.search(text)
    if found:
        out["final_year"] = {"allowed": False, "evidence": _quote(" ".join(text[max(0, found.start() - 40):found.end() + 60].split()))}
    else:
        found = _FINAL_YES.search(text)
        if found and re.search(r"apply|eligible", found.group(0), re.I):
            out["final_year"] = {"allowed": True, "evidence": _quote(" ".join(text[max(0, found.start() - 40):found.end() + 60].split()))}
    batches = sorted({int(g) for m in BATCH.finditer(text) for g in m.groups() if g and 2000 <= int(g) <= 2100})
    if batches:
        first = BATCH.search(text)
        out["batches"] = {"years": batches[:6], "evidence": _quote(" ".join(text[max(0, first.start() - 60):first.end() + 60].split()))}

    # ---- GATE
    if _GATE.search(text) and not _GATE_NOT.search(text):
        gate_sentences = [s for s in sentences if _GATE.search(s)]
        required = any(re.search(r"\b(valid|qualified|must|should|required|through|based\s+on|score|appeared|mandatory|"
                                 r"essential|shortlist)\b", s, re.I) for s in gate_sentences)
        if required:
            papers: list[str] = []
            years: list[int] = []
            score = None
            for sentence in gate_sentences:
                for match in re.finditer(r"\(\s*([A-Z]{2})\s*\)|(?:[Pp]apers?|[Cc]odes?|[Dd]isciplines?|[Ss]ubjects?)\s*(?:code)?\s*[:\-–]?\s*"
                                         r"([A-Z]{2}(?:\s*[/,]\s*[A-Z]{2})*)\b|\bin\s+([A-Z]{2}(?:\s*[/,]\s*[A-Z]{2})*)\b",
                                         sentence):
                    loose = match.group(1) is None  # outside parentheses "ST"/"PH" are reservation groups, not papers
                    for code in re.findall(r"[A-Z]{2}", next(g for g in match.groups() if g)):
                        if code in GATE_PAPERS and code not in papers and not (loose and code in {"ST", "PH", "IN"}):
                            papers.append(code)
                for match in _GATE_YEAR.finditer(sentence):
                    years += [int(g) for g in match.groups() if g and int(g) not in years]
                found = _GATE_SCORE.search(sentence)
                if found and score is None:
                    score = float(found.group(1) or found.group(2))
            out["gate"] = {"required": True, "papers": papers, "years": sorted(years), "min_score": score,
                           "evidence": _quote(" … ".join(gate_sentences[:2]), 320)}

    # ---- experience
    exp: dict[str, Any] = {}
    for sentence in sentences:
        if "experience" not in sentence.casefold():
            continue
        if _EXP_NONE.search(sentence):
            exp.setdefault("min_months", 0)
            exp.setdefault("evidence", _quote(sentence))
            continue
        if re.search(r"\b(desirable|preferable|preferred|weightage|will\s+be\s+an\s+added)\b", sentence, re.I):
            continue
        found = _EXP_MAX.search(sentence)
        if found:
            exp.setdefault("max_months", int(found.group(1)) * 12)
            exp.setdefault("evidence", _quote(sentence))
            continue
        found = _EXP_YEARS.search(sentence)
        if found and 0 < int(found.group(1)) <= 40:
            exp.setdefault("min_months", int(found.group(1)) * 12)
            exp.setdefault("evidence", _quote(sentence))
            continue
        found = _EXP_MONTHS.search(sentence)
        if found and 0 < int(found.group(1)) <= 120:
            exp.setdefault("min_months", int(found.group(1)))
            exp.setdefault("evidence", _quote(sentence))
    found = _INTERN_COUNT.search(text)
    if found and exp:
        exp["internships_count"] = not bool(found.group(2))
    if exp:
        out["experience"] = exp

    # ---- nationality, domicile, gender, PwD / ex-serviceman only
    found = _NATIONALITY.search(text)
    if found:
        out["nationality"] = {"required": "Indian", "evidence": _quote(" ".join(text[max(0, found.start() - 40):found.end() + 40].split()))}
    found = _DOMICILE.search(text)
    if found:
        state = next(s for s in STATES if s.casefold() == " ".join(found.group(1).split()).casefold())
        out["domicile"] = {"state": state, "evidence": _quote(" ".join(text[max(0, found.start() - 60):found.end() + 40].split()))}
    found = _GENDER.search(text)
    if found:
        word = next(g for g in found.groups() if g).casefold()
        out["gender"] = {"only": "female" if word in {"female", "women"} else "male",
                         "evidence": _quote(" ".join(text[max(0, found.start() - 40):found.end() + 40].split()))}
    found = _PWD_ONLY.search(text)
    if found:
        out["pwd_only"] = {"evidence": _quote(" ".join(text[max(0, found.start() - 40):found.end() + 60].split()))}
    found = _EXSM_ONLY.search(text)
    if found:
        out["ex_serviceman_only"] = {"evidence": _quote(" ".join(text[max(0, found.start() - 40):found.end() + 60].split()))}
    return out


def extract_notice_fields(text: str, *, title: str = "") -> dict[str, Any]:
    """Descriptive fields of a notification (never eligibility): advertisement number, posts, vacancies, pay, dates.

    Every value is copied from the text; ``provenance`` maps each field to the clause it was read from."""
    text = str(text or "")
    head = f"{title}\n{text}"
    fields: dict[str, Any] = {}
    provenance: dict[str, str] = {}

    def keep(name: str, value: Any, match: re.Match[str], source: str) -> None:
        if value in (None, "") or name in fields:
            return
        fields[name] = value
        provenance[name] = " ".join(source[max(0, match.start() - 50):match.end() + 50].split())[:240]

    found = _ADV.search(head)
    if found:
        number = found.group(1).strip(" .-–")
        number = re.sub(r"(?<=\d)[A-Z][a-z]{3,}.*$", "", number)  # "17/26Recruitment": words glued on by PDF text
        number = re.sub(r"\s+(?:dated|dt\.?|date)\b.*$", "", number, flags=re.I)
        if number.count(")") > number.count("("):
            number = number.rstrip(")")
        if number.count("(") > number.count(")"):
            number = number[:number.rindex("(")]
        number = number.strip(" .-–/")
        if re.search(r"\d", number) and len(number) >= 3:
            keep("advertisement_number", number[:60], found, head)
    found = _POST.search(head)
    if found:
        post = (found.group(1) or found.group(2) or "").strip(" .,-–")
        if 3 < len(post) <= 110:
            keep("post_name", post, found, head)
    total = None
    for match in _VACANCIES.finditer(text):
        value = int(match.group(1) or match.group(2))
        if 0 < value <= 99999 and (total is None or re.search(r"total", text[max(0, match.start() - 20):match.end()], re.I)):
            total = total if total and not re.search(r"total", text[max(0, match.start() - 20):match.end()], re.I) else value
            keep("vacancies", str(value), match, text)
    if total and fields.get("vacancies") != str(total):
        fields["vacancies"] = str(total)
    found = _PAY.search(text)
    if found:
        pay = found.group(0).strip()
        keep("salary", " ".join(pay.split())[:120], found, text)
    for name, pattern in (("opening_date", _OPEN_DATE), ("closing_date", _CLOSE_DATE), ("exam_date", _EXAM_DATE)):
        for match in pattern.finditer(text):
            if name == "closing_date" and re.search(r"\b(age|born|birth|reckon|as\s+on|experience|qualification)\b",
                                                    text[max(0, match.start() - 60):match.start() + 30], re.I):
                continue  # "age as on / not later than <date>" is not an application deadline
            value = _iso(match.group(1))
            if value:
                keep(name, value, match, text)
                break
    if fields.get("opening_date") and fields.get("closing_date") and fields["closing_date"] < fields["opening_date"]:
        fields.pop("closing_date")
        provenance.pop("closing_date", None)
    fields["provenance"] = provenance
    return fields
