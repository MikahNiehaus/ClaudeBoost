"""
ClaudeBoost TDD guard: PreToolUse hook on Edit|Write|MultiEdit.

Enforces test driven development by checking whether a corresponding test
file was modified before allowing source file edits. Uses git diff detection
(no LLM calls, no external API dependency).

Modes (set via CLAUDEBOOST_TDD_GUARD env var):
  soft   (default) = warning on stderr, exit 0 (nudge, does not block)
  strict           = hard block, exit 2
  off              = disabled, exit 0 silently

Exit codes:
  0 = allow (pass)
  2 = block (strict mode only)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

_BOOST_HOME = Path(os.environ.get("CLAUDEBOOST_HOME") or Path(__file__).resolve().parent.parent)

GATED_TOOLS = {"Edit", "Write", "MultiEdit"}

# Directories where TDD enforcement does not apply.
EXEMPT_SEGMENTS = [
    "workspace",
    "knowledge",
    "plans",
    "docs",
    "state",
    ".claudeboost",
    ".claude",
]

# Patterns that identify a file as a test file.
# {name} is replaced with the base name (no extension) of the source file.
# When checking if the edited file IS a test, we match against the filename itself.
TEST_FILE_INDICATORS = [
    r"^test_",           # Python: test_auth.py
    r"_test\.",          # Go: auth_test.go
    r"\.test\.",         # JS/TS: auth.test.ts
    r"\.spec\.",         # JS/TS: auth.spec.ts
    r"tests\.",          # C#: AuthTests.cs (lowercased; _is_test_file lowercases name)
    r"_spec\.",          # Ruby: auth_spec.rb
    r"__tests__/",       # JS convention dir
    r"/tests?/",         # tests/ or test/ dir
]

# Patterns for finding a corresponding test file given a source file name.
# {name} is the stem of the source file (e.g. "auth" from "auth.py").
CORRESPONDING_TEST_PATTERNS = [
    "test_{name}.",
    "{name}_test.",
    "{name}.test.",
    "{name}.spec.",
    "{name}Tests.",
    "{name}_spec.",
    "{name}Test.",
]


def _write_block_telemetry(tool: str, summary: str, reason: str) -> None:
    """Write a PreToolUse block event to claude-actions.jsonl.

    PostToolUse never fires when a PreToolUse hook exits 2, so we capture
    the block here before returning. Pattern from bash-guard.py:41-59.
    """
    try:
        sys.path.insert(0, str(_BOOST_HOME / "scripts"))
        from telemetry_writer import now_iso, session_id, write_telemetry
        record = {
            "ts": now_iso(),
            "session_id": session_id(),
            "tool": tool,
            "summary": f"{tool} {summary[:200]}",
            "result": "blocked",
            "hook_event": "PreToolUse",
            "block_reason": reason[:300],
        }
        write_telemetry(record, "claude-actions.jsonl")
    except Exception:
        pass


def _get_mode() -> str:
    """Read TDD guard mode from env var. Default: soft."""
    mode = os.environ.get("CLAUDEBOOST_TDD_GUARD", "soft").lower().strip()
    if mode in ("soft", "strict", "off"):
        return mode
    return "soft"


def _path_has_segment(canonical_path: str, segment: str) -> bool:
    """Check if a path contains a segment at a directory boundary.

    Splits on "/" and matches whole segments so "docs" hits a docs/ dir but
    not a docsomething.py file.
    """
    seg = segment.strip("/").lower()
    parts = canonical_path.split("/")
    return seg in parts


def _is_temp_path(canonical_path: str) -> bool:
    """Check if a file is in a system temp directory.

    Collects the resolved temp dirs from tempfile plus the TEMP/TMP/TMPDIR
    env vars and /tmp, /var/tmp, then checks whether the path sits under one.
    """
    temp_dirs = set()
    try:
        temp_dirs.add(Path(tempfile.gettempdir()).resolve().as_posix().lower())
    except Exception:
        pass
    for var in ("TEMP", "TMP", "TMPDIR"):
        val = os.environ.get(var)
        if val:
            try:
                temp_dirs.add(Path(val).resolve().as_posix().lower())
            except Exception:
                pass
    for d in ("/tmp", "/var/tmp"):
        try:
            p = Path(d)
            if p.exists():
                temp_dirs.add(p.resolve().as_posix().lower())
        except Exception:
            pass
    for td in temp_dirs:
        if canonical_path.startswith(td + "/") or canonical_path == td:
            return True
    return False


def _is_exempt(file_path: str) -> bool:
    """Check if a file is exempt from TDD enforcement."""
    canonical = Path(file_path).resolve().as_posix().lower()
    for seg in EXEMPT_SEGMENTS:
        if _path_has_segment(canonical, seg):
            return True
    if _is_temp_path(canonical):
        return True
    return False


def _is_test_file(file_path: str) -> bool:
    """Check if a file is itself a test file."""
    name = Path(file_path).name.lower()
    full = file_path.replace("\\", "/").lower()
    for pattern in TEST_FILE_INDICATORS:
        if re.search(pattern, name) or re.search(pattern, full):
            return True
    return False


def _get_changed_files() -> list[str]:
    """Get files with uncommitted changes (staged + unstaged) via git diff.

    Returns a list of file paths relative to the repo root.
    Falls back to empty list if git is not available or not in a repo.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            # HEAD might not exist (fresh repo). Try without HEAD.
            result = subprocess.run(
                ["git", "diff", "--name-only"],
                capture_output=True, text=True, timeout=5,
            )
        staged = subprocess.run(
            ["git", "diff", "--name-only", "--cached"],
            capture_output=True, text=True, timeout=5,
        )
        files = set()
        for out in (result.stdout, staged.stdout):
            for line in out.strip().splitlines():
                line = line.strip()
                if line:
                    files.add(line)
        return list(files)
    except Exception:
        return []


