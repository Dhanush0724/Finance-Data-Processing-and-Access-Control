# """
# retry_controller.py
# ───────────────────
# Manages the AI generation → validation → retry loop for each changed file.

# Pipeline position:  AI Agent → Validator → [Retry Controller] → Test Writer
# Input:              ContextPayload + filepath to generate tests for
# Output:             Final validated test code string, or raises MaxRetriesExceeded

# How it works:
# 1. Calls ai_agent.analyse_and_generate() to get test code
# 2. Passes the result to validator.validate()
# 3. If validation passes → returns the code to the test writer
# 4. If validation fails → appends diagnostics to next AI call (up to MAX_RETRIES)
# 5. If MAX_RETRIES is hit → raises MaxRetriesExceeded → reporter notifies developer

# The diagnostics from each failed attempt are accumulated and passed back
# to the AI agent so it has full context of what went wrong on every prior attempt.
# """

# import os
# import sys
# import time
# from dataclasses import dataclass, field

# sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
# from ai_agent.ai_agent import analyse_and_generate
# from ai_agent.validator import validate, ValidationResult
# from ai_agent.context_builder import ContextPayload
# from ai_agent.config import MAX_RETRIES


# # ── Exceptions ─────────────────────────────────────────────────────────────────

# class MaxRetriesExceeded(Exception):
#     """
#     Raised when the AI agent fails to produce valid test code
#     within the maximum number of allowed attempts.

#     Caught by main.py → triggers developer notification via reporter.py
#     """
#     def __init__(self, filepath: str, attempts: int, last_result: ValidationResult):
#         self.filepath    = filepath
#         self.attempts    = attempts
#         self.last_result = last_result
#         super().__init__(
#             f"Max retries ({attempts}) exceeded for {filepath}. "
#             f"Last errors: {last_result.errors}"
#         )


# # ── Data Model ─────────────────────────────────────────────────────────────────

# @dataclass
# class AttemptRecord:
#     """
#     Records the outcome of a single generation attempt.

#     Attributes:
#         attempt:    Attempt number (1-based)
#         code:       The raw code the AI generated
#         result:     The ValidationResult for this attempt
#         duration_s: How long the AI call + validation took in seconds
#     """
#     attempt:    int
#     code:       str
#     result:     ValidationResult
#     duration_s: float

#     def __repr__(self) -> str:
#         status = "PASSED" if self.result.passed else "FAILED"
#         return f"AttemptRecord(attempt={self.attempt}, {status}, {self.duration_s:.1f}s)"


# @dataclass
# class RetryOutcome:
#     """
#     The final outcome of the full retry loop for one file.

#     Attributes:
#         filepath:   The source file being tested
#         succeeded:  True if a valid test was generated within MAX_RETRIES
#         code:       The final validated code (empty string if failed)
#         attempts:   List of all AttemptRecord objects (one per try)
#         total_time: Total wall-clock time for all attempts
#     """
#     filepath:   str
#     succeeded:  bool
#     code:       str
#     attempts:   list[AttemptRecord] = field(default_factory=list)
#     total_time: float = 0.0

#     @property
#     def attempt_count(self) -> int:
#         return len(self.attempts)

#     @property
#     def last_attempt(self) -> AttemptRecord | None:
#         return self.attempts[-1] if self.attempts else None

#     def __repr__(self) -> str:
#         status = "SUCCESS" if self.succeeded else "FAILED"
#         return (
#             f"RetryOutcome({self.filepath!r}, {status}, "
#             f"attempts={self.attempt_count}/{MAX_RETRIES}, "
#             f"total={self.total_time:.1f}s)"
#         )


# # ── Public Entry Point ─────────────────────────────────────────────────────────

# def run_with_retry(payload: ContextPayload) -> RetryOutcome:
#     """
#     Runs the full AI generation + validation loop for one file.

#     Attempts up to MAX_RETRIES times, feeding diagnostics back into
#     the AI agent on each failed attempt.

