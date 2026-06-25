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


def get_file_paths(tool_name: str, tool_input: dict) -> list[str]:
    """Extract target file path(s) from the tool input."""
    if tool_name == "MultiEdit":
        edits = tool_input.get("edits") or []
        return [
            e.get("file_path", "").replace("\\", "/")
            for e in edits
            if e.get("file_path")
        ]
    fp = (tool_input.get("file_path") or tool_input.get("path") or "").replace("\\", "/")
    return [fp] if fp else []


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

    file_paths = get_file_paths(tool_name, tool_input)
    if not file_paths:
        return 0

    def is_exempt(fp: str) -> bool:
        return any(frag.replace("\\", "/") in fp for frag in EXEMPT_FRAGMENTS)

    if all(is_exempt(fp) for fp in file_paths):
        return 0

    # Load the approved spec sheet
    spec_path = Path(home) / "state" / "spec-sheet.json"
    if not spec_path.exists():
        first = Path(file_paths[0]).name
        print(json.dumps({
            "permissionDecision": "ask",
            "reason": (
                f"No spec sheet found at state/spec-sheet.json. "
                f"Before editing '{first}', produce a spec sheet: "
                f"a high-level summary of what the task does, then a table listing every "
                f"file and the specific change planned. Wait for user approval, then write "
                f"state/spec-sheet.json with the approved_files list."
            )
        }))
        return 0

    spec = read_json(spec_path, {})
    approved_files = spec.get("approved_files", [])
    task = spec.get("task", "current task")

    # Block if any target that is not exempt is also not in the approved list
    for fp in file_paths:
        if is_exempt(fp):
            continue
        if not file_in_spec(fp, approved_files):
            print(json.dumps({
                "permissionDecision": "ask",
                "reason": (
                    f"'{Path(fp).name}' is not in the approved spec sheet for: {task}. "
                    f"To change this file, extend the spec sheet with a new entry describing "
                    f"the specific change, get user approval, then update state/spec-sheet.json "
                    f"before proceeding."
                )
            }))
            return 0

    return 0  # All files approved


if __name__ == "__main__":
    sys.exit(main())
