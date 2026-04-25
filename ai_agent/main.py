"""
main.py
───────
Orchestrator for the AI Unit Test Generator pipeline.

Entry point for GitHub Actions. Wires all modules together in sequence
and handles top-level error routing.

Full pipeline:
    1.  Validate config        — fail fast if secrets are missing
    2.  Detect changes         — git diff → relevant changed files
    3.  Early exit             — skip if no relevant files changed
    4.  Measure baseline       — capture coverage before generation
    5.  Build contexts         — assemble AI prompt payloads per file
    6.  Generate with retry    — AI agent + validator + retry loop
    7.  Write & create PR      — write files, commit, open draft PR
    8.  Run targeted tests     — verify generated tests pass
    9.  Run full suite         — measure coverage delta
    10. Report results         — PR comment + Teams + email

Exit codes:
    0 — pipeline completed (tests generated and passing)
    1 — pipeline failed (generation failed or tests failing)
    2 — configuration error (missing secrets)
    3 — no relevant changes (skip — not an error)
"""

import os
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ai_agent.config import (
    validate_config,
    print_config,
    MAX_RETRIES,
    GITHUB_RUN_ID,
)
from ai_agent.change_detector import detect_changes
from ai_agent.context_builder import build_all_contexts
from ai_agent.retry_controller import (
    run_all_with_retry,
    print_retry_summary,
    MaxRetriesExceeded,
)
from ai_agent.test_writer import write_and_create_pr
from ai_agent.test_runner import (
    run_targeted,
    run_full_suite,
    get_current_coverage,
)
from ai_agent.reporter import (
    report_success,
    report_failure,
    report_no_changes,
    report_max_retry_breach,
)


# ── Entry Point ────────────────────────────────────────────────────────────────

def main() -> int:
    """
    Runs the full AI Unit Test Generator pipeline.

    Returns:
        Exit code (0=success, 1=failure, 2=config error, 3=no changes)
    """
    pipeline_start = time.monotonic()

    _print_banner()

    # ── Step 1: Validate Config ────────────────────────────────────────────────
    print("\n[Main] ── Step 1: Validate Config ──────────────────────────────────")
    try:
        validate_config()
        print_config()
    except ValueError as e:
        print(f"\n[Main] ✗ Configuration error:\n{e}")
        return 2

    # ── Step 2: Detect Changes ─────────────────────────────────────────────────
    print("\n[Main] ── Step 2: Detect Changes ───────────────────────────────────")
    try:
        changed_files = detect_changes()
    except RuntimeError as e:
        print(f"[Main] ✗ Change detection failed: {e}")
        return 1

    # ── Step 3: Early Exit If No Relevant Changes ──────────────────────────────
    print("\n[Main] ── Step 3: Check Relevant Changes ───────────────────────────")
    if not changed_files:
        print("[Main] No relevant source files changed — skipping AI generation")
        report_no_changes()
        return 3

    print(f"[Main] {len(changed_files)} relevant file(s) detected:")
    for cf in changed_files:
        print(f"  • {cf.filepath}")

    # ── Step 4: Measure Baseline Coverage ─────────────────────────────────────
    print("\n[Main] ── Step 4: Measure Baseline Coverage ────────────────────────")
    baseline_coverage = get_current_coverage()
    print(f"[Main] Baseline coverage: {baseline_coverage:.1f}%")

    # ── Step 5: Build Contexts ─────────────────────────────────────────────────
    print("\n[Main] ── Step 5: Build Contexts ───────────────────────────────────")
    try:
        payloads = build_all_contexts(changed_files)
    except Exception as e:
        print(f"[Main] ✗ Context building failed: {e}")
        traceback.print_exc()
        return 1

    if not payloads:
        print("[Main] No context payloads built — all files may be deleted or unreadable")
        report_no_changes()
        return 3

    print(f"[Main] {len(payloads)} context payload(s) ready")

    # ── Step 6: Generate Tests With Retry ─────────────────────────────────────
    print("\n[Main] ── Step 6: Generate Tests (AI + Retry Loop) ─────────────────")
    max_retry_breaches: list[tuple[str, list[str]]] = []

    try:
        outcomes = run_all_with_retry(payloads)
    except MaxRetriesExceeded as e:
        # Single-file breach — shouldn't reach here since run_all handles it,
        # but catch defensively
        print(f"[Main] ✗ MaxRetriesExceeded: {e.filepath}")
        max_retry_breaches.append((e.filepath, e.last_result.errors))
        outcomes = []
    except Exception as e:
        print(f"[Main] ✗ Generation loop crashed: {e}")
        traceback.print_exc()
        return 1

    print_retry_summary(outcomes)

    # Collect any max-retry breaches recorded inside run_all_with_retry
    for outcome in outcomes:
        if not outcome.succeeded and outcome.attempt_count >= MAX_RETRIES:
            last_errors = (
                outcome.last_attempt.result.errors
                if outcome.last_attempt else ["Unknown error"]
            )
            max_retry_breaches.append((outcome.filepath, last_errors))

    # Notify developer for each breach
    for filepath, errors in max_retry_breaches:
        report_max_retry_breach(
            filepath=filepath,
            attempts=MAX_RETRIES,
            last_errors=errors,
        )

    # If everything failed, exit early
    successful_outcomes = [o for o in outcomes if o.succeeded]
    if not successful_outcomes:
        print("[Main] ✗ No tests were successfully generated — exiting")
        report_failure(
            filepath="(all files)",
            outcomes=outcomes,
            reason=f"All {len(payloads)} file(s) failed generation after {MAX_RETRIES} attempts each",
        )
        return 1

    # ── Step 7: Write Files & Create PR ───────────────────────────────────────
    print("\n[Main] ── Step 7: Write Files & Create PR ───────────────────────────")
    try:
        write_result = write_and_create_pr(outcomes)
    except Exception as e:
        print(f"[Main] ✗ Test writer crashed: {e}")
        traceback.print_exc()
        return 1

    if not write_result.written_files:
        print("[Main] ✗ No files were written — aborting")
        return 1

    print(f"[Main] ✓ Written files:")
    for f in write_result.written_files:
        print(f"  • {f}")

    if write_result.pr_url:
        print(f"[Main] ✓ PR opened: {write_result.pr_url}")

    # ── Step 8: Run Targeted Tests ─────────────────────────────────────────────
    print("\n[Main] ── Step 8: Run Targeted Tests ───────────────────────────────")
    targeted_result = run_targeted(write_result.written_files)

    if not targeted_result.all_passed:
        print(f"[Main] ✗ Targeted test run has failures — reporting")
        pr_number = _extract_pr_number(write_result.pr_url)
        report_failure(
            filepath=", ".join(write_result.written_files),
            outcomes=outcomes,
            run_result=targeted_result,
            pr_number=pr_number,
            reason=(
                f"{targeted_result.failed} test(s) failed, "
                f"{targeted_result.errors} error(s) in generated test files"
            ),
        )
        # Don't exit — still run full suite and report coverage
    else:
        print(f"[Main] ✓ All {targeted_result.passed} targeted test(s) passed")

    # ── Step 9: Run Full Suite ─────────────────────────────────────────────────
    print("\n[Main] ── Step 9: Run Full Suite ───────────────────────────────────")
    full_result = run_full_suite(baseline_coverage=baseline_coverage)

    # ── Step 10: Report Results ────────────────────────────────────────────────
    print("\n[Main] ── Step 10: Report Results ──────────────────────────────────")
    pr_number = _extract_pr_number(write_result.pr_url)

    if full_result.all_passed and targeted_result.all_passed:
        report_success(
            outcomes=outcomes,
            write_result=write_result,
            run_result=full_result,
            pr_number=pr_number,
        )
    else:
        report_failure(
            filepath=", ".join(write_result.written_files),
            outcomes=outcomes,
            run_result=full_result,
            pr_number=pr_number,
            reason=(
                f"Full suite: {full_result.failed} failed, {full_result.errors} errors"
            ),
        )

    # ── Pipeline Complete ──────────────────────────────────────────────────────
    total_time = time.monotonic() - pipeline_start
    _print_final_summary(outcomes, write_result, full_result, total_time)

    # Exit 1 if any tests are still failing after generation
    if not full_result.all_passed or not targeted_result.all_passed:
        return 1

    return 0


