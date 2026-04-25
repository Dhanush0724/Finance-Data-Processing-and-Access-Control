"""
test_runner.py
──────────────
Executes the full pytest suite with coverage and captures structured results.

Pipeline position:  Test Writer → [Test Runner] → Reporter
Input:              List of written test file paths + optional specific files to run
Output:             TestRunResult with pass/fail counts, coverage delta, and diagnostics

Two run modes:
1. Targeted run  — runs only the newly generated test files (fast, used after generation)
2. Full suite    — runs the entire test suite (used for final coverage delta calculation)

Coverage is measured with pytest-cov and reported as JSON for machine parsing.
"""

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from ai_agent.config import (
    REPO_ROOT,
    SRC_DIR,
    TEST_DIR,
)


# ── Data Models ────────────────────────────────────────────────────────────────

@dataclass
class TestCaseResult:
    """Result of a single test function."""
    name:     str
    status:   str          # "passed" | "failed" | "error" | "skipped"
    duration: float = 0.0
    message:  str   = ""   # Failure message or error traceback


@dataclass
class CoverageReport:
    """
    Coverage metrics extracted from pytest-cov JSON output.

    Attributes:
        total_coverage:  Overall coverage percentage (0-100)
        covered_lines:   Total lines covered across all measured files
        missing_lines:   Total lines not covered
        file_coverage:   Per-file coverage breakdown {filepath: pct}
    """
    total_coverage: float             = 0.0
    covered_lines:  int               = 0
    missing_lines:  int               = 0
    file_coverage:  dict[str, float]  = field(default_factory=dict)

    def __repr__(self) -> str:
        return (
            f"CoverageReport(total={self.total_coverage:.1f}%, "
            f"covered={self.covered_lines}, missing={self.missing_lines})"
        )


@dataclass
class TestRunResult:
    """
    Complete result of a pytest run.

    Attributes:
        passed:          Number of tests that passed
        failed:          Number of tests that failed
        errors:          Number of tests that errored
        skipped:         Number of tests skipped
        duration_s:      Total run time in seconds
        coverage:        Coverage report (None if coverage not measured)
        coverage_delta:  Change in coverage vs previous run (None if not applicable)
        test_cases:      Individual test results (populated if verbose=True)
        raw_output:      Full pytest stdout + stderr for diagnostics
        returncode:      pytest exit code (0=all passed, 1=some failed, 2=interrupted, 5=no tests)
        diagnostics:     Formatted failure summary for the retry controller / reporter
    """
    passed:         int                    = 0
    failed:         int                    = 0
    errors:         int                    = 0
    skipped:        int                    = 0
    duration_s:     float                  = 0.0
    coverage:       CoverageReport | None  = None
    coverage_delta: float | None           = None
    test_cases:     list[TestCaseResult]   = field(default_factory=list)
    raw_output:     str                    = ""
    returncode:     int                    = -1
    diagnostics:    str                    = ""

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.errors + self.skipped

    @property
    def all_passed(self) -> bool:
        return self.failed == 0 and self.errors == 0 and self.returncode in (0, 5)

    @property
    def has_tests(self) -> bool:
        return self.total > 0

    def __repr__(self) -> str:
        status = "PASS" if self.all_passed else "FAIL"
        cov    = f", cov={self.coverage.total_coverage:.1f}%" if self.coverage else ""
        return (
            f"TestRunResult({status}, "
            f"passed={self.passed}, failed={self.failed}, "
            f"errors={self.errors}{cov}, {self.duration_s:.1f}s)"
        )


# ── Public Entry Points ────────────────────────────────────────────────────────

def run_targeted(test_files: list[str]) -> TestRunResult:
    """
    Runs only the specified test files — used immediately after generation
    to verify the new tests pass before measuring full suite coverage.

    Args:
        test_files: List of relative test file paths to run

    Returns:
        TestRunResult for the targeted run
    """
    if not test_files:
        print("[TestRunner] No test files specified for targeted run")
        return TestRunResult(returncode=5, diagnostics="No test files to run.")

    print(f"[TestRunner] Targeted run: {len(test_files)} file(s)")
    for f in test_files:
        print(f"  • {f}")

    return _run_pytest(
        targets=test_files,
        measure_coverage=True,
        label="targeted",
    )


