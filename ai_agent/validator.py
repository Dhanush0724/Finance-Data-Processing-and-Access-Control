"""
validator.py
────────────
Validates AI-generated test code before it touches the codebase.

Pipeline position:  AI Agent → [Validator] → Retry Controller → Test Writer
Input:              Raw Python test code string from ai_agent.analyse_and_generate()
Output:             ValidationResult — pass/fail + structured diagnostics

Three-layer validation gate:
1. Syntax check     — AST parse to catch any syntax errors
2. Structure check  — must have at least one test function, valid imports
3. Safety check     — must not contain real credentials, DB URLs, or HTTP calls

If any layer fails, the diagnostics are fed back into the AI agent
by the retry controller for a corrected attempt.
"""

import ast
import re
import sys
import os
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from ai_agent.config import MIN_TEST_FUNCTIONS


# ── Data Model ─────────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    """
    Result of validating a generated test file.

    Attributes:
        passed:      True if all checks passed and the code is safe to write
        errors:      List of blocking errors (cause retry)
        warnings:    List of non-blocking issues (logged but don't cause retry)
        diagnostics: Formatted string fed back to the AI agent on retry
    """
    passed:      bool
    errors:      list[str] = field(default_factory=list)
    warnings:    list[str] = field(default_factory=list)
    diagnostics: str = ""

    def __repr__(self) -> str:
        status = "PASSED" if self.passed else "FAILED"
        return (
            f"ValidationResult({status}, "
            f"errors={len(self.errors)}, "
            f"warnings={len(self.warnings)})"
        )


# ── Public Entry Point ─────────────────────────────────────────────────────────

def validate(code: str, filepath: str = "<generated>") -> ValidationResult:
    """
    Runs all validation checks on AI-generated test code.

    Args:
        code:     The raw Python test code string to validate
        filepath: The intended file path (used in error messages only)

    Returns:
        ValidationResult with passed=True if all checks pass,
        or passed=False with diagnostics to feed back to the AI agent.
    """
    errors:   list[str] = []
    warnings: list[str] = []

    print(f"[Validator] Validating generated code for: {filepath}")

    if not code or not code.strip():
        return ValidationResult(
            passed=False,
            errors=["Generated code is empty."],
            diagnostics="The generated output was empty. Generate a complete pytest test file.",
        )

    # ── Layer 1: Syntax Check ──────────────────────────────────────────────────
    syntax_errors = _check_syntax(code)
    errors.extend(syntax_errors)

    # If syntax is broken, skip further checks — they'll produce false results
    if syntax_errors:
        print(f"[Validator] ✗ Syntax check failed: {len(syntax_errors)} error(s)")
        return _build_result(errors, warnings, code)

    print("[Validator] ✓ Syntax check passed")

    # ── Layer 2: Structure Check ───────────────────────────────────────────────
    structure_errors, structure_warnings = _check_structure(code)
    errors.extend(structure_errors)
    warnings.extend(structure_warnings)

    if structure_errors:
        print(f"[Validator] ✗ Structure check failed: {len(structure_errors)} error(s)")
    else:
        print("[Validator] ✓ Structure check passed")

    # ── Layer 3: Safety Check ──────────────────────────────────────────────────
    safety_errors, safety_warnings = _check_safety(code)
    errors.extend(safety_errors)
    warnings.extend(safety_warnings)

    if safety_errors:
        print(f"[Validator] ✗ Safety check failed: {len(safety_errors)} error(s)")
    else:
        print("[Validator] ✓ Safety check passed")

    # ── Log warnings ───────────────────────────────────────────────────────────
    for warning in warnings:
        print(f"[Validator] ⚠ Warning: {warning}")

    result = _build_result(errors, warnings, code)
    status = "PASSED" if result.passed else "FAILED"
    print(f"[Validator] Result: {status} — {len(errors)} error(s), {len(warnings)} warning(s)")
    return result


# ── Layer 1: Syntax Check ──────────────────────────────────────────────────────

def _check_syntax(code: str) -> list[str]:
    """
    Uses Python's AST parser to detect syntax errors.
    Returns a list of error strings (empty = no errors).
    """
    try:
        ast.parse(code)
        return []
    except SyntaxError as e:
        return [
            f"SyntaxError on line {e.lineno}: {e.msg}\n"
            f"  Offending text: {e.text.strip() if e.text else 'unknown'}"
        ]
    except ValueError as e:
        # ast.parse raises ValueError for null bytes etc.
        return [f"Parse error: {e}"]


# ── Layer 2: Structure Check ───────────────────────────────────────────────────

def _check_structure(code: str) -> tuple[list[str], list[str]]:
    """
    Validates the structure of the generated test file:
    - Must have at least MIN_TEST_FUNCTIONS test functions
    - Test functions must follow the correct naming convention
    - Must import pytest
    - Must not import from __main__
    - Classes should follow TestClass naming if present

    Returns (errors, warnings)
    """
    errors:   list[str] = []
    warnings: list[str] = []

    try:
        tree = ast.parse(code)
    except SyntaxError:
        # Already caught in layer 1
        return errors, warnings

    # ── Count test functions ───────────────────────────────────────────────────
    test_functions = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name.startswith("test_")
    ]

    if len(test_functions) < MIN_TEST_FUNCTIONS:
        errors.append(
            f"Generated code contains {len(test_functions)} test function(s). "
            f"Minimum required: {MIN_TEST_FUNCTIONS}. "
            f"Generate more comprehensive tests covering happy path, edge cases, and error paths."
        )
    else:
        print(f"[Validator] Found {len(test_functions)} test function(s)")

    # ── Check test naming convention ───────────────────────────────────────────
    bad_names = [
        fn.name for fn in test_functions
        if not _is_valid_test_name(fn.name)
    ]
    if bad_names:
        warnings.append(
            f"Test functions with non-descriptive names: {bad_names}. "
            f"Use pattern: test_<function>_<scenario>_<expected_result>"
        )

    # ── Check pytest is imported ───────────────────────────────────────────────
    imports = _get_all_imports(tree)
    if "pytest" not in imports:
        errors.append(
            "pytest is not imported. Add 'import pytest' at the top of the file."
        )

    # ── Check for __main__ imports ─────────────────────────────────────────────
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and "__main__" in node.module:
                errors.append(
                    f"Invalid import from __main__: 'from {node.module} import ...'. "
                    f"Import directly from the module being tested."
                )

    # ── Check for assert statements (not just pass) ────────────────────────────
    has_assertions = _has_assertions(tree)
    if not has_assertions:
        errors.append(
            "No assert statements or pytest.raises() found. "
            "Tests must contain assertions to verify behaviour."
        )

    # ── Check for fixture usage or setup ──────────────────────────────────────
    fixtures = _get_fixtures(tree)
    if not fixtures and len(test_functions) > 3:
        warnings.append(
            "No pytest fixtures found. Consider using fixtures for shared setup "
            "to avoid code duplication across tests."
        )

    # ── Warn if no mocking detected ───────────────────────────────────────────
    if "unittest.mock" not in " ".join(imports) and "pytest_mock" not in " ".join(imports):
        if "mock" not in code.lower() and "patch" not in code.lower():
            warnings.append(
                "No mocking detected (unittest.mock / pytest-mock). "
                "Financial backend tests should mock DB sessions, external APIs, and auth tokens."
            )

    return errors, warnings


def _is_valid_test_name(name: str) -> bool:
    """
    Returns True if a test function name is sufficiently descriptive.
    Valid: test_process_payment_zero_amount_raises_error
    Too short: test_payment, test_1
    """
    parts = name.split("_")
    # Must have at least 3 parts: test + function + scenario
    return len(parts) >= 3


def _get_all_imports(tree: ast.AST) -> list[str]:
    """Returns a flat list of all imported module names in the AST."""
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def _has_assertions(tree: ast.AST) -> bool:
    """Returns True if the code contains assert statements or pytest.raises calls."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            return True
        # pytest.raises() used as context manager
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "raises":
                return True
            if isinstance(func, ast.Name) and func.id == "raises":
                return True
    return False


def _get_fixtures(tree: ast.AST) -> list[str]:
    """Returns names of all pytest fixture functions in the AST."""
    fixtures = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Attribute) and decorator.attr == "fixture":
                    fixtures.append(node.name)
                elif isinstance(decorator, ast.Name) and decorator.id == "fixture":
                    fixtures.append(node.name)
    return fixtures


