"""v5: deterministic candidate eligibility and notice-requirement extraction.

No network, no model: every verdict here is a pure function of the declared profile and the notice clauses.
"""
from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from app.memory.store import Store
from app.services.eligibility import clean_profile, evaluate, filter_bucket, reevaluate_store
from app.services.requirements import extract_notice_requirements

TODAY = date(2026, 11, 16)
QUAL_CS = {"qualification": {"degrees": ["engineering"], "branches": ["cs", "it"], "any_branch": False,
                             "any_degree": False, "equivalent_allowed": False, "evidence": "B.Tech CSE / IT"}}
PROFILE = {
    "date_of_birth": "1997-01-01", "category": "General", "nationality": "Indian",
    "education": {"degree": "B.Tech", "branch": "Computer Science and Engineering", "graduation_year": 2026,
                  "percentage": 72},
    "experience": {"full_time_months": 0},
    "gate": {"appeared": True, "paper": "CS", "year": 2026, "score": 600, "valid_until": "2029-03-31"},
}


def profile(**overrides):
    base = {**PROFILE, **overrides}
    return clean_profile(base)


class AgeTests(unittest.TestCase):
    def test_age_exactly_on_closing_date_is_allowed_one_day_after_is_not(self):
        req = {"age": {"max": 30}, **QUAL_CS}
        exact = evaluate(profile(), req, closing_date="2027-01-01", today=TODAY)
        self.assertEqual(exact["status"], "eligible", exact)
        self.assertEqual(exact["as_of"], "2027-01-01")
        self.assertEqual(exact["as_of_source"], "closing date")
        late = evaluate(profile(), req, closing_date="2027-01-02", today=TODAY)
        self.assertEqual(late["status"], "not_eligible")
        self.assertTrue(any("maximum 30" in reason for reason in late["failed_rules"]))

    def test_relaxation_applies_only_when_the_notice_states_it(self):
        older = profile(date_of_birth="1994-01-01", category="OBC-NCL")
        without = evaluate(older, {"age": {"max": 30}, **QUAL_CS}, closing_date="2027-01-01", today=TODAY)
        self.assertEqual(without["status"], "not_eligible")
        with_relaxation = evaluate(older, {"age": {"max": 30},
                                           "age_relaxation": {"years": {"OBC-NCL": 3},
                                                              "evidence": "OBC-NCL candidates by 3 years"},
                                           **QUAL_CS}, closing_date="2027-01-01", today=TODAY)
        self.assertEqual(with_relaxation["status"], "eligible")
        self.assertTrue(any("3 years' relaxation" in rule for rule in with_relaxation["passed_rules"]))

    def test_missing_date_of_birth_is_uncertain_never_eligible(self):
        unknown = clean_profile({"education": {"degree": "B.Tech", "branch": "CSE"}})
        result = evaluate(unknown, {"age": {"max": 30}}, closing_date="2027-01-01", today=TODAY)
        self.assertEqual(result["status"], "uncertain")
        self.assertTrue(any("birth" in fact.casefold() for fact in result["missing_facts"]))
        self.assertNotEqual(result["status"], "eligible")


class QualificationTests(unittest.TestCase):
    def test_listed_branch_and_any_engineering_branch(self):
        listed = evaluate(profile(), QUAL_CS, closing_date="2027-01-01", today=TODAY)
        self.assertEqual(listed["status"], "eligible")
        self.assertTrue(any("Branch: Computer Science" in rule for rule in listed["passed_rules"]))
        any_branch = {"qualification": {"degrees": ["engineering"], "branches": [], "any_branch": True,
                                        "any_degree": False, "equivalent_allowed": False,
                                        "evidence": "any branch of engineering"}}
        result = evaluate(profile(), any_branch, closing_date="2027-01-01", today=TODAY)
        self.assertEqual(result["status"], "eligible")
        self.assertTrue(any("any discipline" in rule for rule in result["passed_rules"]))

    def test_wrong_branch_is_not_eligible(self):
        mechanical = profile(education={"degree": "B.Tech", "branch": "Mechanical Engineering", "graduation_year": 2026,
                                        "percentage": 72})
        result = evaluate(mechanical, QUAL_CS, closing_date="2027-01-01", today=TODAY)
        self.assertEqual(result["status"], "not_eligible")
        self.assertTrue(any("Branch" in rule for rule in result["failed_rules"]))

    def test_missing_percentage_is_uncertain_and_names_the_fact(self):
        silent = profile(education={"degree": "B.Tech", "branch": "Computer Science", "graduation_year": 2026,
                                    "percentage": None})
        result = evaluate(silent, {"percentage": {"min": 60, "evidence": "minimum 60% marks"}},
                          closing_date="2027-01-01", today=TODAY)
        self.assertEqual(result["status"], "uncertain")
        self.assertIn("Percentage not set", result["missing_facts"])
        self.assertEqual(filter_bucket(result), "needs_fact")

    def test_evidence_quote_is_preserved(self):
        result = evaluate(profile(), QUAL_CS, closing_date="2027-01-01", today=TODAY)
        self.assertTrue(any("B.Tech CSE / IT" in quote for quote in result["evidence"]))


