"""
change_detector.py
──────────────────
Detects which source files changed in the current push/PR and extracts
the specific functions and classes that were modified.

Pipeline position:  Git Push → [Change Detector] → Context Builder
Input:              Git diff (via subprocess or GITHUB_SHA env var)
Output:             List of ChangedFile objects ready for context building

How it works:
1. Runs `git diff` between the current commit and its parent
2. Filters the output to only relevant source files
3. Skips files matching EXCLUDED_PATH_FRAGMENTS in config
4. Parses the diff to extract which functions/classes changed
5. Returns a structured list for the context builder to consume
"""

import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from ai_agent.config import (
    REPO_ROOT,
    SRC_DIR,
    WATCHED_EXTENSIONS,
    EXCLUDED_PATH_FRAGMENTS,
)


# ── Data Model ─────────────────────────────────────────────────────────────────

@dataclass
class ChangedFile:
    """
    Represents a single source file that changed in the current push.

    Attributes:
        filepath:          Relative path from repo root  e.g. "backend/routes/auth.py"
        absolute_path:     Full path on disk
        diff:              Raw unified diff for this file only
        changed_functions: Function/method names modified in this diff
        changed_classes:   Class names modified in this diff
        is_new_file:       True if this file was just created (not modified)
        is_deleted:        True if this file was deleted
    """
    filepath:          str
    absolute_path:     str
    diff:              str
    changed_functions: list[str] = field(default_factory=list)
    changed_classes:   list[str] = field(default_factory=list)
    is_new_file:       bool = False
    is_deleted:        bool = False

    def __repr__(self) -> str:
        status = "NEW" if self.is_new_file else ("DELETED" if self.is_deleted else "MODIFIED")
        return (
            f"ChangedFile({self.filepath!r}, {status}, "
            f"funcs={self.changed_functions}, classes={self.changed_classes})"
        )


# ── Public Entry Point ─────────────────────────────────────────────────────────

def detect_changes(
    base_sha: Optional[str] = None,
    head_sha: Optional[str] = None,
) -> list[ChangedFile]:
    """
    Main entry point. Returns a list of ChangedFile objects for all
    relevant source files that changed between base_sha and head_sha.

    Args:
        base_sha: The commit SHA to diff from (defaults to HEAD~1)
        head_sha: The commit SHA to diff to   (defaults to HEAD)

    Returns:
        List of ChangedFile objects (may be empty if no relevant files changed)
    """
    base = base_sha or _resolve_base_sha()
    head = head_sha or "HEAD"

    print(f"[ChangeDetector] Diffing: {base}..{head}")

    raw_diff = _run_git_diff(base, head)

    if not raw_diff.strip():
        print("[ChangeDetector] No changes detected in diff output.")
        return []

    file_diffs = _split_diff_by_file(raw_diff)
    changed_files = []

    for filepath, file_diff in file_diffs.items():
        if not _is_relevant(filepath):
            print(f"[ChangeDetector] Skipping: {filepath}")
            continue

        absolute_path = str(Path(REPO_ROOT) / filepath)
        is_new     = _is_new_file(file_diff)
        is_deleted = _is_deleted_file(file_diff)

        changed_funcs   = _extract_changed_functions(file_diff)
        changed_classes = _extract_changed_classes(file_diff)

        cf = ChangedFile(
            filepath=filepath,
            absolute_path=absolute_path,
            diff=file_diff,
            changed_functions=changed_funcs,
            changed_classes=changed_classes,
            is_new_file=is_new,
            is_deleted=is_deleted,
        )

        print(f"[ChangeDetector] Found: {cf}")
        changed_files.append(cf)

    print(f"[ChangeDetector] Total relevant files: {len(changed_files)}")
    return changed_files


# ── Git Operations ─────────────────────────────────────────────────────────────

def _resolve_base_sha() -> str:
    """
    Determines the base commit SHA to diff against.

    Priority:
    1. GITHUB_BASE_SHA env var (set by GitHub Actions on pull_request events)
    2. HEAD~1 (previous commit — works for push events)
    """
    base_sha = os.getenv("GITHUB_BASE_SHA", "").strip()
    if base_sha:
        print(f"[ChangeDetector] Using GITHUB_BASE_SHA: {base_sha[:8]}")
        return base_sha

    print("[ChangeDetector] GITHUB_BASE_SHA not set — falling back to HEAD~1")
    return "HEAD~1"


