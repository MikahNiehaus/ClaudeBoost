"""
ClaudeBoost spec-sheet gate — PreToolUse hook.

Enforces that every Edit, MultiEdit, and Write tool call targets a file
that was explicitly approved in state/spec-sheet.json before work started.

Behavior:
  - AUTO mode              → exit 0 silently
  - Bash / read-only tools → exit 0 silently
  - Exempt paths           → exit 0 silently (workspace/, state/, .claudeboost/, plans/, docs/)
  - File in approved_files → exit 0 (go ahead)
  - No spec-sheet.json     → permissionDecision:"ask" with instructions to make a spec sheet
  - File not in spec       → permissionDecision:"ask" with instructions to extend the spec

Replaces the old task-plan.json gate. The old model gated only Write to new files and
let Claude edit anything freely once a vague task description was logged. The new model:
produce a spec sheet with a per-file change table, get user approval, then Claude can
only touch files listed in the approved_files array. Anything else requires a new spec.

See workspace/consult-spec-sheet-approval-2026-06-24/plan.md for full design rationale.
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

GATED_TOOLS = {"Write", "Edit", "MultiEdit"}

EXEMPT_FRAGMENTS = [
    "/workspace/", "\\workspace\\",
    "/state/",     "\\state\\",
    "/.claudeboost/", "\\.claudeboost\\",
    "/plans/",     "\\plans\\",
    "/docs/",      "\\docs\\",
]


def read_json(path: str | os.PathLike, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def normalize(path: str) -> str:
    """Normalize to forward slashes and lowercase for comparison."""
    return path.replace("\\", "/").lower()


def file_in_spec(file_path: str, approved_files: list[str]) -> bool:
    """
    Check whether file_path matches any approved entry.
    Approved entries are relative paths like 'scripts/foo.py'.
    We check whether the normalized path ends with the entry (with a
    separator before it) to handle absolute incoming paths gracefully.
    """
    norm = normalize(file_path)
    for entry in approved_files:
        norm_entry = normalize(entry.strip("/\\"))
        if norm == norm_entry or norm.endswith("/" + norm_entry):
            return True
    return False


def _str_field(source, key: str) -> str:
    """A string field read out of an untrusted payload object, or "" if it isn't one.

    Stdin is a system boundary. The containing object can be null or a string
    rather than a dict, and the field itself a number or a list rather than a
    string; each of those reaches .replace() or Path() and raises. Reading them
    all as "" routes them to the same path as a genuinely absent field.
    Borrowed from clean-rag/hooks/research-gate.py:87-100.
    """
    value = source.get(key) if isinstance(source, dict) else None
    return value if isinstance(value, str) else ""


def get_file_path(tool_input: dict) -> str:
    """Extract the target file path, normalized to forward slashes.

    Edit, Write and MultiEdit all carry exactly one top-level "file_path", so
    there is nothing to branch on. MultiEdit's "edits" items hold only
    old_string/new_string/replace_all, and its schema sets
    additionalProperties:false, so a per-edit "file_path" cannot arrive.
    Reading one yielded no path at all, which skipped this gate for every
    MultiEdit call.

    Forward slashes matter here: is_exempt() compares against EXEMPT_FRAGMENTS
    after mapping them to "/", so a Windows path must be mapped too.
    """
    fp = _str_field(tool_input, "file_path") or _str_field(tool_input, "path")
    return fp.replace("\\", "/")


def main() -> int:
    home = os.environ.get("CLAUDEBOOST_HOME") or os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..")
    )
    mode = read_json(Path(home) / "state" / "claudeboost-mode.json", {}).get("mode", "CONSULT")

    if mode == "AUTO":
        return 0

    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        payload = json.loads(raw) if raw else {}
    except Exception:
        payload = {}

    tool_name = payload.get("tool_name", "") or ""
    tool_input = payload.get("tool_input", {}) or {}

    if tool_name not in GATED_TOOLS:
        return 0

    file_path = get_file_path(tool_input)
    if not file_path:
        return 0

    if any(frag.replace("\\", "/") in file_path for frag in EXEMPT_FRAGMENTS):
        return 0

    # Load the approved spec sheet
    spec_path = Path(home) / "state" / "spec-sheet.json"
    if not spec_path.exists():
        print(json.dumps({
            "permissionDecision": "ask",
            "reason": (
                f"No spec sheet found at state/spec-sheet.json. "
                f"Before editing '{Path(file_path).name}', produce a spec sheet: "
                f"a high-level summary of what the task does, then a table listing every "
                f"file and the specific change planned. Wait for user approval, then write "
                f"state/spec-sheet.json with the approved_files list."
            )
        }))
        return 0

    spec = read_json(spec_path, {})
    approved_files = spec.get("approved_files", [])
    task = spec.get("task", "current task")

    if not file_in_spec(file_path, approved_files):
        print(json.dumps({
            "permissionDecision": "ask",
            "reason": (
                f"'{Path(file_path).name}' is not in the approved spec sheet for: {task}. "
                f"To change this file, extend the spec sheet with a new entry describing "
                f"the specific change, get user approval, then update state/spec-sheet.json "
                f"before proceeding."
            )
        }))
        return 0

    return 0  # File approved


if __name__ == "__main__":
    sys.exit(main())