# ── Helpers ────────────────────────────────────────────────────────────────────

def _extract_pr_number(pr_url: str) -> int | None:
    """
    Extracts the PR number from a GitHub PR URL.
    e.g. https://github.com/owner/repo/pull/42 → 42
    """
    if not pr_url:
        return None
    try:
        return int(pr_url.rstrip("/").split("/")[-1])
    except (ValueError, IndexError):
        return None


def _print_banner() -> None:
    """Prints a startup banner to the Actions log."""
    print("=" * 65)
    print("  🤖  AI Unit Test Generator")
    print(f"  Run ID : {GITHUB_RUN_ID}")
    print(f"  Time   : {__import__('datetime').datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 65)


def _print_final_summary(
    outcomes:     list,
    write_result,
    full_result,
    total_time:   float,
) -> None:
    """Prints the final pipeline summary to the Actions log."""
    succeeded = sum(1 for o in outcomes if o.succeeded)
    failed    = len(outcomes) - succeeded

    cov_str = ""
    if full_result.coverage:
        delta = full_result.coverage_delta
        sign  = "+" if delta and delta >= 0 else ""
        delta_str = f" ({sign}{delta:.2f}%)" if delta is not None else ""
        cov_str = f"{full_result.coverage.total_coverage:.1f}%{delta_str}"

    print("\n" + "=" * 65)
    print("  Pipeline Complete")
    print(f"  Files generated  : {succeeded}/{len(outcomes)}")
    print(f"  Files failed     : {failed}")
    print(f"  Tests written    : {len(write_result.written_files)}")
    print(f"  Tests passed     : {full_result.passed}")
    print(f"  Tests failed     : {full_result.failed}")
    print(f"  Coverage         : {cov_str or 'N/A'}")
    print(f"  PR               : {write_result.pr_url or 'N/A'}")
    print(f"  Total time       : {total_time:.1f}s")
    print("=" * 65)


# ── Script Entry ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.exit(main())