#     Args:
#         payload: ContextPayload from context_builder.build_context()

#     Returns:
#         RetryOutcome with succeeded=True and valid code, or succeeded=False
#         with the full attempt history for the reporter.

#     Raises:
#         MaxRetriesExceeded: If all attempts fail — caught by main.py
#     """
#     filepath   = payload.filepath
#     loop_start = time.monotonic()
#     attempts:  list[AttemptRecord] = []
#     diagnostics = ""  # Accumulated failure diagnostics from prior attempts

#     print(f"\n[RetryController] Starting generation loop for: {filepath}")
#     print(f"[RetryController] Max attempts: {MAX_RETRIES}")

#     for attempt_num in range(1, MAX_RETRIES + 1):
#         print(f"\n[RetryController] ── Attempt {attempt_num}/{MAX_RETRIES} ──────────────────")

#         attempt_start = time.monotonic()

#         # ── Step 1: Call AI Agent ──────────────────────────────────────────────
#         try:
#             code = analyse_and_generate(
#                 filepath=filepath,
#                 context=payload.to_dict(),
#                 diagnostics=diagnostics,
#                 attempt=attempt_num,
#             )
#         except Exception as e:
#             # AI call itself failed (network, timeout, auth) — treat as failed attempt
#             error_msg = f"AI agent call failed: {type(e).__name__}: {e}"
#             print(f"[RetryController] ✗ {error_msg}")

#             fake_result = ValidationResult(
#                 passed=False,
#                 errors=[error_msg],
#                 diagnostics=error_msg,
#             )
#             record = AttemptRecord(
#                 attempt=attempt_num,
#                 code="",
#                 result=fake_result,
#                 duration_s=time.monotonic() - attempt_start,
#             )
#             attempts.append(record)
#             diagnostics = _build_accumulated_diagnostics(attempts)
#             continue

#         # ── Step 2: Validate ───────────────────────────────────────────────────
#         result = validate(code, filepath)
#         duration = time.monotonic() - attempt_start

#         record = AttemptRecord(
#             attempt=attempt_num,
#             code=code,
#             result=result,
#             duration_s=duration,
#         )
#         attempts.append(record)

#         # ── Step 3: Check outcome ──────────────────────────────────────────────
#         if result.passed:
#             total_time = time.monotonic() - loop_start
#             print(
#                 f"\n[RetryController] ✓ Validation passed on attempt {attempt_num}. "
#                 f"Total time: {total_time:.1f}s"
#             )
#             return RetryOutcome(
#                 filepath=filepath,
#                 succeeded=True,
#                 code=code,
#                 attempts=attempts,
#                 total_time=total_time,
#             )

#         # ── Step 4: Prepare retry ──────────────────────────────────────────────
#         print(f"[RetryController] ✗ Attempt {attempt_num} failed:")
#         for err in result.errors:
#             print(f"  Error: {err}")

#         if attempt_num < MAX_RETRIES:
#             diagnostics = _build_accumulated_diagnostics(attempts)
#             wait = _backoff_seconds(attempt_num)
#             if wait > 0:
#                 print(f"[RetryController] Waiting {wait}s before retry...")
#                 time.sleep(wait)
#         else:
#             print(f"[RetryController] ✗ All {MAX_RETRIES} attempts exhausted for: {filepath}")

#     # ── All attempts failed ────────────────────────────────────────────────────
#     total_time = time.monotonic() - loop_start
#     outcome = RetryOutcome(
#         filepath=filepath,
#         succeeded=False,
#         code="",
#         attempts=attempts,
#         total_time=total_time,
#     )

#     raise MaxRetriesExceeded(
#         filepath=filepath,
#         attempts=MAX_RETRIES,
#         last_result=attempts[-1].result if attempts else ValidationResult(
#             passed=False,
#             errors=["No attempts completed"],
#         ),
#     )


# def run_all_with_retry(payloads: list[ContextPayload]) -> list[RetryOutcome]:
#     """
#     Runs the retry loop for a list of context payloads.
#     Collects outcomes for all files — failures do not stop processing of others.

