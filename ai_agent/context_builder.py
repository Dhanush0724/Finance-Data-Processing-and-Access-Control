"""
context_builder.py
──────────────────
Assembles the full context payload sent to the AI agent for each changed file.

Pipeline position:  Change Detector → [Context Builder] → AI Agent
Input:              ChangedFile objects from change_detector.py
Output:             Context dicts ready to pass into ai_agent.analyse_and_generate()

What it builds for each file:
1. source        — full current source code of the changed file
2. diff          — the raw git diff for that file
3. existing_tests — content of the existing test file (if one exists)
4. imports       — resolved import graph (what the file depends on)
5. knowledge     — finance domain context from knowledge.md
"""

import ast
import os
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from ai_agent.change_detector import ChangedFile
from ai_agent.config import (
    REPO_ROOT,
    SRC_DIR,
    TEST_DIR,
    KNOWLEDGE_FILE,
)


# ── Data Model ─────────────────────────────────────────────────────────────────

class ContextPayload:
    """
    Structured context package for a single file passed to the AI agent.

    Attributes:
        filepath:       Relative path of the source file
        source:         Full source code of the file
        diff:           Raw git diff for this file
        existing_tests: Content of the existing test file (None if not found)
        imports:        Resolved source of imported local modules
        knowledge:      Finance domain knowledge base content
        test_filepath:  Where the test file should be written
    """

    def __init__(
        self,
        filepath: str,
        source: str,
        diff: str,
        existing_tests: Optional[str],
        imports: str,
        knowledge: str,
        test_filepath: str,
    ):
        self.filepath       = filepath
        self.source         = source
        self.diff           = diff
        self.existing_tests = existing_tests
        self.imports        = imports
        self.knowledge      = knowledge
        self.test_filepath  = test_filepath

    def to_dict(self) -> dict:
        """Returns the payload as a plain dict — matches ai_agent.analyse_and_generate() signature."""
        return {
            "source":         self.source,
            "diff":           self.diff,
            "existing_tests": self.existing_tests,
            "imports":        self.imports,
            "knowledge":      self.knowledge,
        }

    def __repr__(self) -> str:
        has_tests   = self.existing_tests is not None
        import_size = len(self.imports.splitlines())
        return (
            f"ContextPayload({self.filepath!r}, "
            f"existing_tests={has_tests}, "
            f"import_lines={import_size})"
        )


# ── Public Entry Point ─────────────────────────────────────────────────────────

def build_context(changed_file: ChangedFile) -> Optional[ContextPayload]:
    """
    Builds a complete ContextPayload for a single ChangedFile.

    Returns None if the source file cannot be read (e.g. deleted files
    where we skip test generation since there's nothing to test).

    Args:
        changed_file: A ChangedFile object from change_detector.detect_changes()

    Returns:
        ContextPayload ready to pass to ai_agent.analyse_and_generate(),
        or None if the file should be skipped.
    """
    filepath = changed_file.filepath

    # Skip deleted files — nothing to test
    if changed_file.is_deleted:
        print(f"[ContextBuilder] Skipping deleted file: {filepath}")
        return None

    print(f"[ContextBuilder] Building context for: {filepath}")

    # 1. Read source code
    source = _read_source(changed_file.absolute_path)
    if source is None:
        print(f"[ContextBuilder] Could not read source — skipping: {filepath}")
        return None

    # 2. Locate and read existing test file
    test_filepath    = _resolve_test_filepath(filepath)
    existing_tests   = _read_existing_tests(test_filepath)

    if existing_tests:
        print(f"[ContextBuilder] Found existing tests: {test_filepath}")
    else:
        print(f"[ContextBuilder] No existing tests found — will generate from scratch")

    # 3. Resolve local imports
    imports = _resolve_imports(source, filepath)

    # 4. Load knowledge base
    knowledge = _load_knowledge()

    payload = ContextPayload(
        filepath=filepath,
        source=source,
        diff=changed_file.diff,
        existing_tests=existing_tests,
        imports=imports,
        knowledge=knowledge,
        test_filepath=test_filepath,
    )

    print(f"[ContextBuilder] Context ready: {payload}")
    return payload


