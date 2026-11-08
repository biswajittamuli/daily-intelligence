import unittest
from unittest.mock import AsyncMock

from app.services.extraction import EvidenceExtractor, render_extraction


class EvidenceExtractionTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_quotes_not_present_in_source_and_irrelevant_quotes(self):
        provider = type("Provider", (), {})()
        provider.generate_json = AsyncMock(return_value={"category": "protocol documentation",
            "source_assessments": [
                {"source_id": "S1", "content_type": "protocol documentation",
                 "source_role": "primary",
                 "rationale": "The page describes its own protocol specification.",
                 "evidence_quote": "The MCP server validates tool permissions before execution."},
                {"source_id": "S1", "content_type": "documentation",
                 "source_role": "primary", "rationale": "Unquoted role claim."},
            ], "findings": [
            {"summary": "MCP validates tool permissions", "source_id": "S1",
             "evidence_quote": "The MCP server validates tool permissions before execution.",
             "nature": "explicit"},
            {"summary": "The release adds many features", "source_id": "S1",
             "evidence_quote": "The release adds 42 new features in the runtime.",
             "nature": "explicit"},
            {"summary": "MCP is secure", "source_id": "S9",
             "evidence_quote": "MCP server validates tool permissions before execution.",
             "nature": "explicit"},
        ]})
        extractor = EvidenceExtractor(provider=provider)

        result = await extractor.extract("MCP tool security", [{
            "title": "MCP design", "url": "https://example.org/mcp",
            "excerpts": ["The MCP server validates tool permissions before execution."],
        }])

        self.assertEqual(len(result.findings), 1)
        self.assertEqual(result.content_type, "protocol documentation")
        self.assertEqual(len(result.source_assessments), 2)
        self.assertEqual(result.source_assessments[0].source_role, "primary")
        self.assertEqual(result.source_assessments[1].source_role, "unknown")
        self.assertEqual(result.findings[0].source_id, "S1")
        self.assertEqual(result.findings[0].evidence_quote,
                         "The MCP server validates tool permissions before execution.")
        self.assertIn("verbatim", render_extraction(result))

    async def test_returns_no_claims_when_no_quote_matches_request_topic(self):
        provider = type("Provider", (), {})()
        provider.generate_json = AsyncMock(return_value={"findings": [
            {"summary": "The release ships a compiler", "source_id": "S1",
             "evidence_quote": "The release includes a faster compiler and linker.",
             "nature": "explicit"},
        ]})
        extractor = EvidenceExtractor(provider=provider)

        result = await extractor.extract("weather forecast rainfall", [{
            "url": "https://example.org/release",
            "excerpts": ["The release includes a faster compiler and linker."],
        }])

        self.assertEqual(result.findings, [])

    async def test_accepts_model_string_finding_only_when_it_is_verbatim(self):
        quote = "Free-threaded Python is officially supported in this release."
        provider = type("Provider", (), {})()
        provider.generate_json = AsyncMock(return_value={"findings": [
            quote,
            "Python is now ten times faster.",
        ]})
        extractor = EvidenceExtractor(provider=provider)
        result = await extractor.extract("Python free-threaded support", [{
            "url": "https://docs.example.org/whats-new",
            "excerpts": [quote],
        }])
        self.assertEqual(len(result.findings), 1)
        self.assertEqual(result.findings[0].evidence_quote, quote)


if __name__ == "__main__":
    unittest.main()
