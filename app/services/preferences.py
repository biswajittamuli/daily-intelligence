"""Editable, persisted preference model for discovery categories."""
from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from app.memory.store import Store


DEFAULT_PORTALS = {
    "Wellfound": {"domain": "wellfound.com", "enabled": True},
    "Naukri": {"domain": "naukri.com", "enabled": True},
    "Indeed": {"domain": "indeed.com", "enabled": True},
    "LinkedIn Jobs": {"domain": "linkedin.com/jobs", "enabled": True},
    "YC Work at a Startup": {"domain": "workatastartup.com", "enabled": True},
    "foundit": {"domain": "foundit.in", "enabled": True},
    "Instahyre": {"domain": "instahyre.com", "enabled": True},
    "Cutshort": {"domain": "cutshort.io", "enabled": True},
    "Hirist": {"domain": "hirist.tech", "enabled": False},
    "Company career pages": {"domain": "", "enabled": True},
}

# Role families scanned by the market scan so the app covers more than the configured roles.
DEFAULT_SCAN_ROLES = ["AI Engineer", "Machine Learning Engineer", "Backend Developer",
                      "Full Stack Developer", "Frontend Developer", "Data Engineer",
                      "Data Analyst", "DevOps Engineer", "Software Engineer", "QA Automation Engineer",
                      "Android Developer", "Cybersecurity Analyst"]

DEFAULT_PREFERENCES: dict[str, Any] = {
    "jobs": {
        "roles": [],
        "role_suggestions": ["AI Engineer", "AI Agent Developer", "LLM Engineer",
                             "Machine Learning Engineer", "Python Developer", "Backend Developer",
                             "Software Engineer", "Research Engineer", "Data Scientist", "Internship"],
        "experience": "any",
        "employment_types": [],
        "locations": [],
        "remote": "any",
        "salary_min": None,
        "salary_max": None,
        "ignore_salary": True,
        "skills": [],
        "skill_suggestions": ["Python", "C++", "JavaScript", "FastAPI", "SQL", "PyTorch",
                              "TensorFlow", "LangChain", "MCP", "RAG", "LLMs", "Agentic AI",
                              "Docker", "Linux", "Cloud"],
        "portals": DEFAULT_PORTALS,
        "custom_sites": [],
        "freshness": "30d",
        "match_resume": True,
        "scan_roles": DEFAULT_SCAN_ROLES[:6],
        "scan_role_suggestions": DEFAULT_SCAN_ROLES,
        "pool_size": 100,
        "companies": None,  # None = built-in verified list (app.services.ats_sources)
        "work_authorization": ["India"],
        "discover_employers": False,
    },
    "government": {
        "disciplines": ["Computer Science", "Information Technology"],
        "gate_paper": "",
        "locations": [],
        "freshness": "90d",
    },
    "exams": {
        "freshness": "365d",
    },
    "news": {
        "interests": ["artificial intelligence", "AI startups", "AI policy", "generative AI"],
        "sources": [],
        "region": "India",
        "topics": [],
        "freshness": "7d",
    },
    "papers": {
        "interests": ["LLM agents", "retrieval augmented generation", "efficient inference"],
        "sources": [],
        "freshness": "30d",
    },
    "scan_all": {"categories": ["jobs", "government", "exams", "news", "papers"]},
    "automation": {
        "daily_refresh": False,
        "refresh_time": "08:00",
        "categories": ["jobs", "news"],
        "reverify_hours": 24,
    },
    "skill_aliases": {},
    "scoring": {"weights": {"role": 20, "mandatory_skills": 25, "preferred_skills": 15, "experience": 15,
                            "education": 10, "location_employment": 10, "freshness": 5}},
}

PREFERENCE_KEY = "discovery_preferences"


def _strings(value: Any, limit: int = 40) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    output = []
    for item in value:
        clean = " ".join(str(item).split())[:120]
        if clean and clean not in output:
            output.append(clean)
        if len(output) >= limit:
            break
    return output


def _bounded_number(value: Any) -> float | None:
    if value in (None, "", "any"):
        return None
    try:
        return max(0.0, min(10_000_000.0, float(value)))
    except (TypeError, ValueError):
        return None


def _portals(value: Any) -> dict[str, dict[str, Any]]:
    base = deepcopy(DEFAULT_PORTALS)
    if isinstance(value, dict):
        for name, settings in value.items():
            clean = " ".join(str(name).split())[:80]
            if not clean:
                continue
            domain = ""
            enabled = True
            if isinstance(settings, dict):
                domain = str(settings.get("domain") or "").strip()[:200]
                enabled = bool(settings.get("enabled", True))
            elif isinstance(settings, bool):
                enabled = settings
            base[clean] = {"domain": domain, "enabled": enabled}
    return base


