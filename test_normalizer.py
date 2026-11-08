"""Non-destructive regression coverage for the current fetch normalizer."""

import json
import unittest

from app.mcp.normalizer import canonicalize_url, normalize_fetch_results


class NormalizerTests(unittest.TestCase):
    def test_canonical_url_removes_known_tracking_and_duplicate_slashes(self):
        self.assertEqual(
            canonicalize_url("https://www.example.org//docs/page?featured_on=feed"),
            "https://example.org/docs/page",
        )

    def test_normalizes_records_and_deduplicates_canonical_urls(self):
        raw_results = [{
            "task": "arbitrary topic",
            "content": [json.dumps({
                "results": [
                    {
                        "url": "https://docs.example.org/guide?utm_source=mail",
                        "title": "Guide",
                        "publish_date": "2026-11-01",
                        "excerpts": ["Primary source excerpt."],
                        "acquired_at": "2026-11-06T00:00:00Z",
                    },
                    {
                        "url": "https://www.docs.example.org/guide",
                        "title": "Duplicate",
                        "excerpts": ["Duplicate record."],
                    },
                ]
            })],
        }]

        records = normalize_fetch_results(raw_results)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["title"], "Guide")
        self.assertEqual(records[0]["original_url"],
                         "https://docs.example.org/guide?utm_source=mail")
        self.assertEqual(records[0]["canonical_url"], "https://docs.example.org/guide")
        self.assertEqual(records[0]["evidence"][0]["text"], "Primary source excerpt.")


if __name__ == "__main__":
    unittest.main()