# ── Layer 3: Safety Check ──────────────────────────────────────────────────────

# Patterns that indicate unsafe content in generated test code
_SAFETY_PATTERNS: list[tuple[str, str, bool]] = [
    # (regex pattern, error message, is_blocking)

    # Real credentials
    (
        r'(?i)(password|secret|api_key|token)\s*=\s*["\'][^"\']{8,}["\']',
        "Possible hardcoded credential detected. Use mock values like 'test_password' or MagicMock().",
        False,  # warning — could be a test value
    ),
    (
        r'(?i)Bearer\s+ey[A-Za-z0-9_-]{20,}',
        "Real JWT token detected. Use a mock token string like 'mock_token' instead.",
        True,   # error — real JWT in tests is a security risk
    ),

    # Real database connections
    (
        r'(?i)(postgresql|mysql|sqlite):\/\/[^\s"\']+',
        "Real database connection string detected. Mock the DB session instead of connecting to a real DB.",
        True,
    ),
    (
        r'(?i)create_engine\s*\(\s*["\'][^"\']+["\']',
        "Real SQLAlchemy engine creation detected. Use a mock session, not a real engine.",
        True,
    ),

    # Real HTTP calls
    (
        r'(?i)requests\.(get|post|put|delete|patch)\s*\(\s*["\']https?://',
        "Real HTTP call detected. Mock 'requests' with unittest.mock.patch instead.",
        True,
    ),
    (
        r'(?i)httpx\.(get|post|put|delete|patch)\s*\(\s*["\']https?://',
        "Real HTTP call via httpx detected. Mock the HTTP client instead.",
        True,
    ),

    # Real email/PII patterns
    (
        r'\b[A-Za-z0-9._%+-]+@(?!example\.com|test\.com|pytest\.org)[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        "Possible real email address detected. Use test emails like 'user@example.com'.",
        False,  # warning — might be intentional test data
    ),

    # sleep() calls that slow down tests
    (
        r'\btime\.sleep\s*\(\s*[1-9]',
        "time.sleep() with non-zero value detected. Use mocking or pytest-timeout instead of real sleeps.",
        False,  # warning
    ),

    # print() left in test code
    (
        r'^\s*print\s*\(',
        "print() statement in test code. Use pytest's capsys fixture for output testing.",
        False,  # warning
    ),
]


