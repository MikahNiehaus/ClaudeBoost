#!/usr/bin/env python
"""Stop hook: force bad-cop, and good-cop when bad-cop finds something, to run
for code-changing turns, loop safe.

The test run (auto-test-gate) proves tests pass. It does not prove the tests
catch the bug. Verification is mandatory: after every code change, bad-cop
must run adversarial QA on the files first (new tests, logging, provable
failures). If it finds nothing real, it stamps VERIFIED itself, no separate
good-cop run needed to re-confirm a clean pass. If it finds something, good-cop
must fix what it found, check logging quality, test coverage, and code
correctness, then stamp the files with VERIFIED: lines. The only exception is
/ps (quick mode), which opts out of both research and verification.

This blocks the stop (exit 2) rather than only emitting a JSON nudge. Both
mechanisms are documented for Stop (code.claude.com/docs/en/hooks confirms
hookSpecificOutput.additionalContext works here too), but exit 2 is the one
proven all session in this exact repo: research-gate.py uses the identical
PreToolUse exit-2-plus-stderr pattern, and every research-agent spawn this
session happened because Claude read that stderr and acted on it unprompted.
One battle-tested mechanism beats two parallel ones for the same problem.

The block message tells Claude to spawn bad-cop then good-cop itself, in the
foreground, right now, no user confirmation needed. Hooks can't spawn agents
directly, they're not part of the conversation loop, so "automatic" here means
an instruction forceful enough that Claude acts on it immediately without
asking first, the same way it already does for research-gate.

good-cop's completion, or bad-cop's when it found nothing, fires a PostToolUse
hook (verifier-record.py) that writes a stamp (verifier_state.record_verifier)
naming the files it covered.
check_file_verified() on the next check will find that stamp and let the stop
proceed. If a file is edited again after being reviewed, its stamp is
invalidated and verification must run again.

high_stakes.scan_diff labels the change (auth, money, SQL, subprocess, concurrency)
so the block message can point at the sharpest risk. It is not the trigger: a
change with no high stakes surface still needs a stamp, because "green tests"
and "correct" are different questions everywhere, not only on those surfaces.

The block cap exists because Claude Code re-fires Stop after a block, and the
only loop guard, stop_hook_active, has a documented, reproducible bug where it
comes back false on a retry it should be true for (anthropics/claude-code#54360).
An uncapped block risks a real infinite loop if good-cop ever fails to
produce a parseable stamp. MAX_BLOCKS_PER_SESSION is a bounded last-resort
escape under a real check, the identical pattern auto-test-gate.py already
uses for the same reason. This differs from research-gate.py's edit gate on
purpose: that one is PreToolUse on a discretionary edit Claude can simply
choose not to attempt, so blocking it forever is safe. Stop is different,
Claude Code itself re-fires it, so an uncapped block here is a real risk.

Safety rules, in order:

  - stop_hook_active true means we are already inside a block we raised. Exit 0.
  - A /ps turn opts out entirely. Exit 0.
  - No code changed this turn means nothing to review. Allow.
  - If the tests are currently FAILING, allow: auto-test-gate owns that, and a
    reviewer on broken code is wasted. Verify only once the code runs.
  - Unverified files found: block (exit 2) up to MAX_BLOCKS_PER_SESSION times,
    telling Claude to spawn bad-cop then good-cop itself, right now, foreground.
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
from verifier_state import _record_path, check_file_verified  # noqa: E402

CLEAN_RAG_HOME = Path(os.environ.get("CLEAN_RAG_HOME") or Path(__file__).resolve().parent.parent)
STATE_DIR = CLEAN_RAG_HOME / "state"
BLOCK_DIR = STATE_DIR / "verifier-gate"
MAX_BLOCKS_PER_SESSION = 6
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

    Without this, the cap disables verification for the rest of the session
    the first time two blocks happen in a row, even if good-cop runs
    correctly on every file after that. The cap exists to stop a stuck loop
    (a good-cop that never produces a parseable stamp), not to silently
    give up on verification forever the moment two blocks occur anywhere in a
    long session. Resetting on a clean pass keeps the loop guard scoped to
    actual consecutive failures, never a permanent session wide disable.
    """
    f = BLOCK_DIR / f"{session_id or 'nosession'}.count"
    try:
        f.unlink(missing_ok=True)
    except Exception:
        pass


def _last_verifier_agent(session_id: str):
    """Return (agent, covers) for the most recent verifier stamp, or ('', []) if none.

    Drives the three-way block message routing:
      - ('', [])            → no verifier ran yet → spawn bad-cop
      - ('bad-cop', [])     → bad-cop found real bugs → spawn good-cop
      - ('good-cop', [...]) → good-cop stamped a fix → spawn bad-cop for re-check

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
    # risk so the block message can point at it. Any real code change needs a stamp.
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

    # The real check: has a good-cop stamp actually covered each changed
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

    last_agent, last_covers = _last_verifier_agent(session_id)

    # When good-cop just completed a fix cycle and stamped VERIFIED, reset the
    # consecutive-block cap before spawning bad-cop for the re-check. The cap
    # guards against a stuck loop (an agent that never produces a parseable stamp),
    # not against a healthy loop making real progress each round. Resetting here
    # keeps the cap scoped to consecutive failures within one round rather than
    # accumulated across rounds of a healthy bad-cop → good-cop → bad-cop cycle.
    if last_agent == "good-cop" and last_covers:
        _reset_block_count(session_id)

    if _block_count(session_id) >= MAX_BLOCKS_PER_SESSION:
        print(
            "[verifier-gate] Code change still unverified after "
            f"{MAX_BLOCKS_PER_SESSION} blocks this session. Not blocking again "
            "(anti loop, stop_hook_active is not fully reliable: "
            "anthropics/claude-code#54360). Fix this before you rely on it.",
            file=sys.stderr,
        )
        return 0

    _bump_block_count(session_id)

    if last_agent == "bad-cop" and not last_covers:
        print(
            "[verifier-gate] BLOCKED: bad-cop ran and found real bugs — "
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
    elif last_agent == "good-cop" and last_covers:
        print(
            "[verifier-gate] BLOCKED: good-cop stamped VERIFIED: but "
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
            "[verifier-gate] BLOCKED: these changed files have no valid verifier "
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
            "That final bad-cop VERIFIED: line is what clears this gate. "
            "Fix any Critical or High bad-cop returns, then finish.\n\n"
            "If this really was trivial and needed no reviewer, that was a /ps "
            "turn's call to make up front, not this one's.",
            file=sys.stderr,
        )
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
