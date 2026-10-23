"""Boundaries of the 3.14 approval: what it must not unlock, what it must not let be forged."""
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]


def _run(home, script, payload):
    env = {"USERPROFILE": str(home), "HOME": str(home), "SYSTEMROOT": "C:\\Windows"}
    return subprocess.run([sys.executable, "-I", str(SCRIPTS / script)],
                          input=json.dumps(payload), capture_output=True, text=True,
                          env=env).returncode


def _guard(home, command, sid="s1"):
    return _run(home, "bash-guard.py", {"hook_event_name": "PreToolUse", "session_id": sid,
                                        "tool_input": {"command": command}})


def _approve(home, sid="s1"):
    _run(home, "github-write-gate.py",
         {"hook_event_name": "UserPromptSubmit", "session_id": sid, "prompt": "3.14"})


# A public gist exposes the content to everyone and only the web UI can retract it.
@pytest.mark.parametrize("cmd", ["gh gist create --public f", "gh gist create -p f",
                                 "gh gist create --public=true f"])
def test_public_gist_stays_blocked_after_approval(tmp_path, cmd):
    _approve(tmp_path)
    assert _guard(tmp_path, cmd) == 2


def test_secret_gist_is_allowed_after_approval(tmp_path):
    _approve(tmp_path)
    assert _guard(tmp_path, "gh gist create f") == 0


# The model can write files, so approval must not be forgeable with a file write.
@pytest.mark.parametrize("path", ["~/.claude/state/github-write-approval.json",
                                  ".claude/state/github-write-approval.json"])
def test_approval_state_file_is_protected(path):
    spec = importlib.util.spec_from_file_location("bg_under_test", SCRIPTS / "bash-guard.py")
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    assert guard._is_protected_path(path)


@pytest.mark.parametrize("cmd", [
    "echo '{}' > ~/.claude/state/github-write-approval.json",
    "printf x | tee ~/.claude/state/github-write-approval.json",
    "cp /tmp/a ~/.claude/state/github-write-approval.json",
    "cd ~/.claude/state && echo x > github-write-approval.json",
    "echo x > ~/.claude/state/github-write-approva?.json",
    "python -c \"open('C:/Users/u/.claude/state/github-write-approval.json','w')\"",
])
def test_bash_write_to_approval_state_is_refused(tmp_path, cmd):
    assert _guard(tmp_path, cmd) == 2


_STATE = "/c/Users/u/.claude/state/"


@pytest.mark.parametrize("cmd", [
    "python -c \"open('~/.claude/state/github-write'+'-approval.json','w')\"",
    f"node -e \"require('fs').writeFileSync('{_STATE}github-write-'+'approval.json','x')\"",
    "python -c \"open('/tmp/.cla' '' 'ude/stat' + 'e/x','w')\"",
    f"printf x >| {_STATE}github-write-approval.json",
    f"printf x > {_STATE}github-write-approva\\l.json",
    "printf x > github-write-appro''val.json",
    f"curl -o {_STATE}github-write-approval.json http://localhost/x",
    f"curl --output {_STATE}github-write-approval.json http://localhost/x",
    f"curl --output={_STATE}github-write-approval.json http://localhost/x",
    f"curl -sSo {_STATE}github-write-approval.json http://localhost/x",
    f"curl -o {_STATE}github-write-approva?.json http://localhost/x",
    f"curl --output-dir {_STATE} -O http://localhost/github-write-approval.json",
    f"wget -O {_STATE}github-write-approval.json http://localhost/x",
    f"wget -P {_STATE} http://localhost/github-write-approval.json",
    f"cp /tmp/x/github-write-appr* {_STATE}",
    "cp /tmp/x/github-write-appr* /c/Users/u/.claude/state",
])
def test_approval_forge_spellings_are_refused(tmp_path, cmd):
    assert _guard(tmp_path, cmd) == 2


@pytest.mark.parametrize("cmd", [
    "rm *.json", "rm build/*.json", f"cat {_STATE}other.json",
    "python -c \"print('a' + 'b')\"", "curl -o /tmp/out.html http://localhost/x",
    "wget -qO- http://localhost/x", "rsync -avt scripts/ /tmp/backup",
    "echo x > C:\\Users\\u\\proj\\out.txt", "echo a | grep a",
])
def test_ordinary_commands_near_the_approval_rules_run(tmp_path, cmd):
    assert _guard(tmp_path, cmd) == 0


def test_file_tools_are_denied_on_approval_state():
    spec = importlib.util.spec_from_file_location("setup_under_test", SCRIPTS / "setup.py")
    setup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(setup)
    for tool in ("Edit", "Write"):
        assert f"{tool}(~/.claude/state/github-write-approval.json)" in setup._GIT_DENY


@pytest.mark.parametrize("cmd", ["gh gist create -wp f", "gh gist create --public=false f"])
def test_public_gist_spellings_stay_blocked(tmp_path, cmd):
    _approve(tmp_path)
    assert _guard(tmp_path, cmd) == 2


def test_hand_written_state_file_does_not_approve_other_session(tmp_path):
    state = tmp_path / ".claude" / "state"
    state.mkdir(parents=True)
    (state / "github-write-approval.json").write_text(
        json.dumps({"session_id": "other", "ts": time.time()}), encoding="utf-8")
    assert _guard(tmp_path, "git commit -m x") == 2
