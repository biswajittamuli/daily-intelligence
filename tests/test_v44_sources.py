"""Indian startup seeds: verified boards, career-site employers, re-seeding and career-page rotation."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlsplit

from app.config import Settings
from app.memory.store import Store
from app.services.ats_sources import ATS_TYPES, DEFAULT_COMPANIES, INDIAN_BOARDS, INDIAN_CAREER_SITES, SEED_VERSION


class SeedLists(unittest.TestCase):
    def test_lists_are_well_formed_and_do_not_overlap(self):
        boards = {(c["ats"], c["slug"]) for c in DEFAULT_COMPANIES}
        self.assertEqual(len(boards), len(DEFAULT_COMPANIES))
        self.assertTrue(all(c["ats"] in ATS_TYPES for c in DEFAULT_COMPANIES))
        self.assertTrue(set(INDIAN_BOARDS) <= {c["slug"] for c in DEFAULT_COMPANIES})
        hosts = [urlsplit(s["website"]).hostname for s in INDIAN_CAREER_SITES]
        self.assertEqual(len(hosts), len(set(hosts)))
        self.assertTrue(all(s["website"].startswith("https://") and urlsplit(s["website"]).path == ""
                            for s in INDIAN_CAREER_SITES))  # homepage only: career URLs are discovered, never invented
        board_names = {c["name"].casefold() for c in DEFAULT_COMPANIES}
        self.assertFalse(board_names & {s["name"].casefold() for s in INDIAN_CAREER_SITES})
        for name in ("Zerodha", "Flipkart", "Blinkit"):
            self.assertIn(name, {s["name"] for s in INDIAN_CAREER_SITES})


class Seeding(unittest.TestCase):
    def test_seed_creates_due_employers_once_per_version(self):
        from app.web import Application
        with tempfile.TemporaryDirectory() as tmp:
            app = Application(Settings(data_dir=Path(tmp), notes_dir=Path(tmp) / "notes"))
            try:
                self.assertEqual(app.store.get_preference("employer_seed_version"), SEED_VERSION)
                employers = {e["name"]: e for e in app.store.employers(limit=2000)}
                zerodha = employers["Zerodha"]
                self.assertEqual((zerodha["website"], zerodha["domain"], zerodha["country"]),
                                 ("https://zerodha.com", "zerodha.com", "India"))
                self.assertEqual(employers["Swiggy"]["ats_provider"], "smartrecruiters")
                self.assertEqual(employers["Swiggy"]["country"], "India")
                due = {e["name"] for e in app.store.employers_due_for_discovery(limit=500)}
                self.assertTrue({"Zerodha", "Flipkart", "Blinkit"} <= due)
                self.assertEqual(app.seed_employers_if_changed(), 0)  # same version: no re-seed
                self.assertEqual(len(app.store.employers(limit=2000)), len(employers))
            finally:
                app._executor.shutdown(wait=False)


class CareerRotation(unittest.TestCase):
    def test_mark_career_checked_updates_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            employer, _ = store.upsert_employer({"name": "Zerodha", "website": "https://zerodha.com"})
            self.assertIsNone(employer.get("last_career_check"))
            store.mark_career_checked(employer["id"])
            again = store.find_employer("Zerodha")
            self.assertTrue(again["last_career_check"])


if __name__ == "__main__":
    unittest.main()
