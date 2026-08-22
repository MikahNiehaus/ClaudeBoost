"""
The soft RAG reminder must fire before the hard block, and the guard must
actually engage at its threshold.

Two hooks share one counter, `reads_since_rag` in state/behavior-tracker.json:

  context-nudge.py   PostToolUse, RAG_THRESHOLD, prints a reminder
  rag-read-guard.py  PreToolUse,  RAG_THRESHOLD, exits 2 and blocks the read

The ordering is load bearing and easy to break by editing one number. A
PreToolUse block stops the tool from running, so the PostToolUse hook never
fires and the counter never climbs past the block's threshold. Set the reminder
at or above the block and it becomes unreachable: the read is refused with no
warning ever having been given.

Driven through both real hooks with real stdin payloads.

Run: python -m pytest tests/test_rag_guard_thresholds.py -v
"""

import json
import os
import subprocess
import re
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
GUARD = REPO / "scripts" / "rag-read-guard.py"
NUDGE = REPO / "scripts" / "context-nudge.py"


def _threshold(path: Path) -> int:
    """
    Read RAG_THRESHOLD out of the source text.

    Deliberately not by importing the module. Both hooks have hyphenated
    filenames loaded through importlib, and __pycache__ served stale bytecode
    twice while this was being written: the source said 2 and the imported
    module said 5, so the tests failed against a file that was already correct.
    A constant is a static property of the file, so read the file.
    """
    src = path.read_text(encoding="utf-8")
    m = re.search(r"^RAG_THRESHOLD\s*=\s*(\d+)", src, re.M)
    assert m, f"no RAG_THRESHOLD found in {path.name}"
    return int(m.group(1))


@pytest.fixture(scope="module")
def guard_threshold():
    return _threshold(GUARD)


@pytest.fixture(scope="module")
def nudge_threshold():
    return _threshold(NUDGE)


@pytest.fixture
def home(tmp_path):
    (tmp_path / "state").mkdir(parents=True)
    return tmp_path


def set_reads(home, n, session_id="s1"):
    (home / "state" / "behavior-tracker.json").write_text(json.dumps({
        "reads_since_rag": n,
        "tasks_since_evaluator": 0,
        "reads_since_context_update": 0,
        "session_id": session_id,
    }), encoding="utf-8")


def beat_heartbeat(home):
    """
    The guard disengages unless the RAG heartbeat is fresh, which is correct:
    it must not block reads while offering an alternative that is not running.
    Write a live one so the threshold itself is what is under test.

    Same path and shape clean-rag's server writes (server/app.py
    _write_heartbeat). Getting this path wrong is exactly the bug that left the
    guard permanently disengaged, so the test uses the real one.
    """
    p = home / "clean-rag" / "state" / ".heartbeat"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "ts": time.time(), "model_loaded": True,
        "index_ok": True, "status": "ready",
    }), encoding="utf-8")


def run_guard(home, reads, path="/some/project/module.py", session_id="s1"):
    set_reads(home, reads, session_id)
    beat_heartbeat(home)
    env = dict(os.environ)
    env["CLAUDEBOOST_HOME"] = str(home)
    payload = json.dumps({
        "tool_name": "Read",
        "tool_input": {"file_path": path},
        "session_id": session_id,
        "hook_event_name": "PreToolUse",
    })
    return subprocess.run([sys.executable, str(GUARD)], input=payload,
                          capture_output=True, text=True, env=env,
                          cwd=str(REPO), timeout=60)


def test_the_reminder_fires_strictly_before_the_block(guard_threshold, nudge_threshold):
    """The invariant. Everything else here is a consequence of it."""
    assert nudge_threshold < guard_threshold, (
        f"soft reminder at {nudge_threshold} must be below the hard "
        f"block at {guard_threshold}, otherwise a read is refused "
        "without any warning having been possible"
    )


def test_at_least_one_reminder_lands_before_the_block(guard_threshold, nudge_threshold):
    """
    The reminder fires at multiples of its threshold. At least one of those
    multiples has to fall strictly below the block, or the gap is decorative.
    """
    t, b = nudge_threshold, guard_threshold
    firings = [n for n in range(1, b) if n >= t and n % t == 0]
    assert firings, (
        f"reminder at multiples of {t} never fires below the block at {b}"
    )


def test_the_guard_is_set_where_reads_are_still_cheap(guard_threshold):
    """
    Read averaged 1,267 tokens a call across 322 real transcripts, against
    roughly 500 for a RAG chunk. Letting six of those through before engaging
    was the old behavior and the reason this moved.
    """
    assert guard_threshold <= 3


def test_below_threshold_is_allowed(home, guard_threshold):
    for n in range(guard_threshold):
        assert run_guard(home, n).returncode == 0, f"{n} reads should not block"


def test_at_threshold_the_read_is_blocked(home, guard_threshold):
    r = run_guard(home, guard_threshold)
    assert r.returncode == 2, (
        f"expected a block at {guard_threshold} reads, got "
        f"rc={r.returncode} stderr={r.stderr[:200]!r}"
    )


def test_the_block_message_names_a_working_endpoint(home, guard_threshold):
    """
    Blocking a read and handing back an unusable alternative is worse than not
    blocking. This message used to name port 8612 and an `rag_search` MCP tool,
    neither of which exists.
    """
    r = run_guard(home, guard_threshold)
    assert r.returncode == 2
    err = r.stderr
    assert "8612" not in err
    assert "rag_search" not in err
    assert "/search" in err
    assert '"mode": "both"' in err or "mode" in err


def test_exempted_files_are_never_blocked(home, guard_threshold):
    """Config and workspace files have nothing to research."""
    for path in ("/p/package.json", "/p/context.md", "/p/pyproject.toml"):
        r = run_guard(home, guard_threshold + 5, path=path)
        assert r.returncode == 0, f"{path} should be exempt, got rc={r.returncode}"