#     Args:
#         payloads: List of ContextPayload objects from context_builder

#     Returns:
#         List of RetryOutcome objects, one per file (succeeded or failed)
#     """
#     outcomes: list[RetryOutcome] = []

#     print(f"\n[RetryController] Processing {len(payloads)} file(s)")

#     for i, payload in enumerate(payloads, 1):
#         print(f"\n[RetryController] File {i}/{len(payloads)}: {payload.filepath}")
#         try:
#             outcome = run_with_retry(payload)
#             outcomes.append(outcome)
#         except MaxRetriesExceeded as e:
#             print(f"[RetryController] ✗ MaxRetriesExceeded for: {e.filepath}")
#             # Record the failure as an outcome so the reporter can handle it
#             failed_outcome = RetryOutcome(
#                 filepath=e.filepath,
#                 succeeded=False,
#                 code="",
#                 attempts=[],
#                 total_time=0.0,
#             )
#             outcomes.append(failed_outcome)

#     succeeded = sum(1 for o in outcomes if o.succeeded)
#     failed    = len(outcomes) - succeeded
#     print(f"\n[RetryController] Done — {succeeded} succeeded, {failed} failed")

#     return outcomes


# # ── Diagnostics Builder ────────────────────────────────────────────────────────

# def _build_accumulated_diagnostics(attempts: list[AttemptRecord]) -> str:
#     """
#     Builds a consolidated diagnostics string from all failed attempts so far.
#     This is passed back to the AI agent on the next attempt so it has
#     the full history of what went wrong.

#     Format is designed to be clear and actionable for the AI model.
#     """
#     lines = ["The following attempts have failed. Fix ALL issues listed below:\n"]

#     for record in attempts:
#         if record.result.passed:
#             continue

#         lines.append(f"── Attempt {record.attempt} Errors ──")
#         for err in record.result.errors:
#             lines.append(f"  ERROR: {err}")

#         if record.result.warnings:
#             for warn in record.result.warnings:
#                 lines.append(f"  WARNING: {warn}")

#         lines.append("")

#     lines.extend([
#         "── Reminder: Rules You Must Follow ──",
#         "- Output ONLY a single ```python ... ``` code block — nothing else",
#         "- import pytest at the top",
#         "- Mock ALL external dependencies: DB sessions, HTTP calls, auth tokens",
#         "- Use Decimal for all financial amounts, never float",
#         "- Every test function must contain at least one assert or pytest.raises()",
#         "- Name tests: test_<function>_<scenario>_<expected_result>",
#         "- No real credentials, no real DB URLs, no real HTTP calls",
#     ])

#     return "\n".join(lines)


# # ── Backoff ────────────────────────────────────────────────────────────────────

# def _backoff_seconds(attempt: int) -> float:
#     """
#     Returns the number of seconds to wait before the next retry.
#     Uses a short linear backoff to avoid hammering the API.

#     attempt 1 → 0s  (first retry is immediate)
#     attempt 2 → 2s
#     attempt 3 → 4s
#     """
#     if attempt <= 1:
#         return 0
#     return float((attempt - 1) * 2)


# # ── Summary Printer ────────────────────────────────────────────────────────────

# def print_retry_summary(outcomes: list[RetryOutcome]) -> None:
#     """
#     Prints a clean summary table of all retry outcomes.
#     Called by main.py after all files are processed.
#     """
#     print("\n[RetryController] ── Generation Summary ──────────────────────────────")
#     print(f"  {'File':<50} {'Status':<10} {'Attempts':<10} {'Time'}")
#     print(f"  {'─'*50} {'─'*10} {'─'*10} {'─'*8}")

#     for outcome in outcomes:
#         status   = "✓ PASS" if outcome.succeeded else "✗ FAIL"
#         filename = outcome.filepath[-48:] if len(outcome.filepath) > 48 else outcome.filepath
#         print(
#             f"  {filename:<50} {status:<10} "
#             f"{outcome.attempt_count}/{MAX_RETRIES:<8} "
#             f"{outcome.total_time:.1f}s"
#         )

