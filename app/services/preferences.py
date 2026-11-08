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
    "automation": {
        "daily_refresh": False,
        "refresh_time": "08:00",
        "categories": ["jobs", "news"],
    },
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
    if isinstance(stored, dict):
        for category, values in stored.items():
            if category not in merged or not isinstance(values, dict):
                continue
            merged[category].update(values)
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
    })

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
        "daily_refresh": bool(automation.get("daily_refresh", False)),
        "refresh_time": _clock(automation.get("refresh_time")),
        "categories": [item for item in _strings(automation.get("categories"), 5)
                       if item in {"jobs", "news", "papers", "government", "exams"}] or ["jobs", "news"],
    }

    papers = payload.get("papers") if isinstance(payload.get("papers"), dict) else {}
    output["papers"].update({
        "interests": _strings(papers.get("interests")),
        "sources": _strings(papers.get("sources")),
        "freshness": str(papers.get("freshness") or "30d")[:20],
    })
    return output


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