def run_full_suite(baseline_coverage: float | None = None) -> TestRunResult:
    """
    Runs the entire test suite under TEST_DIR with full coverage measurement.
    Used to calculate the overall coverage delta after tests are generated.

    Args:
        baseline_coverage: Previous coverage percentage to compute delta against

    Returns:
        TestRunResult with coverage and optional coverage_delta
    """
    print(f"[TestRunner] Full suite run: {TEST_DIR}/")

    result = _run_pytest(
        targets=[TEST_DIR],
        measure_coverage=True,
        label="full-suite",
    )

    # Calculate coverage delta if we have a baseline
    if baseline_coverage is not None and result.coverage:
        result.coverage_delta = result.coverage.total_coverage - baseline_coverage
        delta_sign = "+" if result.coverage_delta >= 0 else ""
        print(
            f"[TestRunner] Coverage delta: {delta_sign}{result.coverage_delta:.2f}% "
            f"({baseline_coverage:.1f}% → {result.coverage.total_coverage:.1f}%)"
        )

    return result


def get_current_coverage() -> float:
    """
    Runs a quick coverage-only pass to capture the baseline before
    any new tests are written. Used by main.py to get the pre-run baseline.

    Returns:
        Current total coverage percentage, or 0.0 if measurement fails
    """
    print("[TestRunner] Measuring baseline coverage...")
    result = _run_pytest(
        targets=[TEST_DIR],
        measure_coverage=True,
        label="baseline",
    )
    if result.coverage:
        return result.coverage.total_coverage
    return 0.0


# ── Core pytest Runner ─────────────────────────────────────────────────────────

def _run_pytest(
    targets:          list[str],
    measure_coverage: bool = True,
    label:            str  = "run",
) -> TestRunResult:
    """
    Builds and executes a pytest command, parses the output, and returns
    a structured TestRunResult.

    Args:
        targets:          List of file paths or directories to pass to pytest
        measure_coverage: Whether to run with --cov and generate a JSON report
        label:            Label for log messages

    Returns:
        Populated TestRunResult
    """
    coverage_json = Path(REPO_ROOT) / f".coverage_report_{label}.json"
    cmd = _build_pytest_command(targets, measure_coverage, coverage_json)

    print(f"[TestRunner] Command: {' '.join(cmd)}")

    start = time.monotonic()
    proc  = _execute(cmd)
    duration = time.monotonic() - start

    raw_output = (proc.stdout or "") + (proc.stderr or "")

    print(f"[TestRunner] Completed in {duration:.1f}s — exit code: {proc.returncode}")

    # Parse pytest summary line from stdout
    passed, failed, errors, skipped = _parse_summary(raw_output)

    # Parse coverage JSON if it was generated
    coverage = None
    if measure_coverage and coverage_json.exists():
        coverage = _parse_coverage_json(coverage_json)
        # Clean up the temporary coverage file
        try:
            coverage_json.unlink()
        except OSError:
            pass

    result = TestRunResult(
        passed=passed,
        failed=failed,
        errors=errors,
        skipped=skipped,
        duration_s=duration,
        coverage=coverage,
        raw_output=raw_output,
        returncode=proc.returncode,
    )

    # Build diagnostics from failures (fed back to reporter / retry controller)
    if not result.all_passed:
        result.diagnostics = _extract_failure_diagnostics(raw_output)

    _log_result(result, label)
    return result


def _build_pytest_command(
    targets:       list[str],
    with_coverage: bool,
    coverage_json: Path,
) -> list[str]:
    """Builds the pytest CLI command with all required flags."""
    cmd = [
        sys.executable, "-m", "pytest",
        *targets,
        "--tb=short",           # Short tracebacks — enough to diagnose, not overwhelming
        "--no-header",          # Cleaner output
        "-q",                   # Quiet — suppress per-test dots, show summary only
        "--timeout=60",         # Per-test timeout (requires pytest-timeout)
    ]

    if with_coverage:
        cmd.extend([
            f"--cov={SRC_DIR}",
            "--cov-report=json:" + str(coverage_json),
            "--cov-report=term-missing:skip-covered",
            "--cov-branch",     # Branch coverage (more thorough than line coverage)
        ])

    return cmd


def _execute(cmd: list[str]) -> subprocess.CompletedProcess:
    """Runs the pytest command and returns the CompletedProcess."""
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=600,        # 10-minute hard cap for the full suite
        )
    except subprocess.TimeoutExpired:
        print("[TestRunner] ✗ pytest timed out after 600s")
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=2,
            stdout="",
            stderr="pytest run timed out after 600 seconds",
        )
    except FileNotFoundError:
        print("[TestRunner] ✗ pytest not found — is it installed?")
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=2,
            stdout="",
            stderr="pytest executable not found",
        )


# ── Output Parsers ─────────────────────────────────────────────────────────────