#     total     = len(outcomes)
#     succeeded = sum(1 for o in outcomes if o.succeeded)
#     print(f"\n  Total: {succeeded}/{total} files generated successfully")
#     print("[RetryController] ──────────────────────────────────────────────────────\n")


"""
retry_controller.py
───────────────────
Manages the AI generation → validation → retry loop for each changed file.

Pipeline position:  AI Agent → Validator → [Retry Controller] → Test Writer
Input:              ContextPayload + filepath to generate tests for
Output:             Final validated test code string, or raises MaxRetriesExceeded

How it works:
1. Calls ai_agent.analyse_and_generate() to get test code
2. Passes the result to validator.validate()
3. If validation passes → returns the code to the test writer
4. If validation fails → appends diagnostics to next AI call (up to MAX_RETRIES)
5. If MAX_RETRIES is hit → raises MaxRetriesExceeded → reporter notifies developer

The diagnostics from each failed attempt are accumulated and passed back
to the AI agent so it has full context of what went wrong on every prior attempt.
"""

import os
import sys
import time
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from ai_agent.ai_agent import analyse_and_generate
from ai_agent.validator import validate, ValidationResult
from ai_agent.context_builder import ContextPayload
from ai_agent.config import MAX_RETRIES


# ── Exceptions ─────────────────────────────────────────────────────────────────

class MaxRetriesExceeded(Exception):
    """
    Raised when the AI agent fails to produce valid test code
    within the maximum number of allowed attempts.

    Caught by main.py → triggers developer notification via reporter.py
    """
    def __init__(self, filepath: str, attempts: int, last_result: ValidationResult):
        self.filepath    = filepath
        self.attempts    = attempts
        self.last_result = last_result
        super().__init__(
            f"Max retries ({attempts}) exceeded for {filepath}. "
            f"Last errors: {last_result.errors}"
        )


# ── Data Model ─────────────────────────────────────────────────────────────────

@dataclass
class AttemptRecord:
    """
    Records the outcome of a single generation attempt.

    Attributes:
        attempt:    Attempt number (1-based)
        code:       The raw code the AI generated
        result:     The ValidationResult for this attempt
        duration_s: How long the AI call + validation took in seconds
    """
    attempt:    int
    code:       str
    result:     ValidationResult
    duration_s: float

    def __repr__(self) -> str:
        status = "PASSED" if self.result.passed else "FAILED"
        return f"AttemptRecord(attempt={self.attempt}, {status}, {self.duration_s:.1f}s)"


@dataclass
class RetryOutcome:
    """
    The final outcome of the full retry loop for one file.

    Attributes:
        filepath:   The source file being tested
        succeeded:  True if a valid test was generated within MAX_RETRIES
        code:       The final validated code (empty string if failed)
        attempts:   List of all AttemptRecord objects (one per try)
        total_time: Total wall-clock time for all attempts
    """
    filepath:   str
    succeeded:  bool
    code:       str
    attempts:   list[AttemptRecord] = field(default_factory=list)
    total_time: float = 0.0

    @property
    def attempt_count(self) -> int:
        return len(self.attempts)

    @property
    def last_attempt(self) -> AttemptRecord | None:
        return self.attempts[-1] if self.attempts else None

    def __repr__(self) -> str:
        status = "SUCCESS" if self.succeeded else "FAILED"
        return (
            f"RetryOutcome({self.filepath!r}, {status}, "
            f"attempts={self.attempt_count}/{MAX_RETRIES}, "
            f"total={self.total_time:.1f}s)"
        )


# ── Public Entry Point ─────────────────────────────────────────────────────────

