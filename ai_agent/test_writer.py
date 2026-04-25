"""
test_writer.py
──────────────
Writes validated test code to the correct file paths and creates
a Git branch + Pull Request with the generated tests.

Pipeline position:  Retry Controller → [Test Writer] → Test Runner
Input:              List of RetryOutcome objects with validated test code
Output:             New Git branch + PR opened on GitHub

Safety rules (never violated):
- NEVER commits directly to main or the triggering branch
- NEVER overwrites files without first backing up the original
- NEVER writes code that failed validation
- Always creates a clean branch per pipeline run
"""

import os
import subprocess
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from ai_agent.retry_controller import RetryOutcome
from ai_agent.config import (
    REPO_ROOT,
    TEST_DIR,
    GITHUB_TOKEN,
    GITHUB_REPOSITORY,
    GITHUB_REF_NAME,
    GITHUB_RUN_ID,
    GENERATED_BRANCH_PREFIX,
)


# ── Data Model ─────────────────────────────────────────────────────────────────

class WriteResult:
    """
    Result of writing all generated test files and creating the PR.

    Attributes:
        branch_name:    The Git branch created (e.g. patch/ai-tests-12345)
        pr_url:         URL of the opened Pull Request (empty if PR creation failed)
        written_files:  List of file paths successfully written
        skipped_files:  List of file paths skipped (failed validation / no code)
        errors:         Any errors encountered during write or PR creation
    """
    def __init__(self):
        self.branch_name:   str       = ""
        self.pr_url:        str       = ""
        self.written_files: list[str] = []
        self.skipped_files: list[str] = []
        self.errors:        list[str] = []

    @property
    def succeeded(self) -> bool:
        return bool(self.written_files) and not self.errors

    def __repr__(self) -> str:
        return (
            f"WriteResult(branch={self.branch_name!r}, "
            f"written={len(self.written_files)}, "
            f"skipped={len(self.skipped_files)}, "
            f"pr={self.pr_url!r})"
        )


# ── Public Entry Point ─────────────────────────────────────────────────────────

def write_and_create_pr(outcomes: list[RetryOutcome]) -> WriteResult:
    """
    Writes all successfully generated test files to disk,
    commits them to a new branch, and opens a Pull Request.

    Args:
        outcomes: List of RetryOutcome objects from retry_controller.run_all_with_retry()

    Returns:
        WriteResult with branch name, PR URL, and file lists
    """
    result = WriteResult()

    # Filter to only successful outcomes with code
    successful = [o for o in outcomes if o.succeeded and o.code.strip()]
    failed     = [o for o in outcomes if not o.succeeded]

    for outcome in failed:
        result.skipped_files.append(outcome.filepath)
        print(f"[TestWriter] Skipping (failed validation): {outcome.filepath}")

    if not successful:
        print("[TestWriter] No successfully generated tests to write — skipping branch creation")
        return result

    # ── Step 1: Create branch ──────────────────────────────────────────────────
    branch_name = _create_branch()
    if not branch_name:
        result.errors.append("Failed to create Git branch — aborting write")
        return result

    result.branch_name = branch_name

    # ── Step 2: Write files ────────────────────────────────────────────────────
    for outcome in successful:
        written = _write_test_file(outcome)
        if written:
            result.written_files.append(written)
        else:
            result.skipped_files.append(outcome.filepath)

    if not result.written_files:
        print("[TestWriter] No files were written — aborting commit")
        _cleanup_branch(branch_name)
        return result

    # ── Step 3: Commit & push ──────────────────────────────────────────────────
    committed = _commit_and_push(branch_name, result.written_files)
    if not committed:
        result.errors.append("Git commit/push failed")
        return result

    # ── Step 4: Open Pull Request ──────────────────────────────────────────────
    pr_url = _open_pull_request(
        branch_name=branch_name,
        written_files=result.written_files,
        outcomes=outcomes,
    )
    result.pr_url = pr_url

    print(f"\n[TestWriter] Done: {result}")
    return result


# ── Branch Management ──────────────────────────────────────────────────────────

def _create_branch() -> str:
    """
    Creates a new Git branch for the generated tests.
    Branch name format: patch/ai-tests-{run_id}-{timestamp}

    Returns the branch name on success, empty string on failure.
    """
    timestamp   = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    branch_name = f"{GENERATED_BRANCH_PREFIX}-{GITHUB_RUN_ID}-{timestamp}"

    print(f"[TestWriter] Creating branch: {branch_name}")

    # Ensure we start from the latest state of the triggering branch
    cmds = [
        ["git", "fetch", "origin"],
        ["git", "checkout", GITHUB_REF_NAME],
        ["git", "pull", "origin", GITHUB_REF_NAME],
        ["git", "checkout", "-b", branch_name],
    ]

    for cmd in cmds:
        ok, stderr = _run_git(cmd)
        if not ok:
            print(f"[TestWriter] ✗ Branch creation failed at: {' '.join(cmd)}\n  {stderr}")
            return ""

    print(f"[TestWriter] ✓ Branch created: {branch_name}")
    return branch_name


