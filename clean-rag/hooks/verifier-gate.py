#!/usr/bin/env python
"""Stop hook: nudge a fresh verifier after a code-changing turn, bounded and loop safe.

The test run (auto-test-gate) proves the tests pass. It does not prove the tests
catch the bug. So when a turn changed code, this asks the main agent to spend one
fresh reviewer on it before finishing. The user's rule: always verify a real code
change, the one exception being a turn the human marked /ps (quick mode), which
opts out of research and verification alike.

high_stakes.scan_diff still runs, but only to LABEL the change (auth, money, SQL,
subprocess, concurrency) so the nudge can point at the sharpest risk. It is no
longer the trigger: a change with no high stakes surface still gets a general
correctness review, because "green tests" and "correct" are different questions
everywhere, not only on those surfaces.

A Stop hook cannot spawn a subagent itself, it can only hand text back to the main
agent, which then spawns one. So this blocks once with a reason telling the agent
to spawn verifier-agent. Same nudge shape as auto-test-gate.py, and the same hard
safety rules, because a looping Stop hook has burned this user before:

  - stop_hook_active true means we are already inside a block we raised. Exit 0.
  - A /ps turn opts out entirely. Exit 0.
  - Block at most twice per session, counter under state/. Bounded, cannot loop.
  - No code changed this turn means nothing to review. Allow.
  - If the tests are currently FAILING, allow: auto-test-gate owns that, and a
    reviewer on broken code is wasted. Verify only once the code runs.
  - Any error exits 0 (fail open). A broken gate must never trap the session.

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
import high_stakes  # noqa: E402
from research_state import is_quick_turn  # noqa: E402
from turn_edits import edited_code_files, git_root as _git_root_of  # noqa: E402

CLEAN_RAG_HOME = Path(os.environ.get("CLEAN_RAG_HOME") or Path(__file__).resolve().parent.parent)
STATE_DIR = CLEAN_RAG_HOME / "state"
BLOCK_DIR = STATE_DIR / "verifier-gate"
MAX_BLOCKS_PER_SESSION = 2
RAG_PORT = int(os.environ.get("CLEAN_RAG_PORT", "8613"))

CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".java", ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".scala",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".m", ".mm",
    ".sh", ".bash", ".ps1", ".sql", ".vue", ".svelte",
}


def _git_root(cwd: str):
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd, capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _diff(root: str, files=None):
    """Added code lines and changed code file paths, across staged and unstaged.

    If files is given, the diff is scoped to just those paths (relative to root),
    so the fallback looks at exactly what was edited this session rather than every
    uncommitted change in the repo.
    """
    pathspec = []
    for f in (files or []):
        try:
            pathspec.append(
                str(Path(f).resolve().relative_to(Path(root).resolve())).replace("\\", "/")
            )
        except ValueError:
            pass
    if files and not pathspec:
        return [], []  # the given files are not under this root

    added, paths = [], []
    for base in (["git", "diff"], ["git", "diff", "--staged"]):
        args = base + (["--", *pathspec] if pathspec else [])
        try:
            proc = subprocess.run(args, cwd=root, capture_output=True, text=True, timeout=15)
        except Exception:
            continue
        if proc.returncode != 0:
            continue
        is_code = False
        for line in proc.stdout.splitlines():
            if line.startswith("+++ b/"):
                f = line[6:].strip()
                is_code = Path(f).suffix.lower() in CODE_EXTENSIONS
                if is_code:
                    paths.append(f)
            elif line.startswith("+++"):
                is_code = False
            elif is_code and line.startswith("+") and not line.startswith("+++"):
                added.append(line[1:])
    return added, sorted(set(paths))


def _tests_failing(root: str) -> bool:
    """True only when the server ran real tests and they failed. Errs toward False."""
    try:
        payload = json.dumps({"project_path": root}).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{RAG_PORT}/run-tests",
            data=payload, headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=140) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return False  # server down or unreachable, do not claim failure
    return bool(result.get("has_tests")) and result.get("passed") is False


def _block_count(session_id: str) -> int:
    f = BLOCK_DIR / f"{session_id or 'nosession'}.count"
    try:
        return int(f.read_text(encoding="utf-8").strip())
    except Exception:
        return 0


def _bump_block_count(session_id: str) -> None:
    f = BLOCK_DIR / f"{session_id or 'nosession'}.count"
    try:
        BLOCK_DIR.mkdir(parents=True, exist_ok=True)
        f.write_text(str(_block_count(session_id) + 1), encoding="utf-8")
    except Exception:
        pass


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return 0

    if payload.get("stop_hook_active"):
        return 0

    cwd = payload.get("cwd") or os.getcwd()
    session_id = payload.get("session_id", "")

    # A /ps turn opts out of everything, the verifier included.
    if is_quick_turn(session_id):
        return 0

    root = _git_root(cwd)
    added, paths = ([], [])
    if root:
        added, paths = _diff(root)
    if not added and not paths:
        # cwd based detection found nothing: the cwd is not a repo, or the edits
        # landed elsewhere. Fall back to the files edited this session, diffed in
        # whatever repo they live in.
        edited = edited_code_files(session_id)
        if not edited:
            return 0
        er = _git_root_of(edited[0])
        if not er:
            return 0
        added, paths = _diff(er, files=edited)
        if not added and not paths:
            return 0

    # scan_diff no longer decides whether to review, it only labels the sharpest
    # risk so the nudge can point at it. Any real code change gets a reviewer.
    hits = high_stakes.scan_diff(added, paths)

    # A reviewer on failing code is wasted; the test gate owns that case.
    if _tests_failing(root):
        return 0

    if _block_count(session_id) >= MAX_BLOCKS_PER_SESSION:
        print(
            "[verifier-gate] Code change still unreviewed after "
            f"{MAX_BLOCKS_PER_SESSION} nudges this session. Not blocking again "
            "(anti loop).",
            file=sys.stderr,
        )
        return 0

    files = ", ".join(sorted({p for p in paths})) or "the changed files"
    if hits:
        surface = ("high stakes surfaces where a passing test does not prove the "
                   "property: " + ", ".join(sorted(hits)))
        evidence = "\n".join(
            f"  {cat}: {ex[0]}" for cat, ex in sorted(hits.items()) if ex
        )
    else:
        surface = "code this turn; a passing test is not proof the test catches the bug"
        evidence = ""

    _bump_block_count(session_id)
    print(
        "[verifier-gate] This change should go through a fresh reviewer before you "
        f"finish: {surface}.\n"
        f"Files: {files}\n"
        f"{evidence}\n\n"
        "Spawn verifier-agent (a fresh context, NOT the research agent) on those "
        "files. Give it three things and only three: the requirements, the "
        "correctness properties this change must satisfy, and the diff. Do NOT give "
        "it your reasoning for the change, that is what biases a reviewer into "
        "agreeing with it. It reports findings it can quote from the diff and a "
        "verdict. Fix any Critical or High it returns, then finish.\n\n"
        "If this really was trivial and needed no reviewer, that was a /ps turn's "
        "call to make up front, not this one's.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