def run_with_retry(payload: ContextPayload) -> RetryOutcome:
    """
    Runs the full AI generation + validation loop for one file.

    Attempts up to MAX_RETRIES times, feeding diagnostics back into
    the AI agent on each failed attempt.

    Args:
        payload: ContextPayload from context_builder.build_context()

    Returns:
        RetryOutcome with succeeded=True and valid code, or succeeded=False
        with the full attempt history for the reporter.

    Raises:
        MaxRetriesExceeded: If all attempts fail — caught by main.py
    """
    filepath   = payload.filepath
    loop_start = time.monotonic()
    attempts:  list[AttemptRecord] = []
    diagnostics = ""  # Accumulated failure diagnostics from prior attempts

    print(f"\n[RetryController] Starting generation loop for: {filepath}")
    print(f"[RetryController] Max attempts: {MAX_RETRIES}")

    for attempt_num in range(1, MAX_RETRIES + 1):
        print(f"\n[RetryController] ── Attempt {attempt_num}/{MAX_RETRIES} ──────────────────")

        attempt_start = time.monotonic()

        # ── Step 1: Call AI Agent ──────────────────────────────────────────────
        try:
            code = analyse_and_generate(
                filepath=filepath,
                context=payload.to_dict(),
                diagnostics=diagnostics,
                attempt=attempt_num,
            )
        except Exception as e:
            # AI call itself failed (network, timeout, auth) — treat as failed attempt
            error_msg = f"AI agent call failed: {type(e).__name__}: {e}"
            print(f"[RetryController] ✗ {error_msg}")

            fake_result = ValidationResult(
                passed=False,
                errors=[error_msg],
                diagnostics=error_msg,
            )
            record = AttemptRecord(
                attempt=attempt_num,
                code="",
                result=fake_result,
                duration_s=time.monotonic() - attempt_start,
            )
            attempts.append(record)
            diagnostics = _build_accumulated_diagnostics(attempts)
            continue

        # ── Step 2: Validate ───────────────────────────────────────────────────
        result = validate(code, filepath)
        duration = time.monotonic() - attempt_start

        record = AttemptRecord(
            attempt=attempt_num,
            code=code,
            result=result,
            duration_s=duration,
        )
        attempts.append(record)

        # ── Step 3: Check outcome ──────────────────────────────────────────────
        if result.passed:
            total_time = time.monotonic() - loop_start
            print(
                f"\n[RetryController] ✓ Validation passed on attempt {attempt_num}. "
                f"Total time: {total_time:.1f}s"
            )
            return RetryOutcome(
                filepath=filepath,
                succeeded=True,
                code=code,
                attempts=attempts,
                total_time=total_time,
            )

        # ── Step 4: Prepare retry ──────────────────────────────────────────────
        print(f"[RetryController] ✗ Attempt {attempt_num} failed:")
        for err in result.errors:
            print(f"  Error: {err}")

        if attempt_num < MAX_RETRIES:
            diagnostics = _build_accumulated_diagnostics(attempts)
            wait = _backoff_seconds(attempt_num)
            if wait > 0:
                print(f"[RetryController] Waiting {wait}s before retry...")
                time.sleep(wait)
        else:
            print(f"[RetryController] ✗ All {MAX_RETRIES} attempts exhausted for: {filepath}")

    # ── All attempts failed ────────────────────────────────────────────────────
    total_time = time.monotonic() - loop_start
    outcome = RetryOutcome(
        filepath=filepath,
        succeeded=False,
        code="",
        attempts=attempts,
        total_time=total_time,
    )

    raise MaxRetriesExceeded(
        filepath=filepath,
        attempts=MAX_RETRIES,
        last_result=attempts[-1].result if attempts else ValidationResult(
            passed=False,
            errors=["No attempts completed"],
        ),
    )