def load_preferences(store: Store) -> dict[str, Any]:
    stored = store.get_preference(PREFERENCE_KEY, {}) or {}
    merged = deepcopy(DEFAULT_PREFERENCES)
    merged.setdefault("discovery", {"sections": ["jobs", "government", "exams", "news"]})
    if isinstance(stored, dict):
        for category, values in stored.items():
            if category not in merged or not isinstance(values, dict):
                continue
            merged[category].update(values)
    if isinstance(stored, dict) and isinstance(stored.get("skill_aliases"), dict):
        merged["skill_aliases"] = dict(stored["skill_aliases"])
    from app.services.skills_taxonomy import configure
    configure(merged.get("skill_aliases"))
    # New default portals appear even when older saved preferences predate them.
    merged["jobs"]["portals"] = _portals(merged["jobs"].get("portals"))
    return merged


def validate_preferences(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Preferences must be an object")
    output = deepcopy(DEFAULT_PREFERENCES)

    jobs = payload.get("jobs") if isinstance(payload.get("jobs"), dict) else {}
    output["jobs"].update({
        "roles": _strings(jobs.get("roles")),
        "experience": str(jobs.get("experience") or "any")[:40],
        "employment_types": _strings(jobs.get("employment_types")),
        "locations": _strings(jobs.get("locations")),
        "remote": str(jobs.get("remote") or "any")[:20],
        "salary_min": _bounded_number(jobs.get("salary_min")),
        "salary_max": _bounded_number(jobs.get("salary_max")),
        "ignore_salary": bool(jobs.get("ignore_salary", True)),
        "skills": _strings(jobs.get("skills")),
        "portals": _portals(jobs.get("portals")),
        "custom_sites": _strings(jobs.get("custom_sites")),
        "freshness": str(jobs.get("freshness") or "30d")[:20],
        "match_resume": bool(jobs.get("match_resume", True)),
        "scan_roles": _strings(jobs.get("scan_roles"), 12) if "scan_roles" in jobs
        else list(DEFAULT_SCAN_ROLES[:6]),
        "pool_size": _pool(jobs.get("pool_size")),
        "companies": _companies(jobs.get("companies")),
    })
    scoring = payload.get("scoring") if isinstance(payload.get("scoring"), dict) else {}
    weights = scoring.get("weights") if isinstance(scoring.get("weights"), dict) else {}
    clean_weights = {}
    for key, default in DEFAULT_PREFERENCES["scoring"]["weights"].items():
        try:
            clean_weights[key] = max(0, min(100, int(weights.get(key, default))))
        except (TypeError, ValueError):
            clean_weights[key] = default
    if not any(clean_weights.values()):
        clean_weights = dict(DEFAULT_PREFERENCES["scoring"]["weights"])
    output["scoring"] = {"weights": clean_weights}
    output["skill_aliases"] = {str(k)[:60]: str(v)[:60] for k, v in (payload.get("skill_aliases") or {}).items()
                               if str(k).strip() and str(v).strip()} if isinstance(payload.get("skill_aliases"), dict) else {}
    jobs_in = payload.get("jobs") if isinstance(payload.get("jobs"), dict) else {}
    output["jobs"]["work_authorization"] = _strings(jobs_in.get("work_authorization"), 6) or ["India"]
    output["jobs"]["discover_employers"] = bool(jobs_in.get("discover_employers", False))
    # Acquisition limits (v3.3) and matching mode (v4).
    def _int(key: str, default: int, low: int, high: int) -> int:
        try:
            return max(low, min(high, int(jobs_in.get(key, default))))
        except (TypeError, ValueError):
            return default
    output["jobs"].update({
        "browser_rendering": bool(jobs_in.get("browser_rendering", True)),
        "browser_concurrency": _int("browser_concurrency", 1, 1, 2),
        "browser_timeout_ms": _int("browser_timeout_ms", 15000, 3000, 60000),
        "http_concurrency": _int("http_concurrency", 6, 1, 8),
        "store_cap": _int("store_cap", 500, 50, 2000),
        "firecrawl_enabled": bool(jobs_in.get("firecrawl_enabled", False)),
        "match_mode": "best" if jobs_in.get("match_mode") == "best" else "active",
    })
    discovery = payload.get("discovery") if isinstance(payload.get("discovery"), dict) else {}
    output["discovery"] = {"sections": [item for item in _strings(discovery.get("sections"), 6)
                                        if item in {"jobs", "government", "exams", "news"}]
                           or ["jobs", "government", "exams", "news"]}
    scan_all = payload.get("scan_all") if isinstance(payload.get("scan_all"), dict) else {}
    output["scan_all"] = {"categories": [item for item in _strings(scan_all.get("categories"), 5)
                                         if item in {"jobs", "government", "exams", "news", "papers"}]
                          or ["jobs", "government", "exams", "news", "papers"]}

    government = payload.get("government") if isinstance(payload.get("government"), dict) else {}
    output["government"].update({
        "disciplines": _strings(government.get("disciplines")),
        "gate_paper": str(government.get("gate_paper") or "")[:20],
        "locations": _strings(government.get("locations")),
        "freshness": str(government.get("freshness") or "90d")[:20],
    })

    exams = payload.get("exams") if isinstance(payload.get("exams"), dict) else {}
    output["exams"].update({"freshness": str(exams.get("freshness") or "365d")[:20]})

    news = payload.get("news") if isinstance(payload.get("news"), dict) else {}
    output["news"].update({
        "interests": _strings(news.get("interests")),
        "sources": _strings(news.get("sources")),
        "region": str(news.get("region") or "India")[:80],
        "topics": _strings(news.get("topics"), 10),
        "freshness": str(news.get("freshness") or "7d")[:20],
    })

    automation = payload.get("automation") if isinstance(payload.get("automation"), dict) else {}
    output["automation"] = {
        "reverify_hours": max(0.0, min(168.0, float(automation.get("reverify_hours", 24) or 0))),
        "daily_refresh": bool(automation.get("daily_refresh", False)),
        "refresh_time": _clock(automation.get("refresh_time")),
        "categories": [item for item in _strings(automation.get("categories"), 5)
                       if item in {"jobs", "news", "papers", "government", "exams"}] or ["jobs", "news"],
        "reverify_batch": max(5, min(100, int(automation.get("reverify_batch", 30) or 30))),
        "followed_hours": max(0.0, min(168.0, float(automation.get("followed_hours", 12) or 0))),
        "notify": bool(automation.get("notify", True)),
        "notify_min_score": max(0, min(100, int(automation.get("notify_min_score", 70) or 70))),
    }

    papers = payload.get("papers") if isinstance(payload.get("papers"), dict) else {}
    output["papers"].update({
        "interests": _strings(papers.get("interests")),
        "sources": _strings(papers.get("sources")),
        "freshness": str(papers.get("freshness") or "30d")[:20],
    })
    return output


def _pool(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 100
    return max(20, min(300, number))


def _companies(value: Any) -> list[dict[str, str]] | None:
    if value is None:
        return None
    from app.services.ats_sources import normalize_company
    if not isinstance(value, list):
        return None
    clean = [company for company in (normalize_company(item) for item in value) if company]
    return clean[:80]


def _clock(value: Any) -> str:
    text = str(value or "08:00").strip()
    match = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", text)
    return f"{int(match.group(1)):02d}:{match.group(2)}" if match else "08:00"


def scan_roles(preferences: dict[str, Any]) -> list[str]:
    """Roles for the market scan: configured roles first, then scan roles."""
    jobs = preferences.get("jobs", {})
    roles = list(jobs.get("roles") or []) + list(jobs.get("scan_roles") or DEFAULT_SCAN_ROLES[:6])
    output: list[str] = []
    for role in roles:
        clean = " ".join(str(role).split())
        if clean and clean.casefold() not in {item.casefold() for item in output}:
            output.append(clean)
    return output[:12]


def save_preferences(store: Store, payload: dict[str, Any]) -> dict[str, Any]:
    clean = validate_preferences(payload)
    store.set_preference(PREFERENCE_KEY, clean)
    return clean


def portal_domains(preferences: dict[str, Any]) -> list[str]:
    jobs = preferences.get("jobs", {})
    domains = [str(item.get("domain") or "") for item in jobs.get("portals", {}).values()
               if isinstance(item, dict) and item.get("enabled", True)]
    domains.extend(jobs.get("custom_sites", []))
    output = []
    for domain in domains:
        clean = str(domain).strip().lower()
        clean = clean.removeprefix("https://").removeprefix("http://").strip("/")
        if clean and clean not in output:
            output.append(clean)
    return output


def interests_for(preferences: dict[str, Any], category: str) -> list[str]:
    if category in {"news", "papers"}:
        return list(preferences.get(category, {}).get("interests", []))
    if category == "jobs":
        jobs = preferences.get("jobs", {})
        return list(jobs.get("roles", [])) + list(jobs.get("skills", []))
    if category == "government":
        return list(preferences.get("government", {}).get("disciplines", []))
    return []
