import unittest
from unittest.mock import patch

from src.evaluation import _extract_years_requirement, evaluate_job


class ExperienceRangeTests(unittest.TestCase):
    def test_ranges_use_minimum_with_modifiers(self):
        cases = [
            ("2-5 years related work experience.", 2),
            ("2\u20135 years related work experience.", 2),
            ("2\u20145 years related work experience.", 2),
            ("2 to 5 years related work experience.", 2),
            ("2-5 years of healthcare analytics experience.", 2),
            ("4-7+ years of experience in Data Engineering.", 4),
            ("3-5 years of professional experience.", 3),
            ("5+ years related work experience.", 5),
            ("2-5 years related work experience. Required: 6 years SQL experience.", 6),
            ("2-5 years related work experience. 3 years Python experience.", 3),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(_extract_years_requirement(text), expected)

    def test_healthcare_range_is_not_experience_blocked(self):
        jd = (
            "Requirements: 2-5 years related work experience. "
            "Data validation, reporting, dashboards and stakeholder requirements."
        )
        with patch("src.evaluation.TARGET_EXPERIENCE_MAX_YEARS", 3):
            result = evaluate_job(
                "Healthcare Data Analyst", jd,
                company="Beth Israel Lahey Health", location="Boston, MA",
                source="linkedin", require_us_location=False,
            )
        self.assertFalse(any("Blocked because the role requires" in r for r in result.reasons))

    def test_genuine_four_year_minimum_remains_blocked(self):
        with patch("src.evaluation.TARGET_EXPERIENCE_MAX_YEARS", 3):
            result = evaluate_job(
                "Data Analyst", "Required: 4-7+ years of related work experience.",
                location="Boston, MA", source="linkedin", require_us_location=False,
            )
        self.assertEqual(result.score, 0)
        self.assertTrue(any("requires 4+ years" in r for r in result.reasons))


if __name__ == "__main__":
    unittest.main()