def run_all_with_retry(payloads: list[ContextPayload]) -> list[RetryOutcome]:
    """
    Runs the retry loop for a list of context payloads.
    Collects outcomes for all files — failures do not stop processing of others.

    Args:
        payloads: List of ContextPayload objects from context_builder

    Returns:
        List of RetryOutcome objects, one per file (succeeded or failed)
    """
    outcomes: list[RetryOutcome] = []

    print(f"\n[RetryController] Processing {len(payloads)} file(s)")

    for i, payload in enumerate(payloads, 1):
        print(f"\n[RetryController] File {i}/{len(payloads)}: {payload.filepath}")
        if i > 1:
            print("[RetryController] Waiting 30s before next file (rate limit cooldown)...")
            time.sleep(30)
        try:
            outcome = run_with_retry(payload)
            outcomes.append(outcome)
        except MaxRetriesExceeded as e:
            print(f"[RetryController] ✗ MaxRetriesExceeded for: {e.filepath}")
            # Record the failure as an outcome so the reporter can handle it
            failed_outcome = RetryOutcome(
                filepath=e.filepath,
                succeeded=False,
                code="",
                attempts=[],
                total_time=0.0,
            )
            outcomes.append(failed_outcome)

    succeeded = sum(1 for o in outcomes if o.succeeded)
    failed    = len(outcomes) - succeeded
    print(f"\n[RetryController] Done — {succeeded} succeeded, {failed} failed")

    return outcomes


# ── Diagnostics Builder ────────────────────────────────────────────────────────

def _build_accumulated_diagnostics(attempts: list[AttemptRecord]) -> str:
    """
    Builds a consolidated diagnostics string from all failed attempts so far.
    This is passed back to the AI agent on the next attempt so it has
    the full history of what went wrong.

    Format is designed to be clear and actionable for the AI model.
    """
    lines = ["The following attempts have failed. Fix ALL issues listed below:\n"]

    for record in attempts:
        if record.result.passed:
            continue

        lines.append(f"── Attempt {record.attempt} Errors ──")
        for err in record.result.errors:
            lines.append(f"  ERROR: {err}")

        if record.result.warnings:
            for warn in record.result.warnings:
                lines.append(f"  WARNING: {warn}")

        lines.append("")

    lines.extend([
        "── Reminder: Rules You Must Follow ──",
        "- Output ONLY a single ```python ... ``` code block — nothing else",
        "- import pytest at the top",
        "- Mock ALL external dependencies: DB sessions, HTTP calls, auth tokens",
        "- Use Decimal for all financial amounts, never float",
        "- Every test function must contain at least one assert or pytest.raises()",
        "- Name tests: test_<function>_<scenario>_<expected_result>",
        "- No real credentials, no real DB URLs, no real HTTP calls",
    ])

    return "\n".join(lines)


# ── Backoff ────────────────────────────────────────────────────────────────────

def _backoff_seconds(attempt: int) -> float:
    """
    Returns the number of seconds to wait before the next retry.
    Uses a longer backoff to respect free-tier API rate limits.

    attempt 1 → 20s
    attempt 2 → 40s
    attempt 3 → 60s
    """
    return float(attempt * 20)


# ── Summary Printer ────────────────────────────────────────────────────────────

def print_retry_summary(outcomes: list[RetryOutcome]) -> None:
    """
    Prints a clean summary table of all retry outcomes.
    Called by main.py after all files are processed.
    """
    print("\n[RetryController] ── Generation Summary ──────────────────────────────")
    print(f"  {'File':<50} {'Status':<10} {'Attempts':<10} {'Time'}")
    print(f"  {'─'*50} {'─'*10} {'─'*10} {'─'*8}")

    for outcome in outcomes:
        status   = "✓ PASS" if outcome.succeeded else "✗ FAIL"
        filename = outcome.filepath[-48:] if len(outcome.filepath) > 48 else outcome.filepath
        print(
            f"  {filename:<50} {status:<10} "
            f"{outcome.attempt_count}/{MAX_RETRIES:<8} "
            f"{outcome.total_time:.1f}s"
        )

    total     = len(outcomes)
    succeeded = sum(1 for o in outcomes if o.succeeded)
    print(f"\n  Total: {succeeded}/{total} files generated successfully")
    print("[RetryController] ──────────────────────────────────────────────────────\n")