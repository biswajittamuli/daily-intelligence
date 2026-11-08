import unittest

from app.services.date_verification import verify_publication_dates


class PublicationDateTests(unittest.TestCase):
    def test_matching_search_and_page_dates_are_consistent(self):
        source = {"publish_date": "2026-11-08", "retrieval_metadata": {"date_published": "November 8, 2026"}}
        verify_publication_dates(source)
        self.assertEqual(source["date_verification"], "consistent")

    def test_conflicting_dates_are_flagged(self):
        source = {"publish_date": "2026-11-08", "retrieval_metadata": {"published_date": "2026-11-07"}}
        verify_publication_dates(source)
        self.assertEqual(source["date_verification"], "inconsistent")
        self.assertEqual(len(source["publication_date_claims"]), 2)

    def test_single_claim_is_not_silently_trusted(self):
        source = {"publish_date": "2026-11-08"}
        verify_publication_dates(source)
        self.assertEqual(source["date_verification"], "unverified")

    def test_missing_dates_are_not_available(self):
        source = {}
        verify_publication_dates(source)
        self.assertEqual(source["date_verification"], "not_available")

    def test_unparseable_claims_are_unverified_not_called_conflicts(self):
        source = {"publish_date": "recently", "retrieval_metadata": {"published_date": "last week"}}
        verify_publication_dates(source)
        self.assertEqual(source["date_verification"], "unverified")


if __name__ == "__main__":
    unittest.main()
