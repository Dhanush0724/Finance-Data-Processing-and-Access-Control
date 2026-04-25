"""
config.py
─────────
Central configuration for the AI Unit Test Generator.

All environment variables are read here and nowhere else.
Every other module imports from this file — never from os.environ directly.

Local development  : copy .env.example → .env and fill in your values
GitHub Actions     : set secrets via Settings → Secrets → Actions
"""

import os
from dotenv import load_dotenv

# Load .env file if present (local development only — no effect in CI)
load_dotenv()


# ── OpenRouter ─────────────────────────────────────────────────────────────────

# Your OpenRouter API key — get one at https://openrouter.ai/keys
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")

# The model to use — any model available on OpenRouter works here
# See full list: https://openrouter.ai/models
# Recommended options:
#   anthropic/claude-sonnet-4-5       — best reasoning, higher cost
#   openai/gpt-4o                     — strong all-rounder
#   openai/gpt-4o-mini                — fast and cheap, good for retries
#   google/gemini-2.0-flash           — fast, large context window
#   deepseek/deepseek-chat            — very cost-effective
OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4-5")

# OpenRouter base URL — do not change unless OpenRouter moves their API
OPENROUTER_BASE_URL: str = os.getenv(
    "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
)

# Shown in your OpenRouter usage dashboard under "App"
OPENROUTER_APP_URL: str  = os.getenv("OPENROUTER_APP_URL", "https://github.com")
OPENROUTER_APP_NAME: str = os.getenv("OPENROUTER_APP_NAME", "AI-Unit-Test-Generator")

# Sampling temperature — 0.0 = deterministic, 1.0 = creative
# Keep low (0.2) for test generation — we want consistent, correct code
OPENROUTER_TEMPERATURE: float = float(os.getenv("OPENROUTER_TEMPERATURE", "0.2"))


# ── Project Paths ──────────────────────────────────────────────────────────────

# Root of the repository (where the workflow runs from)
REPO_ROOT: str = os.getenv("GITHUB_WORKSPACE", os.getcwd())

# Directory containing the source code to test
SRC_DIR: str = os.getenv("SRC_DIR", "backend")

# Directory where generated test files are written
TEST_DIR: str = os.getenv("TEST_DIR", "tests")

# Path to the AI knowledge base file injected into every agent prompt
KNOWLEDGE_FILE: str = os.getenv(
    "KNOWLEDGE_FILE", "ai_agent/knowledge/knowledge.md"
)


# ── Retry & Generation ─────────────────────────────────────────────────────────

# Maximum number of AI generation + validation attempts before escalating
MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))

# Maximum tokens the model can generate per response
MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "4096"))


# ── Git & GitHub ───────────────────────────────────────────────────────────────

# GitHub token — auto-provided by GitHub Actions, set manually for local runs
GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")

# The repository in "owner/repo" format — auto-set by GitHub Actions
GITHUB_REPOSITORY: str = os.getenv("GITHUB_REPOSITORY", "")

# The branch that triggered the workflow
GITHUB_REF_NAME: str = os.getenv("GITHUB_REF_NAME", "main")

# Unique run ID used to name the generated test branch
GITHUB_RUN_ID: str = os.getenv("GITHUB_RUN_ID", "local")

# Branch name format for AI-generated test PRs
GENERATED_BRANCH_PREFIX: str = os.getenv(
    "GENERATED_BRANCH_PREFIX", "patch/ai-tests"
)


# ── Notifications ──────────────────────────────────────────────────────────────

# Microsoft Teams incoming webhook URL (optional)
TEAMS_WEBHOOK_URL: str = os.getenv("TEAMS_WEBHOOK_URL", "")

# SMTP settings for email notifications (all optional)
SMTP_HOST: str  = os.getenv("SMTP_HOST", "")
SMTP_PORT: int  = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER: str  = os.getenv("SMTP_USER", "")
SMTP_PASS: str  = os.getenv("SMTP_PASS", "")

# Who receives failure/escalation emails
NOTIFY_EMAIL: str = os.getenv("NOTIFY_EMAIL", "")


# ── File Filtering ─────────────────────────────────────────────────────────────

# Only these file extensions are considered for test generation
WATCHED_EXTENSIONS: list[str] = [".py"]

# Paths containing any of these substrings are skipped by the change detector
EXCLUDED_PATH_FRAGMENTS: list[str] = [
    "migrations",
    "alembic",
    "__pycache__",
    ".pyc",
    "conftest",
    "settings",
    "config",
    "manage.py",
    "setup.py",
    "wsgi.py",
    "asgi.py",
]


# ── Validation ─────────────────────────────────────────────────────────────────

# Minimum number of test functions the AI must produce
MIN_TEST_FUNCTIONS: int = int(os.getenv("MIN_TEST_FUNCTIONS", "1"))


# ── Sanity Check (fail fast on startup if critical values are missing) ─────────

def validate_config() -> None:
    """
    Call this at startup (in main.py) to catch missing secrets early.
    Raises ValueError listing ALL missing required variables at once.
    """
    missing = []

    if not OPENROUTER_API_KEY:
        missing.append("OPENROUTER_API_KEY")
    if not GITHUB_TOKEN:
        missing.append("GITHUB_TOKEN")
    if not GITHUB_REPOSITORY:
        missing.append("GITHUB_REPOSITORY")

    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            f"  • Local : add them to your .env file\n"
            f"  • CI     : Settings → Secrets → Actions"
        )


# ── Debug Helper ───────────────────────────────────────────────────────────────

def print_config() -> None:
    """Prints non-sensitive config values — useful for debugging pipeline runs."""
    print("[Config] ── Runtime Configuration ──────────────────────")
    print(f"[Config] Model          : {OPENROUTER_MODEL}")
    print(f"[Config] Temperature    : {OPENROUTER_TEMPERATURE}")
    print(f"[Config] Max Tokens     : {MAX_TOKENS}")
    print(f"[Config] Max Retries    : {MAX_RETRIES}")
    print(f"[Config] Src Dir        : {SRC_DIR}")
    print(f"[Config] Test Dir       : {TEST_DIR}")
    print(f"[Config] Knowledge File : {KNOWLEDGE_FILE}")
    print(f"[Config] Repository     : {GITHUB_REPOSITORY}")
    print(f"[Config] Branch         : {GITHUB_REF_NAME}")
    print(f"[Config] Run ID         : {GITHUB_RUN_ID}")
    print(f"[Config] Teams Webhook  : {'set' if TEAMS_WEBHOOK_URL else 'not set'}")
    print(f"[Config] Email Notify   : {'set' if NOTIFY_EMAIL else 'not set'}")
    print(f"[Config] API Key        : {'set' if OPENROUTER_API_KEY else '*** MISSING ***'}")
    print("[Config] ────────────────────────────────────────────────")