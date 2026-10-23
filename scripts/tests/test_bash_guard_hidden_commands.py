"""A command bash would run must reach the verb gate, whatever quoting hides it from a naive scanner."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

GUARD = Path(__file__).resolve().parents[1] / "bash-guard.py"
G = "gi" + "t "


def _guard(home, command):
    env = {"USERPROFILE": str(home), "HOME": str(home), "SYSTEMROOT": "C:\\Windows"}
    return subprocess.run([sys.executable, "-I", str(GUARD)], env=env, capture_output=True,
                          text=True, input=json.dumps({"session_id": "s1",
                          "tool_input": {"command": command}})).returncode


@pytest.mark.parametrize("cmd", [
    "echo $'a\\'b'; " + G + "commit -m x",
    "echo $'a\\'b' && " + G + "reset --hard",
    "echo `echo \\`" + G + "commit -m x\\``",
    "echo $(echo 'a)b'); " + G + "commit -m x",
    "echo $(echo \"a)b\"); " + G + "commit -m x",
])
def test_command_after_tricky_quoting_is_still_gated(tmp_path, cmd):
    assert _guard(tmp_path, cmd) == 2


def test_escaped_quote_does_not_merge_words_hiding_a_write_flag(tmp_path):
    assert _guard(tmp_path, G + "diff --src-prefix=a\\' --output=zz --src-prefix=b\\'") == 2