def build_all_contexts(changed_files: list[ChangedFile]) -> list[ContextPayload]:
    """
    Builds context payloads for a list of changed files.
    Filters out any files that return None (deleted or unreadable).

    Args:
        changed_files: Output from change_detector.detect_changes()

    Returns:
        List of ContextPayload objects, one per processable file
    """
    payloads = []
    for cf in changed_files:
        payload = build_context(cf)
        if payload is not None:
            payloads.append(payload)

    print(f"[ContextBuilder] {len(payloads)} context(s) built from {len(changed_files)} changed file(s)")
    return payloads


# ── Source Reading ─────────────────────────────────────────────────────────────

def _read_source(absolute_path: str) -> Optional[str]:
    """
    Reads and returns the full source code of a file.
    Returns None if the file does not exist or cannot be decoded.
    """
    path = Path(absolute_path)

    if not path.exists():
        print(f"[ContextBuilder] File not found on disk: {absolute_path}")
        return None

    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        print(f"[ContextBuilder] Could not decode file as UTF-8: {absolute_path}")
        return None


# ── Test File Resolution ───────────────────────────────────────────────────────

def _resolve_test_filepath(source_filepath: str) -> str:
    """
    Maps a source filepath to its corresponding test filepath.

    Examples:
        backend/services/payment.py       → tests/services/test_payment.py
        backend/routes/auth.py            → tests/routes/test_auth.py
        backend/models/transaction.py     → tests/models/test_transaction.py

    Strategy:
    - Strip the SRC_DIR prefix from the filepath
    - Prepend TEST_DIR
    - Prefix the filename with "test_"
    """
    path = Path(source_filepath)

    # Remove the leading SRC_DIR component
    try:
        relative = path.relative_to(SRC_DIR)
    except ValueError:
        # Fallback: just use the filename if SRC_DIR stripping fails
        relative = Path(path.name)

    # Build test path: tests/<subdirs>/test_<filename>
    test_filename = f"test_{relative.name}"
    test_path     = Path(TEST_DIR) / relative.parent / test_filename

    return str(test_path)


def _read_existing_tests(test_filepath: str) -> Optional[str]:
    """
    Reads an existing test file if it exists.
    Returns None if no test file is found (first-time generation).
    """
    path = Path(REPO_ROOT) / test_filepath

    if not path.exists():
        return None

    try:
        content = path.read_text(encoding="utf-8")
        # Return None if the file is empty or only has comments/whitespace
        if not content.strip() or not _has_test_functions(content):
            return None
        return content
    except (UnicodeDecodeError, OSError):
        return None


def _has_test_functions(content: str) -> bool:
    """Returns True if the file contains at least one test function."""
    return bool("def test_" in content)


# ── Import Resolution ──────────────────────────────────────────────────────────

def _resolve_imports(source: str, source_filepath: str) -> str:
    """
    Parses the source file's imports and reads the content of any local
    modules it depends on. This gives the AI full awareness of dependencies.

    Only resolves LOCAL imports (same repo) — stdlib and third-party
    packages are skipped since the AI already knows those.

    Returns a formatted string of all resolved import sources,
    or an empty string if no local imports are found.
    """
    local_imports = _extract_local_imports(source, source_filepath)

    if not local_imports:
        return ""

    resolved_parts = []

    for module_path, import_name in local_imports:
        content = _read_source(module_path)
        if content:
            resolved_parts.append(
                f"### Imported module: `{import_name}`\n"
                f"```python\n{content}\n```"
            )
            print(f"[ContextBuilder] Resolved import: {import_name}")
        else:
            print(f"[ContextBuilder] Could not resolve import: {import_name}")

    return "\n\n".join(resolved_parts)