def _check_safety(code: str) -> tuple[list[str], list[str]]:
    """
    Scans generated code for safety anti-patterns:
    real credentials, real DB connections, real HTTP calls, PII.

    Returns (errors, warnings)
    """
    errors:   list[str] = []
    warnings: list[str] = []

    for pattern, message, is_blocking in _SAFETY_PATTERNS:
        if re.search(pattern, code, re.MULTILINE):
            if is_blocking:
                errors.append(f"Safety violation: {message}")
            else:
                warnings.append(f"Safety advisory: {message}")

    return errors, warnings


# ── Result Builder ─────────────────────────────────────────────────────────────

def _build_result(
    errors: list[str],
    warnings: list[str],
    code: str,
) -> ValidationResult:
    """
    Assembles the final ValidationResult with formatted diagnostics
    suitable for feeding back into the AI agent on retry.
    """
    passed = len(errors) == 0

    if passed:
        return ValidationResult(passed=True, warnings=warnings, diagnostics="")

    # Build structured diagnostics for the AI agent retry prompt
    diagnostics_lines = [
        "The previously generated test code failed validation. Fix ALL of the following issues:",
        "",
    ]

    for i, error in enumerate(errors, 1):
        diagnostics_lines.append(f"{i}. ERROR: {error}")

    if warnings:
        diagnostics_lines.append("")
        diagnostics_lines.append("Additionally, address these warnings:")
        for warning in warnings:
            diagnostics_lines.append(f"   • {warning}")

    diagnostics_lines.extend([
        "",
        "Rules reminder:",
        "- Output ONLY a single ```python ... ``` code block",
        "- Include ALL necessary imports (especially pytest)",
        "- Mock ALL external dependencies (DB, HTTP, auth)",
        "- Use Decimal for all financial amounts, never float",
        "- Every test function must contain at least one assertion",
        "- Name tests: test_<function>_<scenario>_<expected_result>",
    ])

    return ValidationResult(
        passed=False,
        errors=errors,
        warnings=warnings,
        diagnostics="\n".join(diagnostics_lines),
    )


# ── CLI (manual testing) ───────────────────────────────────────────────────────

if __name__ == "__main__":
    """
    Run directly to validate a test file manually:

        python ai_agent/validator.py tests/services/test_payment.py
        echo "import pytest\ndef test_foo(): assert True" | python ai_agent/validator.py
    """
    import sys

    if len(sys.argv) > 1:
        # Validate a file
        filepath = sys.argv[1]
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                code = f.read()
        except FileNotFoundError:
            print(f"File not found: {filepath}")
            sys.exit(1)
    else:
        # Read from stdin
        print("Reading from stdin (Ctrl+D to finish)...")
        code = sys.stdin.read()
        filepath = "<stdin>"

    result = validate(code, filepath)

    print(f"\n{'='*60}")
    print(f"Validation: {'PASSED ✓' if result.passed else 'FAILED ✗'}")
    print(f"{'='*60}")

    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")
        for err in result.errors:
            print(f"  ✗ {err}")

    if result.warnings:
        print(f"\nWarnings ({len(result.warnings)}):")
        for warn in result.warnings:
            print(f"  ⚠ {warn}")

    if not result.passed:
        print(f"\nDiagnostics (sent to AI on retry):\n{result.diagnostics}")

    sys.exit(0 if result.passed else 1)