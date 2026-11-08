import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock

from app.memory.planning import read_planning_notes
from app.memory.store import Store
from app.services.domain_intelligence import DomainIntelligence
from app.web import Application
import asyncio


class LocalApplicationTests(unittest.TestCase):
    def test_markdown_and_json_notes_preserve_explicit_state_and_deadlines(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "today.md").write_text("- [ ] Submit application due: 2026-11-09\n- [x] Finished task\n")
            (root / "tasks.json").write_text(json.dumps({"tasks": [{"text": "Review notice", "deadline": "2026-11-07"}]}))
            parsed = read_planning_notes(root, date(2026, 11, 8))
            self.assertEqual(len(parsed["tasks"]), 3)
            self.assertEqual(sum(t["status"] == "completed" for t in parsed["tasks"]), 1)
            self.assertTrue(next(t for t in parsed["tasks"] if t["text"] == "Review notice")["overdue"])

    def test_store_persists_tasks_history_and_briefings(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            task_id = store.add_task("Prepare report", "2026-11-09")
            store.set_task_status(task_id, "completed")
            history_id = store.start_history("research", "new topic")
            store.finish_history(history_id, {"answer": "ok"})
            store.save_briefing({"date": "2026-11-08"})
            self.assertEqual(store.tasks()[0]["status"], "completed")
            self.assertEqual(store.history()[0]["result"]["answer"], "ok")
            self.assertEqual(store.briefings()[0]["content"]["date"], "2026-11-08")

    def test_source_change_tracking_stores_hash_and_reports_changed_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            source = {"url": "https://example.org/notice", "title": "Notice", "content": "Deadline is December 1."}
            self.assertEqual(store.observe_sources([source]), [])
            self.assertEqual(store.observe_sources([source]), [])
            updated = {**source, "content": "Deadline is December 5."}
            changes = store.observe_sources([updated])
            self.assertEqual(changes[0]["url"], source["url"])
            self.assertEqual(changes[0]["change_count"], 1)

    def test_interface_home_is_local_dashboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            from app.config import Settings
            app = Application(Settings(data_dir=Path(tmp), notes_dir=Path(tmp) / "notes"))
            page = app.page()
            self.assertIn("id=\"navigation\"", page)
            self.assertIn("/app.css", page)
            self.assertIn("/app.js", page)

    def test_settings_persist_and_apply_to_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            from app.config import Settings
            settings = Settings(data_dir=Path(tmp), notes_dir=Path(tmp) / "notes")
            app = Application(settings)
            updated = asyncio.run(app.update_settings({
                "ollama_model": "", "max_search_queries": 2, "max_fetch_urls": 2,
                "max_content_chars": 8000, "ollama_timeout": 30, "mcp_timeout": 15,
                "notes_dir": str(Path(tmp) / "custom-notes"), "location": "India",
                "briefing_preferences": "entry-level AI", "theme": "light",
            }))
            reloaded = Application(settings)
            self.assertEqual(updated["max_fetch_urls"], 2)
            self.assertEqual(reloaded.settings.notes_dir, Path(tmp) / "custom-notes")
            self.assertEqual(reloaded.public_settings()["theme"], "light")
            self.assertEqual(reloaded.public_settings()["location"], "India")
            app._executor.shutdown(wait=True)
            reloaded._executor.shutdown(wait=True)


class DomainExtractionTests(unittest.IsolatedAsyncioTestCase):
    async def test_accepts_only_fields_with_verbatim_quotes_and_validates_eligibility(self):
        provider = type("Provider", (), {})()
        provider.generate_json = AsyncMock(return_value={"records": [{
            "source_id": "S1", "kind": "recruitment_advertisement",
            "organization": {"value": "Example PSU", "evidence_quote": "Recruitment by Example PSU"},
            "closing_date": {"value": "2026-12-01", "evidence_quote": "Apply by 2026-12-01"},
            "eligibility": {"value": "explicitly_eligible", "evidence_quote": "B.Tech Computer Science graduates may apply"},
            "vacancies": {"value": 42, "evidence_quote": "There are 42 vacancies"},
        }]})
        service = DomainIntelligence(provider=provider)
        records = await service.extract("Find Example PSU recruitment", [{
            "title": "Recruitment by Example PSU", "url": "https://example.org/jobs",
            "content": "Recruitment by Example PSU. B.Tech Computer Science graduates may apply. Apply by 2026-12-01. No vacancy total stated.",
        }])
        self.assertEqual(records[0]["fields"]["eligibility"]["value"], "explicitly_eligible")
        self.assertNotIn("vacancies", records[0]["fields"])
        self.assertEqual(records[0]["application_status"], "open")


if __name__ == "__main__":
    unittest.main()