def _has_corresponding_test(source_path: str, changed_files: list[str]) -> bool:
    """Check if any changed file is a test for the given source file.

    Looks for test files matching the source file's stem using
    CORRESPONDING_TEST_PATTERNS and also checks if any test file
    in the same directory tree was modified.
    """
    stem = Path(source_path).stem.lower()

    # Build expected test name patterns
    expected = []
    for pattern in CORRESPONDING_TEST_PATTERNS:
        expected.append(pattern.format(name=stem).lower())

    for changed in changed_files:
        changed_lower = changed.replace("\\", "/").lower()
        changed_name = Path(changed).name.lower()

        # Direct name match against expected patterns
        for exp in expected:
            if exp in changed_name:
                return True

        # Also accept any test file in the changed set
        if _is_test_file(changed):
            return True

    return False


def _get_file_paths(tool_name: str, tool_input: dict) -> list[str]:
    """Extract file path(s) from tool input. Same pattern as consult-gate.py:66-76."""
    if tool_name == "MultiEdit":
        edits = tool_input.get("edits") or []
        return [
            e.get("file_path", "")
            for e in edits
            if e.get("file_path")
        ]
    fp = tool_input.get("file_path") or tool_input.get("path") or ""
    return [fp] if fp else []


BLOCK_MESSAGE = """\
[TDD Guard] No test changes detected for: {file_name}

Write the failing test FIRST, then edit the source file.

The TDD cycle:
  1. Write a test that describes the desired behavior (RED)
  2. Run it and confirm it fails
  3. Edit the source file to make it pass (GREEN)
  4. Refactor if needed (REFACTOR)

TDD guard checks git diff for test file changes matching "{stem}".
Expected test files: test_{stem}.*, {stem}_test.*, {stem}.test.*, {stem}.spec.*

Mode: {mode} (set CLAUDEBOOST_TDD_GUARD=off to disable, =strict to hard block)
"""


def main() -> int:
    mode = _get_mode()
    if mode == "off":
        return 0

    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, ValueError):
        return 0

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})

    if tool_name not in GATED_TOOLS:
        return 0

    file_paths = _get_file_paths(tool_name, tool_input)
    if not file_paths:
        return 0

    # Check AUTO mode bypass (same as consult-gate.py:83-86)
    home = os.environ.get("CLAUDEBOOST_HOME") or str(_BOOST_HOME)
    try:
        mode_file = Path(home) / "state" / "claudeboost-mode.json"
        cb_mode = json.loads(mode_file.read_text(encoding="utf-8")).get("mode", "CONSULT")
        if cb_mode == "AUTO":
            return 0
    except Exception:
        pass

    changed_files = _get_changed_files()

    for fp in file_paths:
        if _is_exempt(fp):
            continue
        if _is_test_file(fp):
            continue
        if _has_corresponding_test(fp, changed_files):
            continue

        # No test found for this source file
        stem = Path(fp).stem
        msg = BLOCK_MESSAGE.format(
            file_name=Path(fp).name,
            stem=stem,
            mode=mode,
        )

        if mode == "strict":
            _write_block_telemetry(tool_name, fp, "tdd_guard_no_test")
            print(msg, file=sys.stderr)
            return 2
        else:
            # Soft mode: warn but allow
            print(msg, file=sys.stderr)
            return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
