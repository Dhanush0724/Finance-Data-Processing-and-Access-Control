"""
reporter.py
───────────
Handles all outbound reporting for the AI Unit Test Generator pipeline.

Pipeline position:  Test Runner → [Reporter] → Developer
Output channels:
  1. GitHub PR comment  — coverage delta + pass/fail table + failure diagnostics
  2. Microsoft Teams    — webhook card on failure or max-retry breach
  3. Email (SMTP)       — fallback notification on failure or max-retry breach

All channels are optional — the pipeline continues if any notification fails.
Missing credentials are logged and skipped gracefully.
"""

import os
import sys
import json
import smtplib
import textwrap
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from ai_agent.retry_controller import RetryOutcome
from ai_agent.test_writer import WriteResult
from ai_agent.test_runner import TestRunResult
from ai_agent.config import (
    GITHUB_TOKEN,
    GITHUB_REPOSITORY,
    GITHUB_RUN_ID,
    GITHUB_REF_NAME,
    TEAMS_WEBHOOK_URL,
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASS,
    NOTIFY_EMAIL,
    MAX_RETRIES,
)


# ── Public Entry Points ────────────────────────────────────────────────────────

def report_success(
    outcomes:     list[RetryOutcome],
    write_result: WriteResult,
    run_result:   TestRunResult,
    pr_number:    int | None = None,
) -> None:
    """
    Posts a success report after tests are generated, written, and passing.

    Args:
        outcomes:     RetryOutcome list from retry_controller
        write_result: WriteResult from test_writer
        run_result:   TestRunResult from test_runner (full suite run)
        pr_number:    GitHub PR number to comment on (None = skip PR comment)
    """
    print("\n[Reporter] Posting success report...")

    comment = _build_success_comment(outcomes, write_result, run_result)

    if pr_number:
        _post_pr_comment(pr_number, comment)

    # Only send Teams/email on failure — success is visible in the PR itself
    print("[Reporter] ✓ Success report complete")


def report_failure(
    filepath:    str,
    outcomes:    list[RetryOutcome],
    run_result:  TestRunResult | None = None,
    pr_number:   int | None = None,
    reason:      str = "Max retries exceeded",
) -> None:
    """
    Posts a failure report when the AI cannot generate valid tests
    or when the test suite has failures after generation.

    Args:
        filepath:   The source file that triggered the failure
        outcomes:   RetryOutcome list from retry_controller
        run_result: TestRunResult if tests were run (None if generation failed)
        pr_number:  GitHub PR number to comment on (None = skip PR comment)
        reason:     Human-readable reason for the failure
    """
    print(f"\n[Reporter] Posting failure report for: {filepath}")

    comment = _build_failure_comment(filepath, outcomes, run_result, reason)

    if pr_number:
        _post_pr_comment(pr_number, comment)

    _send_teams_notification(
        title=f"❌ AI Test Generator Failed — {filepath}",
        message=reason,
        filepath=filepath,
        is_failure=True,
    )

    _send_email_notification(
        subject=f"[AI Test Generator] Failed: {filepath} — {reason}",
        body=comment,
    )

    print("[Reporter] ✓ Failure report dispatched")


def report_no_changes() -> None:
    """Called when no relevant files changed — logs only, no notifications."""
    print("[Reporter] No relevant changes detected — pipeline skipped. No notifications sent.")


def report_max_retry_breach(
    filepath:  str,
    attempts:  int,
    last_errors: list[str],
    pr_number: int | None = None,
) -> None:
    """
    Escalates to developer when the AI hits MAX_RETRIES without producing
    valid test code. This requires human intervention.

    Args:
        filepath:    The source file that could not be tested
        attempts:    Number of attempts made
        last_errors: Validation errors from the final attempt
        pr_number:   GitHub PR number to comment on (None = skip)
    """
    print(f"\n[Reporter] ⚠ MAX RETRY BREACH: {filepath} ({attempts}/{MAX_RETRIES} attempts)")

    errors_formatted = "\n".join(f"- {e}" for e in last_errors)
    reason = (
        f"AI failed to generate valid tests after {attempts} attempts.\n"
        f"Last validation errors:\n{errors_formatted}"
    )

    comment = _build_max_retry_comment(filepath, attempts, last_errors)

    if pr_number:
        _post_pr_comment(pr_number, comment)

    _send_teams_notification(
        title=f"🚨 AI Test Generator — Human Review Required",
        message=(
            f"Could not auto-generate tests for `{filepath}` "
            f"after {attempts} attempts. Manual tests needed."
        ),
        filepath=filepath,
        is_failure=True,
    )

    _send_email_notification(
        subject=f"[AI Test Generator] ACTION REQUIRED: {filepath}",
        body=comment,
    )


