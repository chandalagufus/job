import unittest
from unittest.mock import patch

from src.evaluation import evaluate_job


class EvaluationEvidenceTests(unittest.TestCase):
    def test_critical_skill_without_resume_evidence_caps_score(self) -> None:
        jd = (
            "Data Engineer. Required: 3 years of enterprise Java experience, "
            "ETL pipelines, BigQuery, Power BI, and data modeling."
        )
        evidence = (
            "Built Python and SQL data pipelines with ETL workflows. "
            "Created BigQuery reporting tables and Power BI dashboards."
        )

        with patch("src.evaluation._resume_evidence_text", return_value=evidence):
            result = evaluate_job(
                "Data Engineer",
                jd,
                company="Google",
                location="New York, NY",
                source="google",
                require_us_location=False,
            )

        self.assertIn("java", result.matched_strong)
        self.assertIn("java", result.unsupported_strong)
        self.assertIn("java", result.critical_skill_gaps)
        self.assertLessEqual(result.score, 72)
        self.assertTrue(any("java" in reason.lower() for reason in result.reasons))


if __name__ == "__main__":
    unittest.main()
