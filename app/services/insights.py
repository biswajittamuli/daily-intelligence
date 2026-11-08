"""Deterministic job-market aggregation for the infographics page.

The numbers are computed only from stored job listings; no model is involved.
Skills are read from the listing's ``skills`` field and, when that is empty,
from distinctive title tokens. Counts are per listing, not per mention.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import date
from typing import Any

from app.services.freshness import parse_date

ROLE_FAMILIES: list[tuple[str, re.Pattern[str] | None]] = [
    ("AI / ML", re.compile(r"\b(ai|a\.i\.|ml|machine learning|deep learning|llm|genai|"
                           r"generative|nlp|computer vision|agentic|data scientist)\b", re.I)),
    ("Data", re.compile(r"\b(data engineer|data analyst|analytics|big data|bi)\b", re.I)),
    ("Full-stack", re.compile(r"\bfull[- ]?stack\b", re.I)),
    ("Backend", re.compile(r"\b(backend|back[- ]end|server|api|python developer|java developer|"
                           r"golang|node(?:\.js)?|django|flask|fastapi)\b", re.I)),
    ("Frontend", re.compile(r"\b(frontend|front[- ]end|react|angular|vue|ui developer|web developer)\b", re.I)),
    ("DevOps / Cloud", re.compile(r"\b(devops|sre|platform engineer|cloud|aws|azure|kubernetes|"
                                  r"infrastructure)\b", re.I)),
    ("Mobile", re.compile(r"\b(android|ios|mobile|flutter|react native)\b", re.I)),
    ("Security", re.compile(r"\b(security|cyber|soc analyst|penetration)\b", re.I)),
    ("Research", re.compile(r"\b(research|phd|postdoc)\b", re.I)),
    ("QA / Testing", re.compile(r"\b(qa|sdet|test(?:ing)? engineer|quality assurance|automation tester)\b", re.I)),
    ("Product / Program", re.compile(r"\b(product manager|program manager|project manager|scrum)\b", re.I)),
    ("Software (general)", re.compile(r"\b(software (?:engineer|developer)|sde|programmer|swe)\b", re.I)),
]

SKILL_ALIASES = {
    "py": "Python", "python": "Python", "java": "Java", "javascript": "JavaScript",
    "js": "JavaScript", "typescript": "TypeScript", "ts": "TypeScript", "c++": "C++",
    "c#": "C#", "golang": "Go", "go": "Go", "rust": "Rust", "sql": "SQL",
    "nosql": "NoSQL", "pytorch": "PyTorch", "tensorflow": "TensorFlow", "keras": "Keras",
    "sklearn": "scikit-learn", "scikit-learn": "scikit-learn", "pandas": "Pandas",
    "numpy": "NumPy", "fastapi": "FastAPI", "flask": "Flask", "django": "Django",
    "node": "Node.js", "nodejs": "Node.js", "react": "React", "angular": "Angular",
    "vue": "Vue", "docker": "Docker", "kubernetes": "Kubernetes", "k8s": "Kubernetes",
    "aws": "AWS", "azure": "Azure", "gcp": "GCP", "linux": "Linux", "git": "Git",
    "llm": "LLMs", "llms": "LLMs", "rag": "RAG", "mcp": "MCP", "langchain": "LangChain",
    "agentic": "Agentic AI", "agents": "Agentic AI", "nlp": "NLP",
    "computer vision": "Computer Vision", "deep learning": "Deep Learning",
    "machine learning": "Machine Learning", "mlops": "MLOps", "hugging face": "Hugging Face",
    "transformers": "Transformers", "spark": "Spark", "hadoop": "Hadoop", "kafka": "Kafka",
    "redis": "Redis", "postgresql": "PostgreSQL", "postgres": "PostgreSQL",
    "mongodb": "MongoDB", "mysql": "MySQL", "terraform": "Terraform", "ci/cd": "CI/CD",
    "rest": "REST", "graphql": "GraphQL", "microservices": "Microservices", "agile": "Agile",
    "sqlalchemy": "SQLAlchemy", "celery": "Celery", "airflow": "Airflow",
}

TITLE_SKILL_HINTS = [
    ("LLMs", re.compile(r"\b(llm|large language model|genai|generative ai)\b", re.I)),
    ("Agentic AI", re.compile(r"\b(agent|agentic)\b", re.I)),
    ("Machine Learning", re.compile(r"\b(machine learning|ml engineer|mlops)\b", re.I)),
    ("Deep Learning", re.compile(r"\b(deep learning)\b", re.I)),
    ("NLP", re.compile(r"\b(nlp|natural language)\b", re.I)),
    ("Computer Vision", re.compile(r"\b(computer vision|vision)\b", re.I)),
    ("PyTorch", re.compile(r"\bpytorch\b", re.I)),
    ("Python", re.compile(r"\bpython\b", re.I)),
    ("RAG", re.compile(r"\brag\b|retrieval augmented", re.I)),
    ("MCP", re.compile(r"\bmcp\b", re.I)),
    ("FastAPI", re.compile(r"\bfastapi\b", re.I)),
    ("Data", re.compile(r"\b(data|analytics)\b", re.I)),
]

JOB_BOARD_HINTS = ("wellfound", "naukri", "indeed", "linkedin", "workatastartup",
                   "glassdoor", "monster", "ziprecruiter", "foundit", "instahyre",
                   "cutshort", "hirist", "timesjobs", "shine.com", "simplyhired")


def _skill_name(value: str) -> str | None:
    clean = " ".join(str(value or "").split()).strip(" .,/|-")
    if not clean or len(clean) > 40:
        return None
    return SKILL_ALIASES.get(clean.casefold(), clean[:1].upper() + clean[1:] if clean.islower() else clean)


def _job_skills(job: dict[str, Any]) -> set[str]:
    skills: set[str] = set()
    for raw in job.get("skills") or []:
        name = _skill_name(str(raw))
        if name:
            skills.add(name)
    if not skills:
        title = str(job.get("title") or "")
        for name, pattern in TITLE_SKILL_HINTS:
            if pattern.search(title):
                skills.add(name)
    return skills


def role_family(title: str) -> str:
    return _role_family(title)


def _role_family(title: str) -> str:
    for name, pattern in ROLE_FAMILIES:
        if pattern and pattern.search(title):
            return name
    return "Other"


def _portal_name(job: dict[str, Any]) -> str:
    value = str(job.get("source_platform") or "").strip().lower()
    if not value:
        return "Unknown source"
    value = value.removeprefix("www.").removeprefix("https://").removeprefix("http://").strip("/")
    return value.split("/")[0] or "Unknown source"


def _portal_kind(domain: str) -> str:
    return "Job board" if any(hint in domain for hint in JOB_BOARD_HINTS) else "Company / other"


def _location(value: str) -> str:
    clean = " ".join(str(value or "").split())
    if not clean:
        return "Not stated"
    return clean.split(",")[0].strip()[:60] or "Not stated"


def _freshness_bucket(posted: Any, today: date) -> str:
    value = parse_date(posted)
    if value is None:
        return "Undated"
    days = (today - value).days
    if days < 0:
        return "Future-dated"
    if days <= 7:
        return "This week"
    if days <= 30:
        return "This month"
    if days <= 90:
        return "Last 90 days"
    return "Older"


def _top(counter: Counter[str], limit: int = 12) -> list[dict[str, Any]]:
    return [{"name": name, "count": count}
            for name, count in counter.most_common(limit) if name and count]


def _week_start(value: date) -> date:
    return value.fromordinal(value.toordinal() - value.weekday())


def job_market(jobs: list[dict[str, Any]], *, today: date | None = None,
               resumes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    today = today or date.today()
    resumes = resumes or []
    skills: Counter[str] = Counter()
    roles: Counter[str] = Counter()
    portals: Counter[str] = Counter()
    locations: Counter[str] = Counter()
    freshness: Counter[str] = Counter()
    status: Counter[str] = Counter()
    skill_by_portal: dict[str, Counter[str]] = {}
    skill_by_role: dict[str, Counter[str]] = {}
    skill_by_kind: dict[str, Counter[str]] = {"Job board": Counter(), "Company / other": Counter()}
    employers: Counter[str] = Counter()
    weekly: Counter[str] = Counter()

    for job in jobs:
        title = str(job.get("title") or "")
        family = _role_family(title)
        roles[family] += 1
        portal = _portal_name(job)
        portals[portal] += 1
        kind = _portal_kind(portal)
        if job.get("employer"):
            employers[" ".join(str(job["employer"]).split())[:60]] += 1
        seen_on = parse_date(job.get("posted_date")) or parse_date(str(job.get("first_seen") or "")[:10])
        if seen_on and 0 <= (today - seen_on).days <= 84:
            weekly[_week_start(seen_on).isoformat()] += 1
        locations[_location(str(job.get("location") or ""))] += 1
        freshness[_freshness_bucket(job.get("posted_date"), today)] += 1
        status[str(job.get("status") or "unverified")] += 1
        job_skills = _job_skills(job)
        skills.update(job_skills)
        skill_by_portal.setdefault(portal, Counter()).update(job_skills)
        skill_by_role.setdefault(family, Counter()).update(job_skills)
        skill_by_kind[kind].update(job_skills)

    top_skills = _top(skills, 12)
    top_portals = _top(portals, 8)
    skill_names = [item["name"] for item in top_skills[:8]]
    portal_names = [item["name"] for item in top_portals[:6]]
    matrix = [[skill_by_portal.get(portal, Counter()).get(skill, 0) for skill in skill_names]
              for portal in portal_names]

    role_names = [item["name"] for item in _top(roles, 8) if item["name"] != "Other"][:7]
    role_matrix = [[skill_by_role.get(role, Counter()).get(skill, 0) for skill in skill_names]
                   for role in role_names]
    board_vs_company = [{"name": skill,
                         "board": skill_by_kind["Job board"].get(skill, 0),
                         "company": skill_by_kind["Company / other"].get(skill, 0)}
                        for skill in [item["name"] for item in top_skills[:10]]]
    weeks = []
    start = _week_start(today)
    for offset in range(11, -1, -1):
        week = start.fromordinal(start.toordinal() - 7 * offset)
        weeks.append({"name": week.isoformat(), "count": weekly.get(week.isoformat(), 0)})

    resume_skills: set[str] = set()
    for resume in resumes:
        profile = resume.get("profile") or {}
        for key in ("skills", "frameworks", "languages", "keywords"):
            resume_skills.update(" ".join(str(item).split()).casefold() for item in profile.get(key) or [])
    gap = [{"name": item["name"], "count": item["count"]} for item in _top(skills, 30)
           if resumes and item["name"].casefold() not in resume_skills][:10]
    have = [{"name": item["name"], "count": item["count"]} for item in _top(skills, 30)
            if resumes and item["name"].casefold() in resume_skills][:10]

    resume_fit: list[dict[str, Any]] = []
    if resumes:
        by_resume: dict[Any, dict[str, list[int]]] = {}
        for job in jobs:
            family = _role_family(str(job.get("title") or ""))
            for entry in job.get("resume_scores") or []:
                if isinstance(entry, dict) and entry.get("score") is not None:
                    by_resume.setdefault(entry.get("label"), {}).setdefault(family, []).append(int(entry["score"]))
        for label, families in by_resume.items():
            resume_fit.append({"label": label, "families": {
                family: round(sum(values) / len(values)) for family, values in families.items()}})

    best_resume_counts: Counter[str] = Counter(
        str(job.get("best_resume_label")) for job in jobs if job.get("best_resume_label"))

    total = len(jobs)
    recent = sum(count for label, count in freshness.items()
                 if label in {"This week", "This month"})
    dated = total - freshness.get("Undated", 0)
    return {
        "totals": {
            "listings": total,
            "recent_30d": recent,
            "dated": dated,
            "undated": freshness.get("Undated", 0),
            "portals": len(portals),
            "roles": len([name for name in roles if name != "Other"]),
            "skills": len(skills),
            "recent_ratio": round(recent / total * 100) if total else 0,
        },
        "roles": _top(roles, 12),
        "skills": top_skills,
        "portals": [{"name": item["name"], "count": item["count"],
                     "kind": _portal_kind(item["name"])} for item in top_portals],
        "locations": _top(locations, 10),
        "freshness": [{"name": name, "count": freshness.get(name, 0)}
                      for name in ("This week", "This month", "Last 90 days", "Older",
                                   "Future-dated", "Undated")],
        "status": [{"name": name, "count": count} for name, count in status.most_common()],
        "skills_by_portal": {"portals": portal_names, "skills": skill_names, "matrix": matrix},
        "skills_by_role": {"roles": role_names, "skills": skill_names, "matrix": role_matrix},
        "board_vs_company": board_vs_company,
        "weekly": weeks,
        "employers": _top(employers, 10),
        "skill_gap": gap,
        "skill_strengths": have,
        "resume_fit": resume_fit,
        "best_resume": _top(best_resume_counts, 6),
        "recent": sorted(
            (job for job in jobs if job.get("posted_date")),
            key=lambda job: str(job.get("posted_date")), reverse=True,
        )[:8],
    }