# ── Comment Builders ───────────────────────────────────────────────────────────

def _build_success_comment(
    outcomes:     list[RetryOutcome],
    write_result: WriteResult,
    run_result:   TestRunResult,
) -> str:
    """Builds the GitHub PR comment body for a successful pipeline run."""

    succeeded = [o for o in outcomes if o.succeeded]
    failed    = [o for o in outcomes if not o.succeeded]

    # Coverage section
    cov_section = ""
    if run_result.coverage:
        cov   = run_result.coverage
        delta = run_result.coverage_delta
        delta_str = ""
        if delta is not None:
            sign      = "+" if delta >= 0 else ""
            emoji     = "📈" if delta >= 0 else "📉"
            delta_str = f" {emoji} `{sign}{delta:.2f}%`"

        cov_section = f"""
### 📊 Coverage Report

| Metric | Value |
|---|---|
| Total Coverage | `{cov.total_coverage:.1f}%`{delta_str} |
| Lines Covered | `{cov.covered_lines}` |
| Lines Missing | `{cov.missing_lines}` |
"""

    # Test results section
    test_section = f"""
### 🧪 Test Run Results

| Result | Count |
|---|---|
| ✅ Passed | `{run_result.passed}` |
| ❌ Failed | `{run_result.failed}` |
| ⚠️ Errors | `{run_result.errors}` |
| ⏭️ Skipped | `{run_result.skipped}` |
| ⏱️ Duration | `{run_result.duration_s:.2f}s` |
"""

    # Generated files table
    file_rows = "\n".join(
        f"| `{f}` | {o.attempt_count} attempt(s) | ✅ |"
        for o, f in zip(succeeded, write_result.written_files)
    )

    failed_rows = ""
    if failed:
        failed_rows = "\n\n### ⚠️ Files Requiring Manual Tests\n\n"
        failed_rows += "| Source File | Reason |\n|---|---|\n"
        failed_rows += "\n".join(
            f"| `{o.filepath}` | Failed after {MAX_RETRIES} attempts |"
            for o in failed
        )

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return f"""## 🤖 AI Unit Test Generator — Run `{GITHUB_RUN_ID}`

> Generated on `{GITHUB_REF_NAME}` at {timestamp}
{cov_section}{test_section}
### 📁 Generated Files

| Test File | Attempts | Status |
|---|---|---|
{file_rows}
{failed_rows}

---
> ⚠️ **Always review AI-generated tests before merging.**
> Tests are on a draft PR — resolve failures, verify logic, then mark ready for review.
"""


def _build_failure_comment(
    filepath:   str,
    outcomes:   list[RetryOutcome],
    run_result: TestRunResult | None,
    reason:     str,
) -> str:
    """Builds the GitHub PR comment body for a failed pipeline run."""

    diagnostics_section = ""
    if run_result and run_result.diagnostics:
        truncated = textwrap.shorten(run_result.diagnostics, width=2000, placeholder="\n...(truncated)")
        diagnostics_section = f"""
### 🔍 Failure Diagnostics

```
{truncated}
```
"""

    attempt_rows = ""
    for outcome in outcomes:
        if not outcome.succeeded and outcome.last_attempt:
            errors = "; ".join(outcome.last_attempt.result.errors[:3])
            attempt_rows += f"| `{outcome.filepath}` | {outcome.attempt_count}/{MAX_RETRIES} | {errors} |\n"

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return f"""## 🤖 AI Unit Test Generator — ❌ Pipeline Failure

> Run `{GITHUB_RUN_ID}` on `{GITHUB_REF_NAME}` at {timestamp}

**Reason:** {reason}

### 📁 Failed Files

| Source File | Attempts | Last Error |
|---|---|---|
{attempt_rows}
{diagnostics_section}

---
> 🔧 **Action required:** Manual tests may be needed for the files above.
> Check the [Actions log](https://github.com/{GITHUB_REPOSITORY}/actions/runs/{GITHUB_RUN_ID}) for full details.
"""