class GateTests(unittest.TestCase):
    def gate_requirement(self, **overrides):
        return {"gate": {"required": True, "papers": ["CS"], "years": [2026], "min_score": 400,
                         "evidence": "GATE 2026 CS score", **overrides}, **QUAL_CS}

    def test_paper_mismatch(self):
        result = evaluate(profile(), self.gate_requirement(papers=["ME"]), closing_date="2027-01-01", today=TODAY)
        self.assertEqual(result["status"], "not_eligible")
        self.assertTrue(any("GATE paper" in rule for rule in result["failed_rules"]))

    def test_score_below_cutoff(self):
        result = evaluate(profile(), self.gate_requirement(min_score=700), closing_date="2027-01-01", today=TODAY)
        self.assertEqual(result["status"], "not_eligible")
        self.assertTrue(any("below the minimum" in rule for rule in result["failed_rules"]))

    def test_expired_score(self):
        expired = profile(gate={"appeared": True, "paper": "CS", "year": 2022, "score": 600,
                                "valid_until": "2025-03-31"})
        result = evaluate(expired, self.gate_requirement(years=[]), closing_date="2027-01-01", today=TODAY)
        self.assertEqual(result["status"], "not_eligible")
        self.assertTrue(any("expired" in rule for rule in result["failed_rules"]))

    def test_wrong_gate_year(self):
        old = profile(gate={"appeared": True, "paper": "CS", "year": 2022, "score": 600,
                            "valid_until": "2029-03-31"})
        result = evaluate(old, self.gate_requirement(), closing_date="2027-01-01", today=TODAY)
        self.assertEqual(result["status"], "not_eligible")
        self.assertTrue(any("2022" in rule for rule in result["failed_rules"]))

    def test_missing_score_is_uncertain(self):
        no_gate = profile(gate={"appeared": None, "paper": None, "year": None, "score": None, "rank": None,
                                "valid_until": None})
        result = evaluate(no_gate, self.gate_requirement(), closing_date="2027-01-01", today=TODAY)
        self.assertEqual(result["status"], "uncertain")
        self.assertIn("GATE score not set", result["missing_facts"])


class RequirementsExtractionTests(unittest.TestCase):
    TEXT = """Upper age limit is 30 years as on 01.01.2027. Age relaxation: OBC-NCL candidates by 3 years.
Essential Qualification: B.Tech in Computer Science / Information Technology with minimum 60% marks.
GATE 2026 score in CS paper is mandatory. Closing date for applications is 31.01.2027."""

    def test_psu_notice_clauses(self):
        req = extract_notice_requirements(self.TEXT)
        self.assertEqual(req["age"]["max"], 30)
        self.assertEqual(req["age"]["as_on"], "2027-01-01")
        self.assertEqual(req["age_relaxation"]["years"], {"OBC-NCL": 3})
        self.assertEqual(req["qualification"]["branches"], ["cs", "it"])
        self.assertEqual(req["percentage"]["min"], 60.0)
        self.assertTrue(req["gate"]["required"])
        self.assertEqual(req["gate"]["papers"], ["CS"])
        self.assertIn("B.Tech in Computer Science", req["qualification"]["evidence"])

    def test_extraction_and_verdict_agree(self):
        result = evaluate(profile(), extract_notice_requirements(self.TEXT), closing_date="2027-01-31", today=TODAY)
        self.assertEqual(result["status"], "eligible", result)
        self.assertGreaterEqual(len(result["evidence"]), 2)


class StoredVerdictTests(unittest.TestCase):
    def test_reevaluate_store_marks_every_notice_and_exam(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp))
            store.save_eligibility_profile(clean_profile(PROFILE))
            notice, _ = store.save_gov_notice({
                "organization": "TEST PSU", "post_name": "Engineer", "official_source": True,
                "source_id": "test", "url": "https://test.psu.in/notice",
                "notification_url": "https://test.psu.in/notice",
                "closing_date": "2027-01-31", "requirements": extract_notice_requirements(RequirementsExtractionTests.TEXT),
                "eligibility": None})
            counts = reevaluate_store(store)
            self.assertGreaterEqual(counts["notices"], 1)
            stored = store.notice(notice["id"])
            self.assertEqual(stored["eligibility"]["status"], "eligible")
            self.assertEqual(stored["eligibility_as_of"], "2027-01-01")
            self.assertEqual(filter_bucket(stored["eligibility"]), "eligible")


if __name__ == "__main__":
    unittest.main()