def _cleanup_branch(branch_name: str) -> None:
    """Deletes a locally created branch if nothing was committed to it."""
    _run_git(["git", "checkout", GITHUB_REF_NAME])
    _run_git(["git", "branch", "-D", branch_name])
    print(f"[TestWriter] Cleaned up empty branch: {branch_name}")


# ── File Writing ───────────────────────────────────────────────────────────────

def _write_test_file(outcome: RetryOutcome) -> str:
    """
    Writes the validated test code to the correct path under TEST_DIR.

    - Creates parent directories if they don't exist
    - Backs up any existing file before overwriting
    - Ensures a conftest.py exists in the test subdirectory

    Args:
        outcome: A successful RetryOutcome with code and test_filepath

    Returns:
        The written file path on success, empty string on failure
    """
    # Derive test filepath from source filepath
    test_filepath = _resolve_test_filepath(outcome.filepath)
    absolute_path = Path(REPO_ROOT) / test_filepath

    print(f"[TestWriter] Writing: {test_filepath}")

    # ── Create parent directories ──────────────────────────────────────────────
    absolute_path.parent.mkdir(parents=True, exist_ok=True)

    # ── Backup existing file ───────────────────────────────────────────────────
    if absolute_path.exists():
        backup_path = absolute_path.with_suffix(f".py.bak")
        try:
            backup_path.write_text(absolute_path.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"[TestWriter] Backed up existing file to: {backup_path.name}")
        except OSError as e:
            print(f"[TestWriter] ⚠ Could not back up existing file: {e}")

    # ── Write generated code ───────────────────────────────────────────────────
    try:
        absolute_path.write_text(outcome.code, encoding="utf-8")
        print(f"[TestWriter] ✓ Written: {test_filepath} ({len(outcome.code)} chars)")
    except OSError as e:
        print(f"[TestWriter] ✗ Write failed for {test_filepath}: {e}")
        return ""

    # ── Ensure conftest.py exists in test subdirectory ─────────────────────────
    _ensure_conftest(absolute_path.parent)

    return test_filepath


def _resolve_test_filepath(source_filepath: str) -> str:
    """
    Maps a source filepath to its test filepath.

    backend/services/payment.py   → tests/services/test_payment.py
    backend/routes/auth.py        → tests/routes/test_auth.py
    """
    path = Path(source_filepath)

    # Strip the leading src dir (e.g. "backend")
    parts = path.parts
    src_parts = Path(os.getenv("SRC_DIR", "backend")).parts

    # Remove matching prefix
    if parts[:len(src_parts)] == src_parts:
        relative_parts = parts[len(src_parts):]
    else:
        relative_parts = parts

    relative      = Path(*relative_parts) if relative_parts else path
    test_filename = f"test_{relative.name}"
    test_path     = Path(TEST_DIR) / relative.parent / test_filename

    return str(test_path)


def _ensure_conftest(directory: Path) -> None:
    """
    Ensures a conftest.py exists in the given test directory.
    Creates a minimal one if absent — pytest requires it for fixture discovery.
    """
    conftest = directory / "conftest.py"
    if not conftest.exists():
        conftest.write_text(
            '"""Shared pytest fixtures for this test package."""\n'
            "import pytest\n",
            encoding="utf-8",
        )
        print(f"[TestWriter] Created conftest.py in: {directory}")


# ── Git Commit & Push ──────────────────────────────────────────────────────────

def _commit_and_push(branch_name: str, written_files: list[str]) -> bool:
    """
    Stages the written test files, commits, and pushes to GitHub.

    Returns True on success, False on failure.
    """
    print(f"[TestWriter] Committing {len(written_files)} file(s) to {branch_name}")

    # Configure git identity for the Actions bot
    _run_git(["git", "config", "user.name",  "AI Test Generator"])
    _run_git(["git", "config", "user.email", "ai-test-generator@github-actions"])

    # Stage only the written test files
    for filepath in written_files:
        ok, stderr = _run_git(["git", "add", filepath])
        if not ok:
            print(f"[TestWriter] ✗ git add failed for {filepath}: {stderr}")
            return False

    # Also stage any new conftest.py files
    _run_git(["git", "add", f"{TEST_DIR}/**/conftest.py"])

    # Commit
    commit_msg = _build_commit_message(written_files)
    ok, stderr = _run_git(["git", "commit", "-m", commit_msg])
    if not ok:
        print(f"[TestWriter] ✗ git commit failed: {stderr}")
        return False

    # Push
    ok, stderr = _run_git(["git", "push", "origin", branch_name])
    if not ok:
        print(f"[TestWriter] ✗ git push failed: {stderr}")
        return False

    print(f"[TestWriter] ✓ Committed and pushed to: {branch_name}")
    return True


