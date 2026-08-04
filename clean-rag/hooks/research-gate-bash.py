#!/usr/bin/env python
"""PreToolUse gate on Bash: close the research gate's write via shell bypass.

research-gate.py covers Edit, Write, and MultiEdit. It does not see a code file
written by a shell command, so `echo ... > x.py`, `tee x.py`, `sed -i x.py`, and
`python -c "open('x.py','w')..."` all slip past it (Claude Code issue #29709).
This catches those high confidence vectors and holds them to the same rule: an
uncovered code file cannot be written, whatever tool does the writing.

Best effort by nature. Shell is not a regex language, so this reads the clear
write vectors, not every possible one. Two are handled elsewhere already: cat
heredocs and multiline `python -c` are blocked by the bash guard hook. cp and mv
are left out on purpose, copying a file is common and legitimate and the false
positives would outweigh the rare bypass. Anything it is unsure about, it allows.

Exit codes: 0 allows, 2 blocks and shows stderr.
"""

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from manifest_files import is_gated_file  # noqa: E402
from research_state import (  # noqa: E402
    check_file_researched,
    has_any_research_this_turn,
    is_quick_turn,
)

CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".java", ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".scala",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".m", ".mm",
    ".sh", ".bash", ".ps1", ".sql", ".vue", ".svelte",
}

EXEMPT_SEGMENTS = {
    "workspace", "state", "plans", "docs", "node_modules",
    ".claude", ".claudeboost", ".git", "__pycache__", "scratchpad",
}

# Removing a dependency is a destructive action on its own, whether or not it
# happens to also rewrite a manifest file through a shell redirect (most of the
# time it doesn't; the package manager edits the manifest internally). Real
# aliases, verified against each tool's own docs or source, not memorized:
# npm's rm/r/un/unlink, pnpm's rm/un, cargo's rm (built in since 1.66), and
# composer's rm/uninstall (confirmed straight from RemoveCommand.php).
DESTRUCTIVE_DEP_PATTERNS = [
    re.compile(r'\bpip3?\s+uninstall\b'),
    re.compile(r'\bnpm\s+(?:uninstall|unlink|remove|rm|r|un)(?=\s|$)'),
    re.compile(r'\byarn\s+remove\b'),
    re.compile(r'\bpnpm\s+(?:remove|rm|uninstall|un)(?=\s|$)'),
    re.compile(r'\bpoetry\s+remove\b'),
    re.compile(r'\bcargo\s+(?:remove|rm)\b'),
    re.compile(r'\bbundle\s+remove\b'),
    re.compile(r'\bgo\s+mod\s+edit\s+\S*-droprequire'),
    re.compile(r'\bgo\s+get\s+\S+@none\b'),
    re.compile(r'\bcomposer\s+(?:remove|rm|uninstall)\b'),
]


def is_destructive_dep_command(command: str) -> bool:
    return any(p.search(command) for p in DESTRUCTIVE_DEP_PATTERNS)


def write_targets(command: str) -> set:
    """Best effort set of code files this command would write."""
    targets = set()

    # `>` or `>>` redirection to a file. The lookbehind skips an error or other fd
    # redirect (`2>` through `9>`) and the `&` of `&>`, but still catches plain `>`
    # and explicit stdout `1>`, both of which are real writes.
    for m in re.finditer(r'(?<![2-9&>])>{1,2}\s*(["\']?)([^\s|&;<>"\']+)\1', command):
        targets.add(m.group(2))

    # tee, optionally appending.
    for m in re.finditer(r'\btee\b\s+(?:-a\s+)?(["\']?)([^\s|&;"\']+)\1', command):
        targets.add(m.group(2))

    # A python open() in a write or append mode.
    for m in re.finditer(r'open\(\s*["\']([^"\']+)["\']\s*,\s*["\'][^"\']*[wa]', command):
        targets.add(m.group(1))

    # sed in place edit: any token ending in a code extension when -i is present.
    if re.search(r'\bsed\b', command) and re.search(r'(?:^|\s)-i', command):
        for _q, tok in re.findall(r'(["\']?)([^\s|&;"\']+)\1', command):
            targets.add(tok)

    return {t for t in targets if t and is_gated_file(t, CODE_EXTENSIONS)}


def _is_exempt(target: str, cwd: str) -> bool:
    p = Path(target)
    if not p.is_absolute():
        p = Path(cwd) / target
    if {seg.lower() for seg in p.parts} & EXEMPT_SEGMENTS:
        return True
    temp = os.environ.get("TEMP") or os.environ.get("TMP")
    if temp:
        try:
            p.resolve().relative_to(Path(temp).resolve())
            return True
        except (ValueError, OSError):
            pass
    return False


def _resolve(target: str, cwd: str) -> str:
    """Absolute form of a shell target, so scope matching lines up with the Edit
    gate, which always sees an absolute path. A bare shell token would never suffix
    match a repo relative COVERS entry, which would false block a covered file."""
    p = Path(target)
    if not p.is_absolute():
        p = Path(cwd) / target
    return str(p)


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return 0

    if payload.get("tool_name") != "Bash":
        return 0
    if os.environ.get("CLEAN_RAG_RESEARCH_GATE") == "off":
        return 0

    command = payload.get("tool_input", {}).get("command", "")
    if not command:
        return 0

    cwd = payload.get("cwd") or os.getcwd()
    session_id = payload.get("session_id", "")

    # A /ps turn skips the gate, shell writes included.
    if is_quick_turn(session_id):
        return 0

    try:
        targets = write_targets(command)
    except Exception:
        return 0

    for target in sorted(targets):
        if _is_exempt(target, cwd):
            continue
        ok, reason = check_file_researched(session_id, _resolve(target, cwd))
        if not ok:
            print(
                f"NUDGE: {reason}.\n\n"
                f"This Bash command would write {target}, a code file.\n"
                "Consider spawning researcher/swiper first, or use /ps to skip.",
                file=sys.stderr,
            )
            # Nudge, not block.
            return 0

    # Removing a dependency this way never touches a file through a redirect, tee,
    # or sed the loop above would catch, the package manager edits the manifest
    # internally. There's no single file to scope research against here, so this
    # checks whether research ran at all this turn, not a specific COVERS entry.
    if is_destructive_dep_command(command) and not _is_exempt(cwd, cwd):
        ok, reason = has_any_research_this_turn(session_id)
        if not ok:
            print(
                f"NUDGE: {reason}.\n\n"
                "This command removes a dependency.\n"
                "Consider spawning researcher/swiper first, or use /ps to skip.",
                file=sys.stderr,
            )
            # Nudge, not block.
            return 0

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Fail open, always. A crashing gate must never trap the session.
        sys.exit(0)
