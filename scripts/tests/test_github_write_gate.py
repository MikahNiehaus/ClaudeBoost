"""github-write-gate.py: 3.14 unlocks gated git/gh writes for one turn."""
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "github-write-gate.py"


def run(home, payload):
    # Scrubbed env: only HOME vars, nothing inherited from the developer shell.
    env = {"USERPROFILE": str(home), "HOME": str(home), "SYSTEMROOT": "C:\\Windows"}
    r = subprocess.run([sys.executable, "-I", str(SCRIPT)], input=json.dumps(payload),
                       capture_output=True, text=True, env=env)
    return r.returncode


def bash(cmd, sid="s1"):
    return {"hook_event_name": "PreToolUse", "session_id": sid,
            "tool_input": {"command": cmd}}


def prompt(text, sid="s1"):
    return {"hook_event_name": "UserPromptSubmit", "session_id": sid, "prompt": text}


GATED = ["git push origin main", "git commit -m x", "git add .", "git -C 'a b' push",
         "cd x && git push", "gh pr create --title x", "gh issue close 3",
         "gh repo create foo --private", "git remote add origin u"]


@pytest.mark.parametrize("cmd", GATED)
def test_blocked_without_token(tmp_path, cmd):
    assert run(tmp_path, bash(cmd)) == 2


@pytest.mark.parametrize("cmd", ["git status", "git log", "gh pr view 1", "echo git push"])
def test_reads_pass(tmp_path, cmd):
    assert run(tmp_path, bash(cmd)) == 0


def test_token_unlocks_same_session_only(tmp_path):
    run(tmp_path, prompt(" 3.14 "))
    assert run(tmp_path, bash("git push")) == 0
    assert run(tmp_path, bash("git push", sid="other")) == 2


def test_next_prompt_revokes(tmp_path):
    run(tmp_path, prompt("3.14"))
    run(tmp_path, prompt("ok now do more"))
    assert run(tmp_path, bash("git push")) == 2


def test_token_inside_sentence_does_not_count(tmp_path):
    run(tmp_path, prompt("push it, 3.14"))
    assert run(tmp_path, bash("git push")) == 2


@pytest.mark.parametrize("sid", ["", None])
def test_missing_session_id_never_approves(tmp_path, sid):
    run(tmp_path, prompt("3.14", sid=sid))
    assert run(tmp_path, bash("git push", sid=sid)) == 2


def test_future_timestamp_does_not_approve(tmp_path):
    state = tmp_path / ".claude" / "state"
    state.mkdir(parents=True)
    (state / "github-write-approval.json").write_text(
        json.dumps({"session_id": "s1", "ts": time.time() + 10**9}), encoding="utf-8")
    assert run(tmp_path, bash("git push")) == 2


def test_unwritable_state_dir_does_not_crash_or_approve(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "state").write_text("not a dir", encoding="utf-8")
    assert run(tmp_path, prompt("3.14")) == 0
    assert run(tmp_path, bash("git push")) == 2
