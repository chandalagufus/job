import unittest
from unittest.mock import patch

from src.evaluation import _extract_years_requirement, _skill_requirement_level, evaluate_job
from src.job_intelligence import extract_structured_fields


class PreferredExperienceTests(unittest.TestCase):
    def test_flattened_preferred_skills_are_not_required(self):
        for separator in ("\n", " "):
            jd = separator.join([
                "Basic Qualifications", "3 years SQL experience.",
                "Preferred Qualifications", "Hadoop and Redshift experience.",
            ])
            with self.subTest(separator=separator):
                self.assertEqual(_skill_requirement_level("hadoop", jd), "preferred")
                self.assertEqual(_skill_requirement_level("redshift", jd), "preferred")
                self.assertEqual(_skill_requirement_level("sql", jd), "required")

    def test_basic_years_not_overridden_by_preferred(self):
        for separator in ("\n", " "):
            jd = separator.join([
                "Basic Qualifications",
                "3+ years of data engineering experience.",
                "3+ years of developing and operating large-scale ETL processes experience.",
                "Preferred Qualifications",
                "6+ years of business intelligence and analytics experience.",
            ])
            with self.subTest(separator=separator):
                self.assertEqual(_extract_years_requirement(jd), 3)
                self.assertEqual(extract_structured_fields("Data Engineer", jd)["years_experience_min"], 3)
                with patch("src.evaluation.TARGET_EXPERIENCE_MAX_YEARS", 3):
                    result = evaluate_job("Data Engineer", jd, location="Culver City, CA", source="linkedin", require_us_location=False)
                self.assertFalse(any("Blocked because the role requires" in r for r in result.reasons))

    def test_required_section_after_preferred_still_blocks(self):
        jd = "Preferred Qualifications 6 years analytics experience. Required Qualifications 4 years data engineering experience."
        self.assertEqual(_extract_years_requirement(jd), 4)
        self.assertEqual(extract_structured_fields("Data Engineer", jd)["years_experience_min"], 4)
        with patch("src.evaluation.TARGET_EXPERIENCE_MAX_YEARS", 3):
            result = evaluate_job("Data Engineer", jd, location="Boston, MA", require_us_location=False)
        self.assertEqual(result.score, 0)

    def test_preferred_only_does_not_create_mandatory_minimum(self):
        jd = "Preferred Qualifications: 6 years analytics experience."
        self.assertEqual(_extract_years_requirement(jd), 0)
        self.assertNotIn("years_experience_min", extract_structured_fields("Data Engineer", jd))

    def test_unsectioned_experience_is_preserved(self):
        self.assertEqual(_extract_years_requirement("5 years data engineering experience."), 5)

    def test_colon_headings(self):
        jd = "Required: 3 years data engineering experience. Preferred: 6 years analytics experience."
        self.assertEqual(_extract_years_requirement(jd), 3)
        self.assertEqual(extract_structured_fields("Data Engineer", jd)["years_experience_min"], 3)


if __name__ == "__main__":
    unittest.main()