def _build_max_retry_comment(
    filepath:    str,
    attempts:    int,
    last_errors: list[str],
) -> str:
    """Builds the escalation comment for a max-retry breach."""

    errors_md = "\n".join(f"- `{e}`" for e in last_errors)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return f"""## 🤖 AI Unit Test Generator — 🚨 Human Review Required

> Run `{GITHUB_RUN_ID}` on `{GITHUB_REF_NAME}` at {timestamp}

The AI agent could not generate valid tests for **`{filepath}`**
after **{attempts}/{MAX_RETRIES}** attempts.

### Last Validation Errors

{errors_md}

### What To Do

1. Review the source file: `{filepath}`
2. Write tests manually in the corresponding test file
3. Or simplify the function signatures to make them easier to mock
4. Check the [Actions log](https://github.com/{GITHUB_REPOSITORY}/actions/runs/{GITHUB_RUN_ID}) for full AI output

---
> This notification was sent because the retry cap was hit.
> No test file was written for this source file.
"""


# ── GitHub PR Comment ──────────────────────────────────────────────────────────

def _post_pr_comment(pr_number: int, body: str) -> bool:
    """
    Posts a comment on the specified GitHub Pull Request.

    Returns True on success, False on failure.
    """
    if not GITHUB_TOKEN:
        print("[Reporter] GITHUB_TOKEN not set — skipping PR comment")
        return False

    if not GITHUB_REPOSITORY:
        print("[Reporter] GITHUB_REPOSITORY not set — skipping PR comment")
        return False

    url = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/issues/{pr_number}/comments"
    headers = {
        "Authorization":        f"Bearer {GITHUB_TOKEN}",
        "Accept":               "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json={"body": body},
            timeout=30,
        )
    except requests.RequestException as e:
        print(f"[Reporter] ✗ PR comment failed: {e}")
        return False

    if response.status_code == 201:
        comment_url = response.json().get("html_url", "")
        print(f"[Reporter] ✓ PR comment posted: {comment_url}")
        return True
    else:
        print(f"[Reporter] ✗ PR comment failed ({response.status_code}): {response.text[:200]}")
        return False


# ── Microsoft Teams ────────────────────────────────────────────────────────────

def _send_teams_notification(
    title:      str,
    message:    str,
    filepath:   str = "",
    is_failure: bool = False,
) -> bool:
    """
    Sends an Adaptive Card to a Microsoft Teams channel via incoming webhook.

    Returns True on success, False if webhook not configured or call fails.
    """
    if not TEAMS_WEBHOOK_URL:
        print("[Reporter] TEAMS_WEBHOOK_URL not set — skipping Teams notification")
        return False

    color   = "FF0000" if is_failure else "00AA00"
    actions_url = f"https://github.com/{GITHUB_REPOSITORY}/actions/runs/{GITHUB_RUN_ID}"

    payload = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type":    "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {
                            "type":   "TextBlock",
                            "text":   title,
                            "weight": "Bolder",
                            "size":   "Medium",
                            "color":  "Attention" if is_failure else "Good",
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {"title": "Repository", "value": GITHUB_REPOSITORY},
                                {"title": "Branch",     "value": GITHUB_REF_NAME},
                                {"title": "Run ID",     "value": GITHUB_RUN_ID},
                                {"title": "File",       "value": filepath or "N/A"},
                                {
                                    "title": "Time",
                                    "value": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                                },
                            ],
                        },
                        {
                            "type": "TextBlock",
                            "text": textwrap.shorten(message, width=500, placeholder="..."),
                            "wrap": True,
                        },
                    ],
                    "actions": [
                        {
                            "type":  "Action.OpenUrl",
                            "title": "View Actions Run",
                            "url":   actions_url,
                        }
                    ],
                },
            }
        ],
    }

    try:
        response = requests.post(
            TEAMS_WEBHOOK_URL,
            json=payload,
            timeout=15,
        )
        if response.status_code in (200, 202):
            print("[Reporter] ✓ Teams notification sent")
            return True
        else:
            print(f"[Reporter] ✗ Teams notification failed ({response.status_code}): {response.text[:200]}")
            return False
    except requests.RequestException as e:
        print(f"[Reporter] ✗ Teams notification error: {e}")
        return False


