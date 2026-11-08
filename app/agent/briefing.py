"""Personalized daily briefing assembled from stored intelligence and planning notes.

When no intelligence has been discovered yet, the service falls back to the previous
bounded live research so the first briefing is still useful.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import replace
from datetime import date
from typing import Any, Callable

from app.agent.research import ResearchAgent
from app.config import Settings
from app.memory.planning import read_planning_notes
from app.memory.store import Store

log = logging.getLogger(__name__)

BRIEFING_REQUEST = (
    "Find the single most useful current update for a personal daily briefing: "
    "relevant entry-level AI/software jobs or official Indian recruitment and exam notices, "
    "or a significant AI/technology/research development. Prefer a high-quality original source. "
    "Return concise evidence-backed information only."
)


async def _await_cancellable(awaitable, cancel_event: threading.Event | None):
    task = asyncio.ensure_future(awaitable)
    while not task.done():
        if cancel_event and cancel_event.is_set():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise asyncio.CancelledError
        await asyncio.wait({task}, timeout=0.2)
    return task.result()


class BriefingService:
    def __init__(self, settings: Settings | None = None, store: Store | None = None,
                 agent: ResearchAgent | None = None):
        self.settings = settings or Settings.from_env()
        self.store = store or Store(self.settings.data_dir)
        bounded = replace(self.settings,
                          max_search_queries=1,
                          max_fetch_urls=2,
                          max_content_chars=min(self.settings.max_content_chars, 8_000),
                          max_llm_calls=2,
                          mcp_timeout=min(self.settings.mcp_timeout, 30.0),
                          ollama_timeout=min(self.settings.ollama_timeout, 60.0))
        self.agent = agent or ResearchAgent(settings=bounded)
        self.briefing_request = BRIEFING_REQUEST
        if settings:
            preferences = []
            if getattr(settings, "location", None):
                preferences.append(f"Location: {settings.location}")
            self.briefing_request += " " + " ".join(preferences) if preferences else ""

    async def ask(self, request: str, *, cancel_event: threading.Event | None = None) -> dict[str, Any]:
        history_id = self.store.start_history("research", request)
        started = time.perf_counter()
        log.info("research start chars=%d", len(request))
        try:
            result = await _await_cancellable(self.agent.research(request), cancel_event)
            payload = {"request": result.request, "answer": result.answer,
                       "sources": result.sources, "domain_records": result.domain_records or [],
                       "source_changes": self.store.observe_sources(result.sources),
                       "queries": result.plan.search_queries, "completed": True}
            self.store.finish_history(history_id, payload)
            log.info("research complete sources=%d elapsed=%.2fs", len(result.sources), time.perf_counter()-started)
            return payload
        except asyncio.CancelledError:
            self.store.finish_history(history_id, error="Cancelled by user")
            log.info("research cancelled elapsed=%.2fs", time.perf_counter()-started)
            raise
        except Exception as exc:
            self.store.finish_history(history_id, error=f"{type(exc).__name__}: {exc}")
            log.error("research failed type=%s elapsed=%.2fs", type(exc).__name__, time.perf_counter()-started)
            raise

    async def generate(self, *, progress: Callable[[str], None] | None = None,
                       cancel_event: threading.Event | None = None) -> dict[str, Any]:
        progress = progress or (lambda _: None)
        started = time.perf_counter()
        history_id = self.store.start_history("briefing", f"Daily briefing {date.today().isoformat()}")

        def step(message: str) -> None:
            progress(message)
            log.info("briefing step=%s elapsed=%.2fs", message, time.perf_counter()-started)

        try:
            step("Reading Planning notes")
            notes = read_planning_notes(self.settings.notes_dir, date.today(), max_files=1)
            self.store.import_tasks(notes["tasks"])
            if cancel_event and cancel_event.is_set():
                raise asyncio.CancelledError

            jobs = self.store.jobs(limit=20)
            notices = self.store.notices(limit=20)
            exams = self.store.exams(upcoming_only=True, limit=20)
            news = self.store.intel(category="news", limit=20)
            papers = self.store.intel(category="papers", limit=20)
            has_intel = any((jobs, notices, exams, news, papers))

            live_section = None
            if not has_intel:
                step("No stored intelligence yet; running one bounded live search")
                result = await _await_cancellable(
                    self.agent.research(self.briefing_request, fetch_limit=2, include_domain=False,
                                        progress=step), cancel_event)
                live_section = {"title": "Daily intelligence", "status": "complete",
                                "answer": result.answer, "sources": result.sources,
                                "queries": result.plan.search_queries,
                                "source_changes": self.store.observe_sources(result.sources)}
                news = self._store_live_news(result.sources)
            else:
                step("Assembling personalized briefing")

            if cancel_event and cancel_event.is_set():
                raise asyncio.CancelledError

            all_tasks = self.store.tasks()
            previous = self.store.briefings(1)
            previous_urls = self._briefing_urls(previous[0]["content"]) if previous else set()
            changes = self._changes(previous_urls, jobs, notices, exams, news, papers)
            deadlines = self._deadlines(all_tasks, notices, exams)
            sections = self._sections(live_section, jobs, notices, exams, news, papers)

            step("Saving briefing")
            content = {
                "date": date.today().isoformat(),
                "tasks": all_tasks,
                "priorities": [t for t in all_tasks if t["status"] == "pending"],
                "notes_missing": notes["missing"],
                "notes_errors": notes["errors"],
                "sections": sections,
                "jobs": jobs[:8],
                "notices": notices[:8],
                "exams": exams[:10],
                "news": news[:8],
                "papers": papers[:8],
                "deadlines": deadlines,
                "changes": changes,
                "recommended_actions": self._actions(all_tasks, jobs, notices, exams),
                "weather": {"status": "not_configured", "message": "Weather integration is not configured."},
                "execution": {"search_queries": 0 if has_intel else 1,
                              "fetched_urls": 0 if has_intel else len((live_section or {}).get("sources", [])),
                              "llm_calls_max": 2,
                              "stored_items": {"jobs": len(jobs), "notices": len(notices),
                                               "exams": len(exams), "news": len(news),
                                               "papers": len(papers)},
                              "duration_seconds": round(time.perf_counter()-started, 2)},
            }
            self.store.save_briefing(content)
            self.store.finish_history(history_id, content)
            step("Briefing ready")
            log.info("briefing complete jobs=%d exams=%d news=%d elapsed=%.2fs",
                     len(jobs), len(exams), len(news), time.perf_counter()-started)
            return content
        except asyncio.CancelledError:
            self.store.finish_history(history_id, error="Cancelled by user")
            log.info("briefing cancelled elapsed=%.2fs", time.perf_counter()-started)
            raise
        except Exception as exc:
            self.store.finish_history(history_id, error=f"{type(exc).__name__}: {exc}")
            log.error("briefing failed type=%s elapsed=%.2fs", type(exc).__name__, time.perf_counter()-started)
            raise

    def _store_live_news(self, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        from app.mcp.normalizer import canonicalize_url
        records = []
        for source in sources:
            url = str(source.get("url") or "")
            if not url:
                continue
            records.append({
                "url": url, "original_url": source.get("original_url") or url,
                "canonical_url": canonicalize_url(url), "category": "news",
                "title": source.get("title") or "Live research source",
                "publisher": source.get("domain"),
                "published_date": source.get("publish_date"),
                "summary": (source.get("excerpts") or [""])[0] if source.get("excerpts") else "",
                "freshness": (source.get("freshness") or {}).get("label", "unverified")
                             if isinstance(source.get("freshness"), dict) else "unverified",
            })
        return self.store.upsert_intel(records)

    @staticmethod
    def _briefing_urls(content: dict[str, Any]) -> set[str]:
        urls = set()
        for key in ("jobs", "notices", "exams", "news", "papers"):
            for item in content.get(key, []) or []:
                if isinstance(item, dict) and item.get("original_url"):
                    urls.add(str(item["original_url"]))
        for section in content.get("sections", []) or []:
            for source in section.get("sources", []) or []:
                if source.get("url"):
                    urls.add(str(source["url"]))
        return urls

    @staticmethod
    def _changes(previous: set[str], *groups: list[dict[str, Any]]) -> dict[str, Any]:
        current = []
        for group in groups:
            for item in group:
                url = item.get("original_url") or item.get("url")
                title = item.get("title") or item.get("post_name") or item.get("exam_name")
                if url and url not in previous:
                    current.append({"title": title, "url": url})
        return {"new_items": current[:20], "new_count": len(current)}

    @staticmethod
    def _deadlines(tasks: list[dict[str, Any]], notices: list[dict[str, Any]],
                   exams: list[dict[str, Any]]) -> list[dict[str, Any]]:
        today = date.today().isoformat()
        output = []
        for task in tasks:
            if task.get("status") == "pending" and task.get("due_date"):
                output.append({"kind": "task", "title": task.get("text"), "date": task["due_date"],
                               "overdue": task["due_date"] < today})
        for notice in notices:
            if notice.get("closing_date"):
                output.append({"kind": "application deadline",
                               "title": notice.get("post_name") or notice.get("organization"),
                               "date": notice["closing_date"], "url": notice.get("original_url"),
                               "overdue": notice["closing_date"] < today})
        for exam in exams:
            if exam.get("event_date"):
                output.append({"kind": exam.get("event_type") or "exam event",
                               "title": exam.get("exam_name"), "date": exam["event_date"],
                               "url": exam.get("original_url"), "overdue": exam["event_date"] < today})
        return sorted(output, key=lambda item: item["date"])[:15]

    @staticmethod
    def _actions(tasks: list[dict[str, Any]], jobs: list[dict[str, Any]],
                 notices: list[dict[str, Any]], exams: list[dict[str, Any]]) -> list[str]:
        actions = []
        overdue = [task for task in tasks if task.get("status") == "pending" and task.get("due_date")
                   and task["due_date"] < date.today().isoformat()]
        if overdue:
            actions.append(f"Clear {len(overdue)} overdue planning task(s).")
        if jobs:
            top = jobs[0]
            actions.append(f"Review the top job match: {top.get('title')} at {top.get('employer') or 'an employer'}.")
        closing = [notice for notice in notices if notice.get("status") == "open" and notice.get("closing_date")]
        if closing:
            actions.append(f"{len(closing)} recruitment application(s) are still open.")
        upcoming = [exam for exam in exams if exam.get("event_date")]
        if upcoming:
            actions.append(f"Next examination event: {upcoming[0].get('exam_name')} on {upcoming[0].get('event_date')}.")
        if not actions:
            actions.append("Run a Jobs, Government, Exams, News or Papers search to populate the next briefing.")
        return actions

    def _sections(self, live_section, jobs, notices, exams, news, papers) -> list[dict[str, Any]]:
        sections = []
        if live_section:
            sections.append(live_section)
        if jobs:
            sections.append({"title": "New matching jobs", "status": "complete",
                             "items": jobs[:6], "answer": self._jobs_answer(jobs)})
        if notices:
            sections.append({"title": "Government and PSU opportunities", "status": "complete",
                             "items": notices[:6], "answer": self._notices_answer(notices)})
        if exams:
            sections.append({"title": "Upcoming examination events", "status": "complete",
                             "items": exams[:8], "answer": self._exams_answer(exams)})
        if news:
            sections.append({"title": "AI and technology news", "status": "complete",
                             "items": news[:6], "answer": "Recent stories from your saved sources."})
        if papers:
            sections.append({"title": "Research and technical discoveries", "status": "complete",
                             "items": papers[:6], "answer": "Recent papers and resources from your saved sources."})
        if not sections:
            sections.append({"title": "Daily intelligence", "status": "empty",
                             "answer": "No stored intelligence yet. Run a category search or build the briefing again."})
        return sections

    @staticmethod
    def _jobs_answer(jobs: list[dict[str, Any]]) -> str:
        lines = []
        for job in jobs[:6]:
            match = f"{job['match_score']}% match" if job.get("match_score") is not None else "unverified match"
            lines.append(f"- {job.get('title')} at {job.get('employer') or 'unknown employer'} "
                         f"({job.get('location') or 'location unknown'}) — {match}")
        return "\n".join(lines)

    @staticmethod
    def _notices_answer(notices: list[dict[str, Any]]) -> str:
        lines = []
        for notice in notices[:6]:
            closing = notice.get("closing_date")
            suffix = f"closes {closing}" if closing else "closing date unavailable"
            lines.append(f"- {notice.get('organization') or 'Organisation'} — "
                         f"{notice.get('post_name') or 'notice'} ({suffix})")
        return "\n".join(lines)

    @staticmethod
    def _exams_answer(exams: list[dict[str, Any]]) -> str:
        return "\n".join(
            f"- {exam.get('exam_name')} — {exam.get('event_type')} on {exam.get('event_date')} "
            f"({exam.get('date_status')})"
            for exam in exams[:8])
