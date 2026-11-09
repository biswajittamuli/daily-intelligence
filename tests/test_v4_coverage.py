"""v4 phase 2: Indian/startup coverage — feeds, work arrangement, common career paths, employer fields.

Every record here is a labelled test fixture served from loopback or a mock transport.
"""
from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.memory.store import Store
from app.services.broad_search import BroadJobSearch
from app.services.employer_discovery import _city_from, _stage_from
from app.services.job_sources.career_discovery import CareerDiscovery
from app.services.job_sources.feeds import parse_feed
from app.services.job_sources.geo import work_arrangement
from app.services.job_sources.safe_http import SafeFetcher
from app.services.preferences import validate_preferences
from tests.fixtures.career_sites import serve_sites

ATOM = """<?xml version='1.0'?><feed xmlns='http://www.w3.org/2005/Atom'>
<entry><title>[TEST FIXTURE] Backend Engineer at Acme, Bengaluru</title><link rel='alternate' href='https://hasjob.co/acme/abc12'/>
<updated>2026-11-08T10:00:00Z</updated><content type='html'>&lt;p&gt;Python, Django. Bengaluru.&lt;/p&gt;</content></entry>
<entry><title></title><link href='https://hasjob.co/x'/></entry>
</feed>"""
RSS = """<rss><channel><item><title>[TEST FIXTURE] ML Intern - Remote</title><link>https://example.test/jobs/1</link>
<pubDate>Sat, 07 Nov 2026 09:00:00 GMT</pubDate><description>Remote, India</description></item></channel></rss>"""


class FeedTests(unittest.TestCase):
    def test_atom_and_rss(self):
        atom = parse_feed(ATOM)
        self.assertEqual(len(atom), 1)
        self.assertEqual(atom[0]["url"], "https://hasjob.co/acme/abc12")
        self.assertEqual(atom[0]["posted_date"], "2026-11-08")
        self.assertEqual(atom[0]["date_source"], "feed entry date")
        self.assertEqual(atom[0]["location"].casefold(), "bengaluru")
        rss = parse_feed(RSS)
        self.assertEqual(rss[0]["posted_date"], "2026-11-07")
        self.assertEqual(rss[0]["location"].casefold(), "remote")

    def test_malformed_and_entity_feeds_are_safe(self):
        self.assertEqual(parse_feed("not xml"), [])
        evil = ("<?xml version='1.0'?><!DOCTYPE f [<!ENTITY x SYSTEM 'file:///etc/passwd'>]>"
                "<rss><channel><item><title>&x;</title><link>https://e.test/1</link></item></channel></rss>")
        for item in parse_feed(evil):
            self.assertNotIn("root:", item["title"])


class WorkArrangementTests(unittest.TestCase):
    def test_classification_needs_evidence(self):
        cases = {("Bengaluru, Karnataka, India", None, ""): "india",
                 ("Pune", "hybrid", ""): "india_hybrid",
                 ("Remote - India", None, ""): "remote_india",
                 ("Remote", None, "This role is remote in India."): "remote_india",
                 ("Remote - US only", None, ""): "remote_restricted",
                 ("Remote (Worldwide)", None, ""): "remote_india",
                 ("Berlin, Germany", None, "Relocation assistance provided."): "relocation",
                 ("London, UK", None, ""): "abroad",
                 ("", None, ""): "unknown",
                 ("Remote", None, ""): "unknown"}
        for (loc, remote, text), kind in cases.items():
            self.assertEqual(work_arrangement(loc, remote, text)["kind"], kind, (loc, remote, text))
        self.assertFalse(work_arrangement("", None, "We love India")["india_eligible"])


class CareerPathProbeTests(unittest.TestCase):
    def run_discovery(self, name):
        with serve_sites([name]) as sites:
            async def go():
                async with SafeFetcher(allow_private_hosts={"127.0.0.1"}, per_host_interval=0, timeout=5) as http:
                    return await CareerDiscovery(http).run(name.capitalize(), sites[name][0])
            return asyncio.run(go())

    def test_unlinked_common_path_is_found_and_verified(self):
        result = self.run_discovery("probe")
        self.assertEqual(result["outcome"], "career_verified")
        self.assertTrue(result["career_url"].endswith("/join-us"))
        self.assertEqual([j["title"] for j in result["listings"]], ["Platform Engineer"])
        self.assertTrue(any(m["stage"] == "D2" and m["state"] == "extraction_successful" for m in result["methods"]))

    def test_soft_404_is_not_mistaken_for_a_careers_page(self):
        result = self.run_discovery("soft404")
        self.assertEqual(result["outcome"], "not_found")
        self.assertIsNone(result["career_url"])


class EmployerFieldTests(unittest.TestCase):
    def test_city_and_stage(self):
        self.assertEqual(_city_from("Bengaluru-based Kovai Labs. Offices in Bangalore and Pune."), "Bengaluru")
        self.assertEqual(_stage_from("Kovai Labs raises $5 Mn in Series A round"), "Series A")
        self.assertIsNone(_stage_from("Kovai Labs launches app"))

    def test_registry_fields_and_follow(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            employer, _ = store.upsert_employer({"name": "Fixture Labs", "city": "Pune", "stage": "Seed",
                                                 "verification_status": "website verified"})
            self.assertEqual((employer["city"], employer["stage"]), ("Pune", "Seed"))
            store.set_employer_followed(employer["id"], True)
            self.assertEqual([e["name"] for e in store.followed_employers()], ["Fixture Labs"])
            store.save_career_discovery(employer["id"], {"outcome": "career_verified", "attempts": 1,
                                                         "checked_at": "2026-11-09T00:00:00+00:00"})
            self.assertEqual(store.find_employer("Fixture Labs")["verification_status"], "career page verified")


class StartupHubPlanTests(unittest.TestCase):
    def test_hubs_rotate_between_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            prefs = validate_preferences({"jobs": {"locations": ["India"], "roles": ["AI Engineer"]}})
            engine = BroadJobSearch(Settings(data_dir=Path(tmp)), store, prefs)
            first = [h for b in engine.plan("", 200)["batches"] if b.get("group") == "startup" for h in b.get("hubs", [])]
            self.assertIn("Bengaluru", first)
            store.set_preference("startup_hub_rotation", 4)
            later = [b for b in engine.plan("", 200)["batches"] if b.get("group") == "startup"]
            self.assertTrue(later)
            self.assertNotEqual(later[0]["hubs"][0], "Bengaluru")
            pune = engine.plan("AI engineer jobs in Pune", 200)
            self.assertTrue(any(b.get("hubs", [""])[0] == "Pune" for b in pune["batches"] if b.get("group") == "startup")
                            or not any(b.get("group") == "startup" for b in pune["batches"]))


if __name__ == "__main__":
    unittest.main()