def _parse_summary(output: str) -> tuple[int, int, int, int]:
    """
    Parses the pytest summary line to extract pass/fail/error/skip counts.

    Handles formats like:
        5 passed, 2 failed, 1 error, 3 skipped in 4.32s
        10 passed in 1.23s
        no tests ran
    """
    import re

    passed = failed = errors = skipped = 0

    # Match individual counts from the summary line
    patterns = {
        "passed":  r"(\d+)\s+passed",
        "failed":  r"(\d+)\s+failed",
        "error":   r"(\d+)\s+error",
        "skipped": r"(\d+)\s+skipped",
    }

    # Look for the summary line (last line containing "passed" or "failed" or "error")
    for line in reversed(output.splitlines()):
        line_lower = line.lower()
        if any(k in line_lower for k in ("passed", "failed", "error", "no tests")):
            for key, pattern in patterns.items():
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    count = int(match.group(1))
                    if key == "passed":  passed  = count
                    if key == "failed":  failed  = count
                    if key == "error":   errors  = count
                    if key == "skipped": skipped = count
            break

    return passed, failed, errors, skipped


def _parse_coverage_json(json_path: Path) -> CoverageReport | None:
    """
    Parses the pytest-cov JSON output file into a CoverageReport.

    The JSON structure (from coverage.py):
    {
        "totals": { "percent_covered": 72.3, "covered_lines": 500, "missing_lines": 193 },
        "files": { "backend/services/payment.py": { "summary": { "percent_covered": 85.0 } } }
    }
    """
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"[TestRunner] Could not parse coverage JSON: {e}")
        return None

    totals = data.get("totals", {})
    files  = data.get("files", {})

    file_coverage = {
        filepath: round(info.get("summary", {}).get("percent_covered", 0.0), 1)
        for filepath, info in files.items()
    }

    return CoverageReport(
        total_coverage=round(totals.get("percent_covered", 0.0), 2),
        covered_lines=totals.get("covered_lines", 0),
        missing_lines=totals.get("missing_lines", 0),
        file_coverage=file_coverage,
    )


def _extract_failure_diagnostics(output: str) -> str:
    """
    Extracts the failure section from pytest output for use in
    the reporter and retry feedback.

    Captures everything between FAILURES/ERRORS sections and the summary line.
    """
    lines      = output.splitlines()
    capturing  = False
    diagnostic_lines: list[str] = []
    max_lines  = 150   # Cap diagnostics length to avoid bloating the AI prompt

    for line in lines:
        # Start capturing at failure/error sections
        if line.startswith("FAILURES") or line.startswith("ERRORS") or "_ FAILED _" in line:
            capturing = True

        # Stop at the short test summary section
        if capturing and line.startswith("short test summary"):
            break

        if capturing:
            diagnostic_lines.append(line)
            if len(diagnostic_lines) >= max_lines:
                diagnostic_lines.append("... (truncated)")
                break

    if not diagnostic_lines:
        # Fall back to last 50 lines of output
        diagnostic_lines = lines[-50:]

    return "\n".join(diagnostic_lines)


# ── Logging ────────────────────────────────────────────────────────────────────

def _log_result(result: TestRunResult, label: str) -> None:
    """Prints a clean summary of the test run to stdout."""
    status = "✓ ALL PASSED" if result.all_passed else "✗ FAILURES DETECTED"
    print(f"\n[TestRunner] ── {label.upper()} Run Result ─────────────────────────")
    print(f"  Status  : {status}")
    print(f"  Passed  : {result.passed}")
    print(f"  Failed  : {result.failed}")
    print(f"  Errors  : {result.errors}")
    print(f"  Skipped : {result.skipped}")
    print(f"  Total   : {result.total}")
    print(f"  Time    : {result.duration_s:.2f}s")

    if result.coverage:
        cov = result.coverage
        delta_str = ""
        if result.coverage_delta is not None:
            sign = "+" if result.coverage_delta >= 0 else ""
            delta_str = f" ({sign}{result.coverage_delta:.2f}%)"
        print(f"  Coverage: {cov.total_coverage:.1f}%{delta_str}")
        print(f"  Lines   : {cov.covered_lines} covered, {cov.missing_lines} missing")

    print(f"[TestRunner] ─────────────────────────────────────────────────────────\n")


# ── CLI (manual testing) ───────────────────────────────────────────────────────

if __name__ == "__main__":
    """
    Run directly to execute tests manually:

        python ai_agent/test_runner.py                          # full suite
        python ai_agent/test_runner.py tests/services/          # targeted directory
        python ai_agent/test_runner.py tests/services/test_payment.py  # single file
    """
    args    = sys.argv[1:]
    targets = args if args else None

    if targets:
        result = run_targeted(targets)
    else:
        result = run_full_suite()

    print(result)
    sys.exit(0 if result.all_passed else 1)