#!/usr/bin/env python
"""Stop hook: the execution feedback loop, bounded and loop safe.

When code changed this turn, run the project's tests. If they really fail, block
the stop once and hand the model the REAL failure text (assertion diff, stack
trace) so it fixes from actual output, not from a vague "it failed". Research
(arXiv 2404.10100, 2304.05128, LDB 2402.16906) shows that is the single highest
leverage lift for a weak model.

Safety is the whole point here, because a looping Stop hook has burned this user
before. The rules, in order:

  - stop_hook_active true means Claude is already responding to a previous block
    from this hook. Exit 0 immediately, do nothing. This is the anti loop guard.
  - Block at most twice per session, then always allow. A counter file per
    session under state/. Bounded, so it can never loop.
  - Never block when there is nothing to run, the runner is not installed, or the
    failure looks like an environment problem (missing binary, connection
    refused) rather than a real test failure. When unsure, allow. A gate that
    blocks on something the model cannot fix is the failure mode to avoid.
  - Never block on a turn where no code file changed.
  - Any error exits 0 (fail open). A broken gate must not trap the session.

Exit codes: 0 allows the stop, 2 blocks it and shows stderr to the model.
"""

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from turn_edits import edited_code_files, git_root as _git_root_of  # noqa: E402

CLEAN_RAG_HOME = Path(os.environ.get("CLEAN_RAG_HOME") or Path(__file__).resolve().parent.parent)
STATE_DIR = CLEAN_RAG_HOME / "state"
BLOCK_DIR = STATE_DIR / "auto-test-gate"
MAX_BLOCKS_PER_SESSION = 2
RAG_PORT = int(os.environ.get("CLEAN_RAG_PORT", "8613"))

# Same set the research gate uses. Only a real code change makes the gate fire.
CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".java", ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".scala",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".m", ".mm",
    ".sh", ".bash", ".ps1", ".sql", ".vue", ".svelte",
}

# If the failure text carries one of these, it is an environment problem the model
# cannot fix by editing code, so we allow rather than block. Erring toward allow is
# deliberate: blocking on an unfixable failure is the exact trap to avoid.
ENV_MARKERS = (
    "is not recognized",          # windows cmd: 'npm' is not recognized
    "command not found",          # posix shell
    "no module named",            # python import, usually a missing dep
    "modulenotfounderror",
    "cannot find module",         # node
    "err_module_not_found",
    "could not determine executable",  # npx with the package absent
    "econnrefused",
    "connection refused",
    "eaddrinuse",
)


def _git_root(cwd: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd, capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    root = proc.stdout.strip()
    return root or None


def _code_changed(root: str) -> bool:
    """True if git shows an uncommitted change to a code file under root."""
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root, capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return False
    if proc.returncode != 0:
        return False
    for line in proc.stdout.splitlines():
        # Format: "XY path" or "XY old -> new" for renames. The path is after the
        # first space that follows the two status chars.
        entry = line[3:].strip() if len(line) > 3 else ""
        if " -> " in entry:
            entry = entry.split(" -> ", 1)[1]
        entry = entry.strip().strip('"')
        if not entry:
            continue
        if Path(entry).suffix.lower() in CODE_EXTENSIONS:
            return True
    return False


def _run_tests(project_path: str) -> dict | None:
    """Ask the clean-rag server to detect and run the project's tests."""
    try:
        payload = json.dumps({"project_path": project_path}).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{RAG_PORT}/run-tests",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        # The run itself is capped at 120s server side, so give it a little more.
        with urllib.request.urlopen(req, timeout=140) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        # Server down or unreachable. Nothing to enforce, allow.
        return None


def _block_count(session_id: str) -> int:
    f = BLOCK_DIR / f"{session_id or 'nosession'}.count"
    try:
        return int(f.read_text(encoding="utf-8").strip())
    except Exception:
        return 0


def _bump_block_count(session_id: str) -> bool:
    """Record one more block for this session. True if it actually persisted.

    The return value matters. If the count cannot be written (the state
    directory is unwritable, the disk is full, a scanner holds the file), then
    _block_count reads back 0 forever, MAX_BLOCKS_PER_SESSION is never reached,
    and blocking anyway would wedge the session shut permanently. That is the
    exact failure the cap exists to prevent, so the caller declines to block
    when the budget cannot be tracked.
    """
    f = BLOCK_DIR / f"{session_id or 'nosession'}.count"
    try:
        BLOCK_DIR.mkdir(parents=True, exist_ok=True)
        f.write_text(str(_block_count(session_id) + 1), encoding="utf-8")
        return True
    except Exception:
        return False


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return 0

    # Anti loop guard. If this stop is already a response to a block we raised,
    # never block again from here. Do nothing.
    if payload.get("stop_hook_active"):
        return 0

    cwd = payload.get("cwd") or os.getcwd()
    session_id = payload.get("session_id", "")

    root = _git_root(cwd)
    if not root or not _code_changed(root):
        # cwd based detection found nothing: the cwd is not a repo, or the edits
        # landed in a different repo than the cwd. Fall back to the files actually
        # edited this session and test the repo they live in.
        edited = edited_code_files(session_id)
        if not edited:
            return 0
        root = _git_root_of(edited[0]) or root
        if not root:
            return 0

    result = _run_tests(root)
    if not result:
        return 0

    # Nothing runnable, or the run couldn't produce a real pass/fail. Allow.
    if not result.get("has_tests"):
        return 0
    if result.get("passed") is not False:
        return 0
    # A run that never produced a real exit code (timeout, launch failure) is too
    # ambiguous to block on. Allow.
    if result.get("exit_code") is None:
        return 0

    failures = result.get("failures", "") or ""
    low = failures.lower()
    if any(marker in low for marker in ENV_MARKERS):
        # Environment problem, not a code bug. Allow.
        return 0

    if _block_count(session_id) >= MAX_BLOCKS_PER_SESSION:
        print(
            "[auto-test-gate] Tests still failing after "
            f"{MAX_BLOCKS_PER_SESSION} blocks this session. Not blocking again "
            "(anti loop). Fix the tests before you rely on this passing.",
            file=sys.stderr,
        )
        return 0

    if not _bump_block_count(session_id):
        # The budget could not be recorded, so the cap above can never fire and
        # every future Stop would block again on the same failure. An uncounted
        # block is an unbounded one, so this allows instead and says why.
        print(
            failures + "\n\n"
            "Tests are failing. Fix from the actual output above, then finish. "
            "Do not self review.\n\n"
            f"[auto-test-gate] Could not record the block budget under {BLOCK_DIR}, "
            "so the anti loop cap cannot work. Not blocking.",
            file=sys.stderr,
        )
        return 0

    print(
        failures + "\n\n"
        "Tests are failing. Fix from the actual output above, then finish. "
        "Do not self review.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Fail open, always. A crashing gate must never trap the session.
        sys.exit(0)
