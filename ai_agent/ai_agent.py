"""
ai_agent.py
───────────
Core AI reasoning unit — powered exclusively by OpenRouter.

OpenRouter provides a unified OpenAI-compatible API that routes to any
major model: GPT-4o, Gemini, DeepSeek, Llama, Mistral, Claude, and more.
Switch the model anytime via the OPENROUTER_MODEL environment variable
without touching any code.

Docs: https://openrouter.ai/docs
Models: https://openrouter.ai/models
"""

import os
import re
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from ai_agent.config import (
    OPENROUTER_MODEL,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OPENROUTER_APP_URL,
    OPENROUTER_APP_NAME,
    OPENROUTER_TEMPERATURE,
)

# ── System Prompt ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a senior Python test engineer specialising in financial backend systems.

Your task:
1. Read the provided source code and git diff carefully.
2. Identify ALL functions, methods, and classes that need test coverage.
3. Identify any EXISTING tests that are now outdated due to the diff.
4. Generate a COMPLETE, runnable pytest test file.

Rules you must follow:
- Output ONLY a single ```python ... ``` code block — nothing else before or after.
- Include ALL necessary imports at the top of the file.
- Use pytest fixtures (conftest or inline) for shared setup.
- Use unittest.mock / pytest-mock to mock: DB sessions, external APIs, auth tokens.
- Cover: happy path, edge cases, error/exception paths, and boundary values.
- For finance code: always test: zero values, negative amounts, currency precision, permission checks.
- Name tests descriptively: test_<function>_<scenario>_<expected_result>
- Never test private methods directly — test through public interfaces.
- Do NOT use any real credentials, real DB connections, or real HTTP calls.
- If existing tests are provided and still valid, keep them and ADD new ones."""


# ── Public Entry Point ─────────────────────────────────────────────────────────

def analyse_and_generate(
    filepath: str,
    context: dict,
    diagnostics: str = "",
    attempt: int = 1,
) -> str:
    """
    Calls OpenRouter with the full context payload and returns
    extracted, executable pytest test code.

    Args:
        filepath:    The source file being tested
        context:     Dict with keys: source, diff, existing_tests, imports, knowledge
        diagnostics: Validation failure output from previous attempt (retry context)
        attempt:     Current attempt number (1-based, used in logging)

    Returns:
        String containing only the Python test code (no fences, no preamble)
    """
    _validate_api_key()

    user_prompt = _build_prompt(filepath, context, diagnostics, attempt)

    print(f"[AIAgent] OpenRouter → model: {OPENROUTER_MODEL}")
    print(f"[AIAgent] Attempt {attempt} for: {filepath}")

    raw_text = _call_openrouter(user_prompt)
    return _extract_code_block(raw_text)


# ── OpenRouter API Call ────────────────────────────────────────────────────────

def _call_openrouter(user_prompt: str) -> str:
    """
    POSTs to OpenRouter's /chat/completions endpoint.
    Uses the OpenAI message format — compatible with all OpenRouter models.
    """
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type":  "application/json",
        # These headers appear in your OpenRouter usage dashboard
        "HTTP-Referer":  OPENROUTER_APP_URL,
        "X-Title":       OPENROUTER_APP_NAME,
    }

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ],
        "max_tokens":  4096,
        "temperature": OPENROUTER_TEMPERATURE,
        # Ask OpenRouter to prefer providers with low latency
        "provider": {
            "sort": "throughput",
        },
    }

    try:
        response = requests.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=120,
        )
    except requests.Timeout:
        raise RuntimeError(
            "OpenRouter request timed out after 120s. "
            "Try a faster model (e.g. openai/gpt-4o-mini) or increase timeout."
        )
    except requests.ConnectionError as e:
        raise RuntimeError(f"OpenRouter connection failed: {e}")

    # ── Handle HTTP errors with useful messages ────────────────────────────────
    if response.status_code == 401:
        raise RuntimeError(
            "OpenRouter returned 401 Unauthorized. "
            "Check that OPENROUTER_API_KEY is set correctly."
        )
    if response.status_code == 402:
        raise RuntimeError(
            "OpenRouter returned 402 Payment Required. "
            "Add credits at https://openrouter.ai/credits"
        )
    if response.status_code == 429:
        raise RuntimeError(
            "OpenRouter rate limit hit (429). "
            "Reduce request frequency or upgrade your plan."
        )
    if response.status_code != 200:
        raise RuntimeError(
            f"OpenRouter API error {response.status_code}:\n{response.text[:600]}"
        )

    # ── Parse response ─────────────────────────────────────────────────────────
    data = response.json()

    # Log token usage for cost tracking
    usage = data.get("usage", {})
    if usage:
        print(
            f"[AIAgent] Tokens — prompt: {usage.get('prompt_tokens', '?')} | "
            f"completion: {usage.get('completion_tokens', '?')} | "
            f"total: {usage.get('total_tokens', '?')}"
        )

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(
            f"Unexpected OpenRouter response shape. "
            f"Expected choices[0].message.content. Got: {data}"
        ) from e


# ── Prompt Builder ─────────────────────────────────────────────────────────────

def _build_prompt(
    filepath: str,
    context: dict,
    diagnostics: str,
    attempt: int,
) -> str:
    """Assembles the structured user prompt sent to the model."""
    source         = context.get("source", "")
    diff           = context.get("diff", "")
    existing_tests = context.get("existing_tests")
    knowledge      = context.get("knowledge", "")

    existing_block = (
        f"## Existing Tests (keep valid ones, update outdated ones)\n"
        f"```python\n{existing_tests}\n```"
        if existing_tests
        else "## Existing Tests\nNone — generate a brand new test file from scratch."
    )

    retry_block = (
        f"\n## ⚠️ Attempt #{attempt - 1} Failed — Fix These Specific Issues\n"
        f"```\n{diagnostics}\n```\n"
        if diagnostics
        else ""
    )

    return f"""
## Project Knowledge Base
{knowledge}

## Source File: `{filepath}`
```python
{source}
```

## Git Diff (what changed)
```diff
{diff}
```

{existing_block}
{retry_block}

Generate the complete, updated test file for `{filepath}`.
Output ONLY a single ```python ... ``` code block — no explanation, no preamble.
""".strip()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _validate_api_key() -> None:
    """Fails fast with a clear message if the API key is missing."""
    if not OPENROUTER_API_KEY:
        raise ValueError(
            "OPENROUTER_API_KEY is not set.\n"
            "  • Local: add it to your .env file\n"
            "  • GitHub Actions: Settings → Secrets → Actions → OPENROUTER_API_KEY"
        )


def _extract_code_block(text: str) -> str:
    """
    Extracts the first ```python ... ``` fenced block from the model response.
    Falls back to returning the raw text if no fences are found.
    """
    match = re.search(r"```python\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    print("[AIAgent] Warning: no ```python block detected — using raw response as-is")
    return text.strip()