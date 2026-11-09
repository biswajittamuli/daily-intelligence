"""v4 phase 4: resume intelligence — best-resume mode, four eligibility levels, profile facets (fixtures)."""
from __future__ import annotations

import unittest

from app.services.job_matching import active_resume_match
from app.services.preferences import validate_preferences
from app.services.resume import extract_profile_deterministic

AI = {"id": 1, "label": "AI", "is_default": True, "status": "processed",
      "profile": {"skills": ["Python", "PyTorch", "RAG", "LLMs"], "experience_years": 0, "education": ["B.Tech CSE"]}}
FE = {"id": 2, "label": "Frontend", "is_default": False, "status": "processed",
      "profile": {"skills": ["React", "TypeScript", "JavaScript", "Next.js", "CSS3"], "experience_years": 0}}
FE_JOB = {"title": "[TEST] Frontend Developer", "location": "Pune, India", "discovered_via": "company career board",
          "raw_text": "Requirements:\n* React and TypeScript\n* Next.js\n* 0-1 years of experience\n* B.Tech or BE"}


class MatchModeTests(unittest.TestCase):
    def test_active_mode_scores_against_active_resume(self):
        prefs = validate_preferences({"jobs": {"locations": ["India"], "roles": ["Frontend Developer"]}})
        result = active_resume_match(FE_JOB, prefs, [AI, FE])
        self.assertEqual(result["best_resume_label"], "AI")
        self.assertEqual(result["eligibility"]["match_mode"], "active")

    def test_best_mode_uses_the_best_fitting_resume(self):
        prefs = validate_preferences({"jobs": {"locations": ["India"], "roles": ["Frontend Developer"], "match_mode": "best"}})
        result = active_resume_match(FE_JOB, prefs, [AI, FE])
        self.assertEqual(result["best_resume_label"], "Frontend")
        primary = [s for s in result["resume_scores"] if s.get("primary")][0]
        self.assertEqual(primary["label"], "Frontend")
        self.assertFalse(primary["active"])
        self.assertGreater(primary["score"], next(s["score"] for s in result["resume_scores"] if s["label"] == "AI"))


class EligibilityLevelTests(unittest.TestCase):
    def level(self, text, title="[TEST] Software Engineer", location="Bengaluru, India"):
        prefs = validate_preferences({"jobs": {"locations": ["India"], "roles": ["Software Engineer"]}})
        job = {"title": title, "location": location, "raw_text": text, "discovered_via": "company career board"}
        return active_resume_match(job, prefs, [AI])["eligibility"]

    def test_four_levels(self):
        eligible = self.level("Requirements:\n* Python\n* 0-1 years of experience\n* B.Tech in Computer Science")
        self.assertEqual((eligible["level"], eligible["level_label"]), ("eligible", "Eligible"))
        likely = self.level("Requirements:\n* Python\n* 0-1 years of experience")
        self.assertEqual(likely["level"], "likely_eligible")
        uncertain = self.level("We build things with Python.", title="[TEST] Engineer")
        self.assertEqual(uncertain["level"], "uncertain")
        no = self.level("Requirements:\n* Python\n* 5+ years of experience")
        self.assertEqual((no["level"], no["tier"]), ("not_eligible", "ineligible"))
        self.assertNotEqual(uncertain["tier"], "strong")  # uncertain is never shown as a strong match


class ProfileFacetTests(unittest.TestCase):
    def test_facets_are_deterministic(self):
        text = ("[TEST FIXTURE RESUME] Asha Rao, Guwahati, Assam\nEducation: B.Tech Computer Science 2026\n"
                "Skills: Python, PyTorch, LangChain, Docker, AWS, Kubernetes, React\n"
                "Certifications\nAWS Cloud Practitioner\n")
        profile = extract_profile_deterministic(text)
        self.assertIn("PyTorch", profile["ai_ml_skills"])
        self.assertTrue({"Docker", "AWS"} <= set(profile["cloud_skills"]))
        self.assertEqual(profile["location"], "Guwahati")
        self.assertEqual(profile["graduation_year"], 2026)
        self.assertTrue(profile["certifications"])


if __name__ == "__main__":
    unittest.main()