def _build_commit_message(written_files: list[str]) -> str:
    """Builds a descriptive commit message listing all generated test files."""
    file_list = "\n".join(f"  - {f}" for f in written_files)
    return (
        f"test(ai-generated): add/update unit tests [run {GITHUB_RUN_ID}]\n\n"
        f"Auto-generated by AI Unit Test Generator.\n"
        f"Files updated:\n{file_list}\n\n"
        f"Review carefully before merging."
    )


# ── Pull Request Creation ──────────────────────────────────────────────────────

def _open_pull_request(
    branch_name:   str,
    written_files: list[str],
    outcomes:      list[RetryOutcome],
) -> str:
    """
    Opens a Pull Request on GitHub via the REST API.

    Returns the PR URL on success, empty string on failure.
    """
    if not GITHUB_TOKEN:
        print("[TestWriter] GITHUB_TOKEN not set — skipping PR creation")
        return ""

    if not GITHUB_REPOSITORY:
        print("[TestWriter] GITHUB_REPOSITORY not set — skipping PR creation")
        return ""

    print(f"[TestWriter] Opening PR: {branch_name} → {GITHUB_REF_NAME}")

    url     = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/pulls"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept":        "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    body = _build_pr_body(written_files, outcomes)

    payload = {
        "title": f"🤖 AI-Generated Tests — Run {GITHUB_RUN_ID}",
        "body":  body,
        "head":  branch_name,
        "base":  GITHUB_REF_NAME,
        "draft": True,   # Always open as draft — requires human review before merge
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
    except requests.RequestException as e:
        print(f"[TestWriter] ✗ PR API call failed: {e}")
        return ""

    if response.status_code == 201:
        pr_url = response.json().get("html_url", "")
        print(f"[TestWriter] ✓ PR opened: {pr_url}")
        return pr_url
    else:
        print(f"[TestWriter] ✗ PR creation failed ({response.status_code}): {response.text[:300]}")
        return ""


def _build_pr_body(written_files: list[str], outcomes: list[RetryOutcome]) -> str:
    """Builds a descriptive PR body with generation stats and file list."""
    succeeded = [o for o in outcomes if o.succeeded]
    failed    = [o for o in outcomes if not o.succeeded]

    file_rows = "\n".join(
        f"| `{f}` | ✅ Generated |"
        for f in written_files
    )
    failed_rows = "\n".join(
        f"| `{o.filepath}` | ❌ Failed after {o.attempt_count} attempt(s) |"
        for o in failed
    )

    failed_section = (
        f"\n### ❌ Failed Files (require manual tests)\n"
        f"| Source File | Status |\n|---|---|\n{failed_rows}\n"
        if failed_rows else ""
    )

    return f"""## 🤖 AI-Generated Unit Tests

> **Auto-generated by AI Unit Test Generator — Run `{GITHUB_RUN_ID}`**
> ⚠️ **Review all tests carefully before merging.**

---

### 📊 Generation Summary

| Metric | Value |
|---|---|
| Files processed | {len(outcomes)} |
| Tests generated | {len(succeeded)} |
| Failed | {len(failed)} |
| Target branch | `{GITHUB_REF_NAME}` |

---

### ✅ Generated Test Files

| Test File | Status |
|---|---|
{file_rows}
{failed_section}

---

### 🔍 Review Checklist

- [ ] All test assertions are logically correct
- [ ] Mocks reflect actual module interfaces
- [ ] Edge cases match real business rules
- [ ] No real credentials or PII in test data
- [ ] Coverage of happy path, edge cases, and error paths

---

*This PR was opened as a **draft** — it will not auto-merge.*
*Resolve any failing tests, review the logic, then mark ready for review.*
"""


# ── Git Helper ─────────────────────────────────────────────────────────────────

def _run_git(cmd: list[str]) -> tuple[bool, str]:
    """
    Runs a git command in REPO_ROOT.
    Returns (success, stderr_or_stdout).
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=60,
        )
        if result.returncode != 0:
            return False, result.stderr.strip()
        return True, result.stdout.strip()
    except subprocess.TimeoutExpired:
        return False, f"Command timed out: {' '.join(cmd)}"
    except FileNotFoundError:
        return False, "git not found on PATH"