def _run_git_diff(base: str, head: str) -> str:
    """
    Runs `git diff` and returns the raw unified diff output as a string.
    Raises RuntimeError if git is not available or the command fails.
    """
    cmd = ["git", "diff", f"{base}..{head}", "--unified=5"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=30,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "git is not installed or not on PATH. "
            "Ensure git is available in the GitHub Actions runner."
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("git diff timed out after 30s.")

    if result.returncode != 0:
        raise RuntimeError(
            f"git diff failed (exit {result.returncode}):\n{result.stderr[:400]}"
        )

    return result.stdout


# ── Diff Parsing ───────────────────────────────────────────────────────────────

def _split_diff_by_file(raw_diff: str) -> dict[str, str]:
    """
    Splits a full unified diff into per-file chunks.

    Returns a dict mapping relative filepath → its diff section.
    """
    # Each file section starts with "diff --git a/... b/..."
    pattern = re.compile(r"^diff --git a/.+ b/(.+)$", re.MULTILINE)
    matches = list(pattern.finditer(raw_diff))

    if not matches:
        return {}

    file_diffs: dict[str, str] = {}

    for i, match in enumerate(matches):
        filepath = match.group(1).strip()
        start    = match.start()
        end      = matches[i + 1].start() if i + 1 < len(matches) else len(raw_diff)
        file_diffs[filepath] = raw_diff[start:end]

    return file_diffs


def _extract_changed_functions(diff: str) -> list[str]:
    """
    Extracts function and method names that appear in the added/modified
    lines of a diff (lines starting with '+').

    Matches patterns like:
        +def my_function(
        +    def _private_method(
        +async def handle_payment(
    """
    pattern = re.compile(
        r"^\+[ \t]*(?:async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(",
        re.MULTILINE,
    )
    return list(dict.fromkeys(pattern.findall(diff)))  # deduplicated, order preserved


def _extract_changed_classes(diff: str) -> list[str]:
    """
    Extracts class names that appear in the added/modified lines of a diff.

    Matches patterns like:
        +class PaymentService:
        +class TransactionValidator(BaseModel):
    """
    pattern = re.compile(
        r"^\+[ \t]*class\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*[:(]",
        re.MULTILINE,
    )
    return list(dict.fromkeys(pattern.findall(diff)))


def _is_new_file(diff: str) -> bool:
    """Returns True if the diff indicates this is a newly created file."""
    return "new file mode" in diff


def _is_deleted_file(diff: str) -> bool:
    """Returns True if the diff indicates this file was deleted."""
    return "deleted file mode" in diff


# ── File Filtering ─────────────────────────────────────────────────────────────

def _is_relevant(filepath: str) -> bool:
    """
    Returns True if a filepath should be processed by the AI agent.

    A file is relevant when ALL of the following are true:
    1. It has a watched extension (e.g. .py)
    2. It lives inside SRC_DIR (e.g. backend/)
    3. Its path does not contain any excluded fragment
    4. It is not itself a test file (test files are outputs, not inputs)
    """
    path = Path(filepath)

    # Must have a watched extension
    if path.suffix not in WATCHED_EXTENSIONS:
        return False

    # Must be inside the source directory
    if not filepath.startswith(SRC_DIR):
        return False

    # Must not be an excluded path (migrations, configs, etc.)
    lower = filepath.lower()
    for fragment in EXCLUDED_PATH_FRAGMENTS:
        if fragment.lower() in lower:
            return False

    # Must not be a test file itself
    name = path.name.lower()
    if name.startswith("test_") or name.endswith("_test.py"):
        return False

    return True


# ── CLI (manual testing) ───────────────────────────────────────────────────────

if __name__ == "__main__":
    """
    Run directly to test change detection locally:

        python ai_agent/change_detector.py
        python ai_agent/change_detector.py <base_sha> <head_sha>
    """
    args = sys.argv[1:]
    base_arg = args[0] if len(args) > 0 else None
    head_arg = args[1] if len(args) > 1 else None

    results = detect_changes(base_sha=base_arg, head_sha=head_arg)

    if not results:
        print("\n[ChangeDetector] No relevant changes found — pipeline will skip AI generation.")
    else:
        print(f"\n[ChangeDetector] {len(results)} file(s) queued for test generation:")
        for cf in results:
            print(f"  • {cf.filepath}")
            if cf.changed_functions:
                print(f"      Functions : {cf.changed_functions}")
            if cf.changed_classes:
                print(f"      Classes   : {cf.changed_classes}")