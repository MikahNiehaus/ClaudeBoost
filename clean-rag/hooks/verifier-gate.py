#!/usr/bin/env python
"""Stop hook: require a fresh verifier stamp after a code-changing turn, loop safe.

The test run (auto-test-gate) proves the tests pass. It does not prove the tests
catch the bug. So when code changed, this requires one fresh reviewer to have
actually run and stamped the changed files before the turn can end. The user's
rule: always verify a real code change, the one exception being a turn the human
marked /ps (quick mode), which opts out of research and verification alike.

This used to be a counter: block up to twice, print a nudge, then give up for
the rest of the session regardless of whether verifier-agent ever ran. That
counted nudges printed, not verification done. It's now a real check, the same
shape research-gate.py already uses: verifier-agent's completion writes a stamp
(verifier-record.py -> verifier_state.record_verifier) naming the files it
covered, and this gate checks that stamp per file (verifier_state.check_file_verified)
before allowing the stop, invalidated if a file was edited again after being
reviewed.

The cap stays, unlike research-gate.py's edit gate, and that's a deliberate
difference, not a leftover. research-gate.py is PreToolUse on a discretionary
edit: the model can simply not attempt the edit, so blocking it indefinitely is
safe, there's no forced retry. This is a Stop hook: Claude Code itself re-fires
the Stop event after a block, and the only loop guard is stop_hook_active, which
has a documented, reproducible bug where it comes back false on a retry it
should be true for (anthropics/claude-code#54360). An uncapped block here risks
a real infinite loop if verifier-agent ever fails to produce a parseable stamp.
So the cap is now what auto-test-gate.py already does for the same reason: a
bounded last-resort escape under a REAL check, not the check itself.

high_stakes.scan_diff still runs, but only to LABEL the change (auth, money, SQL,
subprocess, concurrency) so the block message can point at the sharpest risk. It
is not the trigger: a change with no high stakes surface still needs a stamp,
because "green tests" and "correct" are different questions everywhere, not only
on those surfaces.

Safety rules, in order:

  - stop_hook_active true means we are already inside a block we raised. Exit 0.
  - A /ps turn opts out entirely. Exit 0.
  - No code changed this turn means nothing to review. Allow.
  - If the tests are currently FAILING, allow: auto-test-gate owns that, and a
    reviewer on broken code is wasted. Verify only once the code runs.
  - Block on any changed file with no valid stamp, up to MAX_BLOCKS_PER_SESSION
    times, then allow as the last-resort loop breaker.
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
from manifest_files import is_gated_file  # noqa: E402
from research_state import is_quick_turn  # noqa: E402
from turn_edits import edited_code_files, git_root as _git_root_of  # noqa: E402
from verifier_state import check_file_verified  # noqa: E402

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
                is_code = is_gated_file(f, CODE_EXTENSIONS)
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
    diff_root = root
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
        diff_root = er
        added, paths = _diff(er, files=edited)
        if not added and not paths:
            return 0

    # scan_diff no longer decides whether to review, it only labels the sharpest
    # risk so the block message can point at it. Any real code change needs a stamp.
    hits = high_stakes.scan_diff(added, paths)

    # A reviewer on failing code is wasted; the test gate owns that case.
    if _tests_failing(diff_root):
        return 0

    # The real check: has a verifier-agent stamp actually covered each changed
    # file, and not been invalidated by a later edit? Unlike the old counter,
    # this reflects whether verification happened, not how many times we asked.
    # diff_root, not root: the fallback resolves paths against the repo the
    # edited files actually live in, which can differ from cwd's repo.
    unverified = []
    for p in sorted(set(paths)):
        abs_path = str((Path(diff_root) / p).resolve())
        ok, reason = check_file_verified(session_id, abs_path)
        if not ok:
            unverified.append((p, reason))

    if not unverified:
        return 0

    if _block_count(session_id) >= MAX_BLOCKS_PER_SESSION:
        print(
            "[verifier-gate] Code change still unverified after "
            f"{MAX_BLOCKS_PER_SESSION} blocks this session. Not blocking again "
            "(anti loop, stop_hook_active is not fully reliable: "
            "anthropics/claude-code#54360). Fix this before you rely on it.",
            file=sys.stderr,
        )
        return 0

    files = ", ".join(f"{p} ({reason})" for p, reason in unverified)
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
        "[verifier-gate] BLOCKED: these changed files have no valid verifier "
        f"stamp: {files}\n\n"
        f"This touches {surface}.\n"
        f"{evidence}\n\n"
        "Spawn verifier-agent (a fresh context, NOT the research agent) on those "
        "files. Give it three things and only three: the requirements, the "
        "correctness properties this change must satisfy, and the diff. Do NOT give "
        "it your reasoning for the change, that is what biases a reviewer into "
        "agreeing with it. Its report MUST end with a VERIFIED: line naming every "
        "file it covered, the same way research-agent's COVERS: line works, or this "
        "gate has nothing to check and stays blocked. Fix any Critical or High it "
        "returns, then finish.\n\n"
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