def _extract_local_imports(source: str, source_filepath: str) -> list[tuple[str, str]]:
    """
    Uses AST parsing to extract local module imports from a source file.

    Returns list of (absolute_path, import_name) tuples for local modules only.
    Skips stdlib and third-party packages.
    """
    results = []
    source_dir = Path(REPO_ROOT) / Path(source_filepath).parent

    try:
        tree = ast.parse(source)
    except SyntaxError:
        print(f"[ContextBuilder] AST parse failed for {source_filepath} — skipping import resolution")
        return []

    for node in ast.walk(tree):
        # Handle: from .module import something  /  from backend.x import y
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""

            # Relative imports (from . import x)
            if node.level and node.level > 0:
                candidate = source_dir / f"{module.replace('.', '/')}.py"
                if candidate.exists():
                    results.append((str(candidate), module))
                continue

            # Absolute local imports (from backend.services.x import y)
            candidate = _module_to_path(module)
            if candidate:
                results.append((candidate, module))

        # Handle: import backend.utils
        elif isinstance(node, ast.Import):
            for alias in node.names:
                candidate = _module_to_path(alias.name)
                if candidate:
                    results.append((candidate, alias.name))

    return results


def _module_to_path(module_name: str) -> Optional[str]:
    """
    Converts a dotted module name to a filesystem path if it exists
    within the repo's SRC_DIR.

    Example: "backend.services.payment" → "/repo/backend/services/payment.py"
    Returns None if the module is not a local file (stdlib / third-party).
    """
    parts = module_name.split(".")
    candidate = Path(REPO_ROOT).joinpath(*parts).with_suffix(".py")

    if candidate.exists():
        return str(candidate)

    # Also try as a package __init__.py
    init_candidate = Path(REPO_ROOT).joinpath(*parts, "__init__.py")
    if init_candidate.exists():
        return str(init_candidate)

    return None


# ── Knowledge Base ─────────────────────────────────────────────────────────────

def _load_knowledge() -> str:
    """
    Loads the finance domain knowledge base from knowledge.md.
    This is injected into every AI agent call to ground its reasoning.

    Returns an empty string if the file doesn't exist yet
    (the pipeline still works — knowledge is optional context).
    """
    knowledge_path = Path(REPO_ROOT) / KNOWLEDGE_FILE

    if not knowledge_path.exists():
        print(f"[ContextBuilder] Knowledge file not found: {KNOWLEDGE_FILE} — continuing without it")
        return ""

    try:
        content = knowledge_path.read_text(encoding="utf-8")
        print(f"[ContextBuilder] Loaded knowledge base: {KNOWLEDGE_FILE} ({len(content)} chars)")
        return content
    except (UnicodeDecodeError, OSError) as e:
        print(f"[ContextBuilder] Could not read knowledge file: {e}")
        return ""


# ── CLI (manual testing) ───────────────────────────────────────────────────────

if __name__ == "__main__":
    """
    Run directly to test context building locally:

        python ai_agent/context_builder.py backend/services/payment.py

    Prints a summary of what context would be sent to the AI agent.
    """
    import sys
    from ai_agent.change_detector import ChangedFile

    if len(sys.argv) < 2:
        print("Usage: python ai_agent/context_builder.py <filepath>")
        print("Example: python ai_agent/context_builder.py backend/services/payment.py")
        sys.exit(1)

    target = sys.argv[1]
    abs_path = str(Path(REPO_ROOT) / target)

    # Simulate a ChangedFile for testing
    mock_cf = ChangedFile(
        filepath=target,
        absolute_path=abs_path,
        diff="(simulated diff — run via pipeline for real diff)",
        changed_functions=[],
        changed_classes=[],
        is_new_file=False,
        is_deleted=False,
    )

    payload = build_context(mock_cf)

    if payload is None:
        print("\n[ContextBuilder] No payload generated — file may be deleted or unreadable.")
    else:
        print(f"\n[ContextBuilder] ── Payload Summary ──────────────────────────")
        print(f"  Source file   : {payload.filepath}")
        print(f"  Test file     : {payload.test_filepath}")
        print(f"  Source lines  : {len(payload.source.splitlines())}")
        print(f"  Has tests     : {payload.existing_tests is not None}")
        print(f"  Import lines  : {len(payload.imports.splitlines())}")
        print(f"  Knowledge     : {len(payload.knowledge)} chars")
        print(f"────────────────────────────────────────────────────────────────")