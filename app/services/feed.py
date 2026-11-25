"""Unified opportunity feed: one prioritised list built from the shared intelligence database.

Jobs, government notices and exam events are normalised into ``FeedItem`` dicts with section tags
(strong, good, stretch, internship, fresher, remote, startup, product, government, followed). Sections
are filters over the same items — no section triggers its own acquisition.

Priority order (highest first): newly discovered strong matches, approaching deadlines, followed
companies, fresh startup vacancies, internships, government recruitment, then everything else by rank.
Within that, listings verified on the employer's system rank above unverified or undated ones.
Closed/expired, hidden and reported listings are left out of the default feed but never deleted.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any

from app.services.freshness import parse_date

NEW_BUCKETS = {"new_today", "new_24h", "new_3d"}
LIFECYCLE_ADJUST = {"open_verified": 5, "open_page_checked": -5, "unverified": -15, "unknown": -15,
                    "inaccessible": -20}
INTERN = re.compile(r"\b(intern(ship)?s?|trainee|apprentice)\b", re.I)


def _days_until(value: Any, today: date) -> int | None:
    parsed = parse_date(value)
    return (parsed - today).days if parsed else None


GROUP_TIER = {"verified_strong": "strong", "verified_good": "possible", "verified_low": "low", "stretch": "ineligible",
              "pending": "pending"}


def job_item(job: dict[str, Any], *, employers: dict[int, dict[str, Any]], states: dict[int, str],
             reported: set[int], today: date) -> dict[str, Any]:
    e = job.get("eligibility") or {}
    verdict = job.get("validation") or {}
    group = verdict.get("group")
    # The validation group decides the tier shown: only verified, in-geography vacancies can be strong or good.
    tier = GROUP_TIER.get(group) or e.get("tier") or "low"
    level = e.get("level") or e.get("status") or "uncertain"
    employer = employers.get(job.get("employer_id")) if job.get("employer_id") is not None else None
    bucket = (job.get("freshness_bucket") or {}).get("key")
    arrangement = job.get("arrangement") or {}
    deadline_days = _days_until(job.get("deadline"), today)
    flags = job.get("flags") or {}
    sections = set()
    if tier == "strong":
        sections.add("strong")
    elif tier == "possible":
        sections.add("good")
    elif tier == "ineligible":
        sections.add("stretch")
    if flags.get("intern") or INTERN.search(str(job.get("title") or "")):
        sections.add("internship")
    if flags.get("fresher"):
        sections.add("fresher")
    if flags.get("remote") or arrangement.get("kind") == "remote_india":
        sections.add("remote")
    if employer and employer.get("classification") == "startup":
        sections.add("startup")
    if employer and employer.get("classification") == "established" and employer.get("country") == "India":
        sections.add("product")
    if employer and employer.get("followed"):
        sections.add("followed")
    if bucket in NEW_BUCKETS:
        sections.add("new")
    if group == "pending":
        sections.add("pending")
    priority = 0.0
    priority += (job.get("eligibility") or {}).get("composite") or job.get("match_score") or 0
    if tier == "strong" and bucket in NEW_BUCKETS:
        priority += 400
    if deadline_days is not None and 0 <= deadline_days <= 7:
        priority += 300 - deadline_days * 10
    if "followed" in sections:
        priority += 200
    if "startup" in sections and bucket in NEW_BUCKETS:
        priority += 120
    if "internship" in sections and (job.get("match_score") or 0) >= 60:
        priority += 40  # an internship bonus only for internships that actually match the resume
    # Default feed favours vacancies published within the last 7 days (publication date, never first-seen).
    window = (job.get("freshness_bucket") or {}).get("window")
    priority += {"24h": 70, "3d": 60, "7d": 50, "14d": 25, "30d": 5, "older": -30}.get(window, 0)
    if tier == "ineligible":
        priority -= 200
    if level == "uncertain":
        priority -= 15
    # Trust: a listing confirmed on the employer's own system outranks one nobody could check.
    priority += LIFECYCLE_ADJUST.get((job.get("lifecycle") or {}).get("state") or "", 0)
    if bucket == "date_unknown":
        priority -= 5
    if group == "pending":
        priority -= 40
    return {
        "kind": "job", "id": job["id"], "title": job.get("title"), "org": job.get("employer"),
        "employer_id": job.get("employer_id"), "location": job.get("location"),
        "arrangement": arrangement.get("label"), "match": job.get("match_score"), "tier": tier,
        "eligibility": level, "eligibility_label": e.get("level_label") or level,
        "confidence": e.get("confidence_label"), "freshness": job.get("freshness_bucket"),
        "lifecycle": job.get("lifecycle"), "deadline": job.get("deadline"), "deadline_days": deadline_days,
        "url": job.get("original_url"), "application_url": job.get("application_url"),
        "source_type": job.get("source_type"), "sources": len(job.get("sources") or []),
        "why": e.get("why") or job.get("match_reason"), "missing": (e.get("missing_mandatory") or [])[:4],
        "matched": (e.get("matched") or [])[:6], "resume": job.get("best_resume_label"),
        "sections": sorted(sections), "state": states.get(job["id"]), "reported": job["id"] in reported,
        "first_seen": job.get("first_seen"), "posted": job.get("posted_date"),
        "priority": round(priority, 1),
        "group": group, "group_label": verdict.get("group_label"), "group_reason": verdict.get("reason"),
        "vacancy_status": job.get("vacancy_status_label"), "verification_level": job.get("verification_level"),
        "geography": (verdict.get("geography") or {}).get("label"),
        "published_label": ((verdict.get("freshness") or {}).get("label")),
    }


ELIGIBILITY_ADJUST = {"eligible": 60, "likely_eligible": 30, "uncertain": 0, "not_eligible": -200}


def _verdict(record: dict[str, Any]) -> dict[str, Any]:
    """Feed fields of a stored deterministic verdict (app.services.eligibility)."""
    e = record.get("eligibility") or {}
    status = e.get("status") or "uncertain"
    missing = e.get("missing_facts") or []
    return {"eligibility": status, "eligibility_label": e.get("status_label") or "Not evaluated yet",
            "eligibility_bucket": record.get("eligibility_bucket") or ("needs_fact" if status == "uncertain" and missing else None),
            "why": e.get("summary"), "missing": missing[:4], "passed": (e.get("passed_rules") or [])[:5],
            "failed": (e.get("failed_rules") or [])[:4], "evidence": (e.get("evidence") or [])[:2],
            "as_of": e.get("as_of"), "window": (e.get("window") or {}).get("label"),
            # "ineligible" keeps a notice out of the default lenses, exactly like a stretch job.
            "tier": "ineligible" if status == "not_eligible" else ("strong" if status == "eligible" else None)}


def notice_item(notice: dict[str, Any], today: date) -> dict[str, Any]:
    deadline = notice.get("closing_date")
    deadline_days = _days_until(deadline, today)
    verdict = _verdict(notice)
    priority = 150 + (max(0, 60 - deadline_days * 3) if deadline_days is not None and deadline_days >= 0 else 0)
    priority += ELIGIBILITY_ADJUST.get(verdict["eligibility"], 0)
    sections = ["government"] + ([verdict["eligibility"]] if verdict["eligibility"] in {"eligible", "likely_eligible"} else [])
    return {"kind": "notice", "id": notice["id"], "title": notice.get("post_name") or notice.get("organization"),
            "org": notice.get("organization") or notice.get("source_name"), "location": notice.get("location"),
            "deadline": deadline, "deadline_days": deadline_days,
            "url": notice.get("document_url") or notice.get("original_url"),
            "application_url": notice.get("application_url"), "official": bool(notice.get("official", True)),
            "source_name": notice.get("source_name"), "advertisement_number": notice.get("advertisement_number"),
            **verdict, "sections": sections, "priority": priority, "first_seen": notice.get("first_seen")}


def exam_item(exam: dict[str, Any], today: date) -> dict[str, Any] | None:
    days = _days_until(exam.get("event_date"), today)
    if days is None or days < 0 or days > 60:
        return None
    verdict = _verdict(exam)
    return {"kind": "exam", "id": exam["id"], "title": exam.get("exam_name"),
            "org": exam.get("organization"), "event": exam.get("event_type"), "deadline": exam.get("event_date"),
            "deadline_days": days, "url": exam.get("document_url") or exam.get("original_url"),
            **verdict, "sections": ["exam"],
            "priority": 100 + max(0, 60 - days) + min(0, ELIGIBILITY_ADJUST.get(verdict["eligibility"], 0)),
            "first_seen": exam.get("first_seen")}


def build_feed(*, jobs: list[dict[str, Any]], notices: list[dict[str, Any]], exams: list[dict[str, Any]],
               employers: list[dict[str, Any]], states: dict[int, str], reported: set[int],
               news: list[dict[str, Any]] | None = None, last_visit: str | None = None,
               today: date | None = None, include_hidden: bool = False) -> dict[str, Any]:
    today = today or date.today()
    by_id = {e["id"]: e for e in employers}
    items: list[dict[str, Any]] = []
    other_opportunities: list[dict[str, Any]] = []
    hidden = 0
    outside = 0
    for job in jobs:
        if job.get("source_kind") in {"search_page", "index_page"}:
            continue
        group = (job.get("validation") or {}).get("group")
        if group == "not_vacancy":
            document = (job.get("validation") or {}).get("document") or {}
            if document.get("separate_section"):
                other_opportunities.append({"id": job["id"], "title": job.get("title"), "kind": document.get("label"),
                                            "url": job.get("original_url"), "reason": document.get("reason")})
            continue
        if group == "outside_geography" and not include_hidden:
            outside += 1
            continue
        e = job.get("eligibility") or {}
        if e.get("tier") == "excluded":
            continue
        life = (job.get("lifecycle") or {}).get("state")
        if life in {"closed", "expired"} and not include_hidden:
            continue
        if (states.get(job["id"]) == "dismissed" or job["id"] in reported) and not include_hidden:
            hidden += 1
            continue
        items.append(job_item(job, employers=by_id, states=states, reported=reported, today=today))
    leads = 0
    for notice in notices:
        if str(notice.get("status") or "") in {"closed", "expired"}:
            continue
        if notice.get("lead"):
            leads += 1  # search-fallback results without an official notification: shown under Government, not here
            continue
        items.append(notice_item(notice, today))
    for exam in exams:
        item = exam_item(exam, today)
        if item:
            items.append(item)
    items.sort(key=lambda item: (-item["priority"], str(item.get("first_seen") or "")))
    jobs_only = [i for i in items if i["kind"] == "job"]
    since = last_visit
    new_since = [i for i in jobs_only if since and str(i.get("first_seen") or "") > since]
    deadlines = sorted([i for i in items if i.get("deadline_days") is not None and 0 <= i["deadline_days"] <= 14],
                       key=lambda i: i["deadline_days"])
    sections: dict[str, int] = {}
    for item in items:
        for section in item["sections"]:
            sections[section] = sections.get(section, 0) + 1
    summary = {
        "new_opportunities": sum(1 for i in jobs_only if (i.get("freshness") or {}).get("key") in NEW_BUCKETS
                                 and i.get("group") != "pending"),
        "newly_discovered_undated": sum(1 for i in jobs_only if (i.get("freshness") or {}).get("key") == "date_unknown"
                                        and (i.get("freshness") or {}).get("newly_discovered")),
        "verification_pending": sum(1 for i in jobs_only if i.get("group") == "pending"),
        "outside_geography": outside, "other_opportunities": len(other_opportunities),
        "new_since_last_visit": len(new_since),
        "strong_matches": sum(1 for i in jobs_only if i["tier"] == "strong"),
        "good_matches": sum(1 for i in jobs_only if i["tier"] == "possible"),
        "deadlines_14d": len(deadlines), "exam_updates": sum(1 for i in items if i["kind"] == "exam"),
        "government": sum(1 for i in items if i["kind"] == "notice"), "hidden": hidden,
        "government_eligible": sum(1 for i in items if i["kind"] == "notice" and i.get("eligibility") == "eligible"),
        "government_needs_fact": sum(1 for i in items if i["kind"] == "notice" and i.get("eligibility_bucket") == "needs_fact"),
        "government_leads": leads,
        "sections": sections,
    }
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "summary": summary, "items": items,
            "other_opportunities": other_opportunities[:30],
            "deadlines": deadlines[:10],
            "news": [{"id": n["id"], "title": n.get("title"), "url": n.get("original_url"), "publisher": n.get("publisher"),
                      "date": n.get("published_date"), "topic": n.get("topic")} for n in (news or [])[:5]]}
