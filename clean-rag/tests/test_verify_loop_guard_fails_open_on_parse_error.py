"""verify-loop-git-guard.py exists to stop bad-cop/good-cop from committing
or pushing on their own (see its own module docstring: the 2026-08-25
incident this guard was written to prevent). It works by shlex.split()-ing
the raw command and looking for a blocked git subcommand among the tokens.

Both of its exception handlers -- the JSON payload parse and the
shlex.split() parse -- return 0 (allow) rather than refusing, which is the
wrong direction for a denylist: if the guard cannot see the command's
structure, it cannot know a blocked subcommand isn't in it, so "allow" is
exactly backwards. Contrast with clean-rag/hooks/research-agent-bash-guard.py,
which explicitly fails closed on both failure modes for the same reason.

The shlex failure is not a contrived edge case. An ordinary English
contraction inside a single-quoted -m message (a shape an LLM writes
constantly: "don't", "it's", "won't") ends the quoted string early and
leaves an unbalanced quote for the rest of the command, which is exactly
what trips shlex.split()'s "No closing quotation" -- on a `git commit` or
`git push` invocation that is otherwise completely ordinary.
"""

import importlib.util
import io
import json
import shlex
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HOOKS = REPO / "clean-rag" / "hooks"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def guard():
    sys.path.insert(0, str(HOOKS))
    return _load("_cr_verify_loop_git_guard", HOOKS / "verify-loop-git-guard.py")


def _run(guard, monkeypatch, raw_stdin: str) -> int:
    monkeypatch.setattr(sys, "stdin", io.StringIO(raw_stdin))
    return guard.main()


class TestUnparseableInputIsRefused:
    def test_malformed_json_payload_is_refused(self, guard, monkeypatch):
        # Whatever tool call produced this, the guard cannot tell whether it
        # carries a blocked git subcommand, and lets it through anyway.
        rc = _run(guard, monkeypatch, "{not valid json")
        assert rc == 2, (
            "verify-loop-git-guard.py returned 0 (allow) on a JSON payload it "
            "could not parse. A guard that cannot see the command's structure "
            "cannot know a blocked git subcommand isn't in it, so failing "
            "open here defeats the entire denylist."
        )

    def test_ordinary_contraction_in_commit_message_breaks_shlex_and_is_refused(
        self, guard, monkeypatch
    ):
        # An apostrophe inside a single-quoted -m argument -- "don't" -- ends
        # the shell string early. This is not adversarial input; it is a
        # completely ordinary commit message an LLM would write without a
        # second thought.
        command = "git commit -m 'fix: don't break the build'"

        # Confirms this is a real shlex failure and not a mistaken premise.
        with pytest.raises(ValueError):
            shlex.split(command)

        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
        rc = _run(guard, monkeypatch, payload)
        assert rc == 2, (
            "verify-loop-git-guard.py allowed a real 'git commit' through "
            "because the unbalanced quote from an ordinary contraction broke "
            "shlex.split() and the except path returns 0 instead of refusing. "
            "This is exactly the class of incident "
            "(2026-08-25, cited in this guard's own docstring) it exists to "
            "prevent: good-cop committing/pushing with nobody having asked."
        )
