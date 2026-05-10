"""Candidate profile template with optional local overrides.

Tracked file stays generic. Personal local data should live in
``src/profile_local.py`` which is gitignored.
"""
from __future__ import annotations

PROFILE = {
    "name": "candidate name",
    "email": "",
    "location": "Fairfax, Virginia",
    "preferred_locations": [
        "Fairfax, Virginia",
        "Atlanta, Georgia",
        "Texas",
        "Ohio",
        "Pennsylvania",
    ],
    "location_addresses": {
        "Fairfax, Virginia": "Fairfax, Virginia",
        "Atlanta / Georgia": "10 Ridge Run SE, Marietta, GA",
        "Texas": "8011 N MacArthur Blvd, Irving, TX",
        "Ohio": "1591 Charterwoods Circle, Fairborn, OH 45324",
        "Pennsylvania / Philadelphia": "703 Norwood House Rd, Downingtown, PA 19335",
    },
    "experience_years": 3,
    "education": "M.S. Data Analytics Engineering - George Mason University (GPA 3.97/4.0)",
    "target_roles": [
        "Data Scientist",
        "Data Engineer",
        "Data Analyst",
        "Financial Analyst",
        "Operations Analyst",
        "Research Analyst",
        "Financial Data Analyst",
        "Operations Data Analyst",
        "Research Data Analyst",
        "Analytics Engineer",
        "Machine Learning Engineer",
        "Machine Learning Scientist",
        "MLOps Engineer",
        "Applied Scientist",
        "AI Engineer",
        "Decision Scientist",
        "Research Scientist",
        "Business Intelligence Analyst",
        "Business Intelligence Engineer",
        "Business Intelligence Developer",
        "Data Warehouse Engineer",
        "ML/AI Data Engineer",
        "Product Analyst",
        "Business Analyst",
        "Insights Analyst",
        "Insights Engineer",
        "Reporting Analyst",
        "Product Analytics Engineer",
        "Forecasting Analyst",
        "Experimentation Analyst",
        "Data Platform Engineer",
        "LLM Engineer",
        "Prompt Engineer",
    ],
    "contact_phone": "",
    "linkedin_url": "",
    "github_url": "",
}

SKILLS_STRONG: set[str] = {
    "airflow",
    "apache spark",
    "attention mechanisms",
    "automated retraining",
    "aws",
    "azure",
    "bash",
    "beautifulsoup",
    "bigquery",
    "chroma",
    "chromadb",
    "ci/cd",
    "codex",
    "cursor",
    "data modeling",
    "data warehouse",
    "databricks",
    "dbt",
    "docker",
    "drift detection",
    "duckdb",
    "elt",
    "etl",
    "faiss",
    "fastapi",
    "git",
    "github",
    "github actions",
    "gcp",
    "glue",
    "google analytics",
    "hadoop",
    "hugging face",
    "hugging face transformers",
    "java",
    "kafka",
    "kinesis",
    "kubernetes",
    "lambda",
    "lightgbm",
    "linux",
    "llm evaluation",
    "llm fine-tuning",
    "lstm",
    "machine learning",
    "matplotlib",
    "mcp",
    "ml",
    "mlflow",
    "model monitoring",
    "mongodb",
    "monte carlo",
    "mysql",
    "nltk",
    "numpy",
    "openai api",
    "pandas",
    "pipeline",
    "postgres",
    "postgresql",
    "power bi",
    "prompt engineering",
    "pyspark",
    "python",
    "pytorch",
    "quicksight",
    "rag",
    "redshift",
    "rest api",
    "r",
    "s3",
    "sagemaker",
    "scikit-learn",
    "sklearn",
    "shap",
    "snowflake",
    "spark",
    "sql",
    "sql server",
    "streamlit",
    "tableau",
    "tensorflow",
    "transfer learning",
    "transformer",
    "transformer architectures",
    "xgboost",
}

SKILLS_MODERATE: set[str] = {
    "alteryx",
    "chain-of-thought prompting",
    "excel",
    "google cloud",
    "hive",
    "hql",
    "looker",
}

try:
    from .profile_local import PROFILE as LOCAL_PROFILE
    from .profile_local import SKILLS_MODERATE as LOCAL_SKILLS_MODERATE
    from .profile_local import SKILLS_STRONG as LOCAL_SKILLS_STRONG
except ImportError:
    LOCAL_PROFILE = None
    LOCAL_SKILLS_STRONG = None
    LOCAL_SKILLS_MODERATE = None

if isinstance(LOCAL_PROFILE, dict):
    PROFILE = LOCAL_PROFILE
if isinstance(LOCAL_SKILLS_STRONG, set):
    SKILLS_STRONG = LOCAL_SKILLS_STRONG
if isinstance(LOCAL_SKILLS_MODERATE, set):
    SKILLS_MODERATE = LOCAL_SKILLS_MODERATE

_STRONG_BONUS = 8
_MODERATE_BONUS = 3


def skill_bonus(text: str, cap: int = 20) -> int:
    """Return a skill-match bonus (0-cap) based on skills found in ``text``."""
    t = (text or "").lower()
    bonus = 0
    for skill in SKILLS_STRONG:
        if skill in t:
            bonus += _STRONG_BONUS
    for skill in SKILLS_MODERATE:
        if skill in t:
            bonus += _MODERATE_BONUS
    return min(bonus, cap)


def profile_summary_html() -> str:
    return (
        f"<p style='font-size:12px;color:#666;margin:0 0 8px'>"
        f"Matched for <strong>{PROFILE['name']}</strong> - "
        f"targeting <em>{', '.join(PROFILE['target_roles'][:4])}...</em></p>"
    )


def profile_summary_text() -> str:
    return (
        f"Profile: {PROFILE['name']} | "
        f"Target: {', '.join(PROFILE['target_roles'][:3])}..."
    )