# ── Email (SMTP) ───────────────────────────────────────────────────────────────

def _send_email_notification(subject: str, body: str) -> bool:
    """
    Sends an email notification via SMTP on failure or max-retry breach.

    Returns True on success, False if SMTP not configured or send fails.
    """
    if not all([SMTP_HOST, SMTP_USER, SMTP_PASS, NOTIFY_EMAIL]):
        missing = [
            k for k, v in {
                "SMTP_HOST":    SMTP_HOST,
                "SMTP_USER":    SMTP_USER,
                "SMTP_PASS":    SMTP_PASS,
                "NOTIFY_EMAIL": NOTIFY_EMAIL,
            }.items() if not v
        ]
        print(f"[Reporter] SMTP not fully configured (missing: {missing}) — skipping email")
        return False

    print(f"[Reporter] Sending email to: {NOTIFY_EMAIL}")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SMTP_USER
    msg["To"]      = NOTIFY_EMAIL

    # Plain text version
    plain = textwrap.fill(body.replace("#", "").replace("`", ""), width=80)
    msg.attach(MIMEText(plain, "plain"))

    # HTML version — convert markdown-ish body to basic HTML
    html_body = _markdown_to_basic_html(body)
    html = f"""
    <html><body style="font-family: monospace; padding: 20px;">
    <h2>AI Unit Test Generator</h2>
    {html_body}
    <hr>
    <p><small>Run ID: {GITHUB_RUN_ID} | Repo: {GITHUB_REPOSITORY}</small></p>
    </body></html>
    """
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, NOTIFY_EMAIL, msg.as_string())
        print(f"[Reporter] ✓ Email sent to: {NOTIFY_EMAIL}")
        return True
    except smtplib.SMTPAuthenticationError:
        print("[Reporter] ✗ SMTP authentication failed — check SMTP_USER and SMTP_PASS")
        return False
    except smtplib.SMTPException as e:
        print(f"[Reporter] ✗ SMTP error: {e}")
        return False
    except OSError as e:
        print(f"[Reporter] ✗ Email connection error: {e}")
        return False


# ── Helpers ────────────────────────────────────────────────────────────────────

def _markdown_to_basic_html(text: str) -> str:
    """
    Converts a simple markdown string to basic HTML for the email body.
    Handles headers, bold, code blocks, and line breaks only.
    """
    import re
    lines  = text.splitlines()
    output = []

    in_code = False
    for line in lines:
        if line.startswith("```"):
            if in_code:
                output.append("</pre>")
                in_code = False
            else:
                output.append("<pre style='background:#f4f4f4;padding:8px;'>")
                in_code = True
            continue

        if in_code:
            output.append(line)
            continue

        # Headers
        if line.startswith("### "):
            output.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("## "):
            output.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("# "):
            output.append(f"<h1>{line[2:]}</h1>")
        # Bold
        elif line.startswith("**") and line.endswith("**"):
            output.append(f"<strong>{line[2:-2]}</strong><br>")
        # Horizontal rule
        elif line.startswith("---"):
            output.append("<hr>")
        # Empty line
        elif not line.strip():
            output.append("<br>")
        else:
            # Inline code
            line = re.sub(r"`([^`]+)`", r"<code>\1</code>", line)
            output.append(f"{line}<br>")

    if in_code:
        output.append("</pre>")

    return "\n".join(output)