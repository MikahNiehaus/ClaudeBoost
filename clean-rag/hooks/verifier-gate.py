#!/usr/bin/env python
"""Stop hook: nudge toward bad-cop, and good-cop when bad-cop finds something,
on code-changing turns. It never refuses a stop.

Nothing here forces anything, by decision. Research and verification are
process steps, and the measured tradeoff (arxiv 2604.11088) is that a hard
boundary earns its friction for something irreversible, not for ceremony. This
repo has also run the blocking version twice and reverted it twice: the research
gate's per-turn block was removed as too disruptive, and verify-gate-cmd.py
records a forced-response hook that stalled batch work. The ordering still
matters and is still stated: bad-cop first, good-cop only when bad-cop found
something real, then bad-cop again on the fix. That is advice now, not a refusal.

The test run (auto-test-gate) proves the tests pass. It does not prove the tests
catch the bug, which is the whole reason a reviewer is worth spawning at all.
So the advice this hook gives, after a code change: send bad-cop at the changed
files first, with adversarial tests and real execution output. If bad-cop finds
nothing real it stamps VERIFIED: itself and the pass is done, no separate
good-cop run to re-confirm a clean pass. If it finds something, good-cop fixes
what was found, checks logging quality, test coverage and correctness, then
stamps the files it covered, and bad-cop re-checks the fix. The loop ends when
bad-cop stamps VERIFIED: on a clean pass. A /ps turn skips all of it, the same
way it skips research.

The nudge goes to stderr, which the model reads. Hooks cannot spawn agents
directly, so the message names who to spawn and what to hand them.

good-cop's completion, or bad-cop's when it found nothing, fires a PostToolUse
hook (verifier-record.py) that writes a stamp (verifier_state.record_verifier)
naming the files it covered. check_file_verified() finds that stamp on the next
Stop and those files go quiet. If a file is edited again after being reviewed,
its stamp is invalidated and the file reads as unverified again.

high_stakes.scan_diff labels the change (auth, money, SQL, subprocess, concurrency)
so the nudge can point at the sharpest risk. It is not the trigger: a change with
no high stakes surface is still worth a reviewer, because "green tests" and
"correct" are different questions everywhere, not only on those surfaces.

MAX_BLOCKS_PER_SESSION keeps its old name and no longer caps a block, since
there is none to cap. It caps how many times the nudge repeats in one session. A
reminder that prints on every Stop stops being read, so one ignored that many
times has already failed and goes quiet instead of adding noise.

Rules, in order:

  - stop_hook_active true means this Stop is a re-fire after a previous Stop
    hook ran. Exit 0 immediately and say nothing.
  - A /ps turn opts out entirely. Exit 0.
  - No code changed this turn means nothing to review. Exit 0.
  - If the tests are currently FAILING, exit 0: auto-test-gate owns that, and a
    reviewer on broken code is wasted. Review once the code runs.
  - Unverified files found: name them on stderr, up to MAX_BLOCKS_PER_SESSION
    times, saying who to spawn and what to hand them. Exit 0.
  - Any error exits 0 (fail open). A broken hook must never trap the session.

Exit codes: 0 always. Nothing here blocks.
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
from verifier_state import _record_path, check_file_verified  # noqa: E402

CLEAN_RAG_HOME = Path(os.environ.get("CLEAN_RAG_HOME") or Path(__file__).resolve().parent.parent)
STATE_DIR = CLEAN_RAG_HOME / "state"
BLOCK_DIR = STATE_DIR / "verifier-gate"
MAX_BLOCKS_PER_SESSION = 6
RAG_PORT = int(os.environ.get("CLEAN_RAG_PORT", "8613"))

# Where the bad-cop → good-cop → bad-cop loop stands, from the newest stamp.
STAGE_NO_VERIFIER = "no-verifier-yet"
STAGE_BUGS_FOUND = "bad-cop-found-bugs"
STAGE_FIX_STAMPED = "good-cop-stamped-fix"

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


def _reset_block_count(session_id: str) -> None:
    """Clear the cap once verification actually succeeds.

    Without this, the cap silences the nudge for the rest of the session the
    first time two of them land in a row, even if good-cop runs correctly on
    every file after that. The cap exists to stop a stuck loop (a good-cop
    that never produces a parseable stamp), not to give up on asking for the
    rest of a long session the moment two nudges occur anywhere in it.
    Resetting on a clean pass keeps the loop guard scoped to actual
    consecutive failures, never a permanent session wide silence.
    """
    f = BLOCK_DIR / f"{session_id or 'nosession'}.count"
    try:
        f.unlink(missing_ok=True)
    except Exception:
        pass


def _last_verifier_agent(session_id: str):
    """Return (agent, covers) for the most recent verifier stamp, or ('', []) if none.

    loop_stage() turns that pair into the three-way nudge message routing.

    Using the most recent stamp (not any stamp) avoids stale matches from earlier
    rounds: an old empty-covers bad-cop stamp no longer redirects to good-cop once
    the loop has already advanced past that round and good-cop has since stamped.
    """
    path = _record_path(session_id)
    if not path.exists():
        return "", []
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "", []
    stamps = record.get("stamps", [])
    if not isinstance(stamps, list) or not stamps:
        return "", []
    last = stamps[-1]
    return last.get("agent", ""), last.get("covers") or []


def loop_stage(session_id: str) -> str:
    """Which round of the bad-cop → good-cop → bad-cop loop this session is in.

    One place decides it, so the nudge message and the counter reset cannot
    disagree, and a test can assert the routing without restating the condition.
    """
    agent, covers = _last_verifier_agent(session_id)
    if agent == "bad-cop" and not covers:
        return STAGE_BUGS_FOUND
    if agent == "good-cop" and covers:
        return STAGE_FIX_STAMPED
    return STAGE_NO_VERIFIER


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


def _security_scan(root, files):
    """Call /security-scan for the changed files. Returns findings or []."""
    try:
        payload = json.dumps({"project_path": root, "changed_files": files}).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{RAG_PORT}/security-scan",
            data=payload, headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        return [f for f in result.get("findings", [])
                if f.get("severity", "").lower() in ("critical", "high")]
    except Exception:
        return []


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
    # risk so the nudge can point at it. Any real code change is worth a reviewer.
    hits = high_stakes.scan_diff(added, paths)

    # Opt-in: run security scanners on high stakes files for extra evidence.
    # Gated by env var so it only runs when the user explicitly enables it.
    if hits and os.environ.get("CLEAN_RAG_SECURITY_SCAN") == "1":
        sec_findings = _security_scan(diff_root, [p for p in paths])
        if sec_findings:
            hits.setdefault("security-scan", [])
            for f in sec_findings[:5]:
                hits["security-scan"].append(
                    f"{f.get('severity', 'low').upper()}: {f.get('title', '?')} "
                    f"({f.get('file', '?')}:{f.get('line', 0)})"
                )

    # A reviewer on failing code is wasted; the test gate owns that case.
    if _tests_failing(diff_root):
        return 0

    # The real check: has a verifier stamp actually covered each changed file
    # (good-cop's fix, or bad-cop finding nothing to fix), and not been
    # invalidated by a later edit? Unlike the counter, this reflects whether
    # verification happened, not how many times we asked for it.
    # diff_root, not root: the fallback resolves paths against the repo the
    # edited files actually live in, which can differ from cwd's repo.
    unverified = []
    for p in sorted(set(paths)):
        abs_path = str((Path(diff_root) / p).resolve())
        ok, reason = check_file_verified(session_id, abs_path)
        if not ok:
            unverified.append((p, reason))

    if not unverified:
        _reset_block_count(session_id)
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

    stage = loop_stage(session_id)

    # When good-cop just completed a fix cycle and stamped VERIFIED, reset the
    # consecutive-nudge cap before bad-cop is asked for the re-check. The cap
    # guards against a stuck loop (an agent that never produces a parseable stamp),
    # not against a healthy loop making real progress each round. Resetting here
    # keeps the cap scoped to consecutive failures within one round rather than
    # accumulated across rounds of a healthy bad-cop → good-cop → bad-cop cycle.
    if stage == STAGE_FIX_STAMPED:
        _reset_block_count(session_id)

    # The counter no longer caps a block, since nothing here blocks. It caps how
    # often the nudge repeats. A reminder printed on every Stop of a long session
    # stops being read (the alert fatigue result: most alerts go uninvestigated
    # once they are constant), so a nudge that has been ignored this many times
    # has already failed and should get out of the way.
    if _block_count(session_id) >= MAX_BLOCKS_PER_SESSION:
        print(
            "[verifier-gate] Code change still unverified after "
            f"{MAX_BLOCKS_PER_SESSION} nudges this session. Staying quiet from "
            "here so the reminder does not become noise. Verification is still "
            "the thing that catches what green tests do not.",
            file=sys.stderr,
        )
        return 0

    _bump_block_count(session_id)

    if stage == STAGE_BUGS_FOUND:
        print(
            "[verifier-gate] NUDGE: bad-cop ran and found real bugs — "
            f"these files still have no valid verifier stamp: {files}\n\n"
            "Spawn good-cop NOW (Opus model, fresh context, foreground, "
            "run_in_background: false — never backgrounded). "
            "Give good-cop four things only: (1) the requirements/ticket "
            "context, (2) the correctness properties, (3) the diff, "
            "(4) bad-cop's actual findings with their real execution output. "
            "Not your reasoning for the change. good-cop researches the "
            "correct fix, applies it, reruns bad-cop's new tests plus the "
            "existing suite until everything is green, then stamps VERIFIED: "
            "naming every file it covered.\n\n"
            "After good-cop stamps VERIFIED:, spawn bad-cop again (fresh "
            "context, foreground, same three things plus the updated diff) "
            "for a final re-check on the fix. If bad-cop finds nothing on "
            "that re-check, it stamps VERIFIED: itself and the loop ends. "
            "If it finds more issues, spawn good-cop again. The loop "
            "(bad-cop → good-cop → bad-cop) continues until bad-cop stamps "
            "VERIFIED: itself — that is the only terminal condition.",
            file=sys.stderr,
        )
    elif stage == STAGE_FIX_STAMPED:
        print(
            "[verifier-gate] NUDGE: good-cop stamped VERIFIED: but "
            f"these files still have no valid verifier stamp: {files}\n\n"
            "Spawn bad-cop again (Sonnet model, fresh context, foreground, "
            "run_in_background: false) for a re-check on good-cop's fix. "
            "Give it three things only: (1) the requirements/ticket context, "
            "(2) the correctness properties, (3) the diff including good-cop's "
            "changes. Not your reasoning.\n\n"
            "If bad-cop finds nothing on this re-check, it stamps VERIFIED: "
            "itself and the loop ends. If it finds more issues, spawn "
            "good-cop again with those findings. The loop continues until "
            "bad-cop stamps VERIFIED: itself.",
            file=sys.stderr,
        )
    else:
        print(
            "[verifier-gate] NUDGE: these changed files have no valid verifier "
            f"stamp: {files}\n\n"
            f"This touches {surface}.\n"
            f"{evidence}\n\n"
            "Spawn bad-cop first (a fresh context, NOT the research agent) on "
            "those files, right now, in the foreground: run_in_background: "
            "false, never true. A backgrounded completion arrives later as a "
            "TaskNotificationMessage, not a tool result, so the verifier record "
            "hook never fires for it and the stamp never lands.\n\n"
            "Give bad-cop three things and only three: (1) the "
            "requirements/ticket context if any, (2) the correctness properties "
            "this change must satisfy, (3) the actual diff. Do NOT give it your "
            "reasoning for the change, that is what biases a reviewer into "
            "agreeing with it. bad-cop writes adversarial tests, runs the code, "
            "adds logging, and reports the real failures it finds.\n\n"
            "If bad-cop finds nothing real, it stamps VERIFIED: itself and "
            "the loop ends — no separate good-cop run needed. Only if it finds "
            "something: spawn good-cop next (Opus, fresh context, foreground, "
            "four things: requirements, correctness properties, diff, and "
            "bad-cop's findings). good-cop fixes what was found and gets every "
            "test green, then stamps VERIFIED:. After good-cop stamps, spawn "
            "bad-cop again for a final re-check. The loop (bad-cop → good-cop "
            "→ bad-cop) continues until bad-cop stamps VERIFIED: itself — "
            "that is the only terminal condition, not good-cop claiming done.\n\n"
            "Fix any Critical or High bad-cop returns, then finish.\n\n"
            "For a quick check that you did what you said you did, rather than "
            "a full adversarial pass, dispatch quick-cop instead. It is not a "
            "verifier, it stamps nothing, and it never satisfies this nudge.",
            file=sys.stderr,
        )
    # Nudge, not block: name the unverified files and let the turn end.
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
