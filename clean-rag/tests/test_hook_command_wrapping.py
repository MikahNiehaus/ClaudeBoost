"""The hook command string contract, across the two files that build it.

Written after 29 of 50 live hook registrations were found corrupted. The cause
was `_wrap_command` assuming every hook command is `<interpreter> <script>` and
regex-splitting the first token off the front. ClaudeBoost's `_py_cmd` emits an
`if command -v ...; then ...; elif ...; fi` chain instead, so the split captured
the keyword `if` as the interpreter and produced:

    if "<runner>" command -v "$CLAUDEBOOST_PYTHON" >/dev/null 2>&1; then ...

That still ran. hook-run.py was handed the argument `command`, found no such
script, exited 0, so the test passed and the real script ran unwrapped. Every
hook kept working while the protection hook-run.py exists to provide was gone,
which is why nothing surfaced it for three days.

There was no test on either function before this file. That absence is what let
it ship: a single assertion that the wrap output does not start with the runner
would have caught it at the point of change.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def install():
    return _load("_cr_install_under_test", REPO / "clean-rag" / "install.py")


@pytest.fixture(scope="module")
def setup():
    return _load("_cb_setup_under_test", REPO / "scripts" / "setup.py")


@pytest.fixture(scope="module")
def runner(install):
    return str(install.HOOK_RUNNER).replace("\\", "/")


SCRIPT = '"$CLAUDEBOOST_HOME/scripts/bash-guard.py"'


def _canonical(script: str = SCRIPT) -> str:
    """`_py_cmd`'s historical output, before the runner was emitted inline."""
    return (
        f'if command -v "$CLAUDEBOOST_PYTHON" >/dev/null 2>&1; then "$CLAUDEBOOST_PYTHON" {script}; '
        f'elif command -v python3 >/dev/null 2>&1; then python3 {script}; '
        f'elif command -v python >/dev/null 2>&1; then python {script}; '
        f'else py {script}; fi'
    )


def _mangled(runner: str, script: str = SCRIPT) -> str:
    """The exact corruption found in the 29 live registrations."""
    return (
        f'if "{runner}" command -v "$CLAUDEBOOST_PYTHON" >/dev/null 2>&1; '
        f'then "$CLAUDEBOOST_PYTHON" {script}; '
        f'elif command -v python3 >/dev/null 2>&1; then python3 {script}; '
        f'elif command -v python >/dev/null 2>&1; then python {script}; '
        f'else py {script}; fi'
    )


class TestCompoundCommands:
    """The if/elif/else chain, which is the shape that broke."""

    def test_runner_never_lands_in_front_of_the_if(self, install, runner):
        # The single assertion that would have caught the original bug.
        out = install._wrap_command(_canonical(), runner=runner)
        assert not out.lstrip().startswith(f'if "{runner}"')
        assert f'if "{runner}" command' not in out

    def test_the_command_v_test_is_left_alone(self, install, runner):
        out = install._wrap_command(_canonical(), runner=runner)
        assert 'if command -v "$CLAUDEBOOST_PYTHON" >/dev/null 2>&1' in out

    def test_every_branch_gets_the_runner(self, install, runner):
        # Kills the mutant that wraps only the first branch: the else branch is
        # the one that runs on a machine where $CLAUDEBOOST_PYTHON is unset,
        # which is exactly the machine-move case the fallback chain exists for.
        out = install._wrap_command(_canonical(), runner=runner)
        assert out.count(runner) == 4
        assert f'then "$CLAUDEBOOST_PYTHON" "{runner}" {SCRIPT}' in out
        assert f'then python3 "{runner}" {SCRIPT}' in out
        assert f'then python "{runner}" {SCRIPT}' in out
        assert f'else py "{runner}" {SCRIPT}' in out

    def test_wrapping_twice_changes_nothing(self, install, runner):
        # Kills the mutant that drops the per-branch already-wrapped check.
        once = install._wrap_command(_canonical(), runner=runner)
        assert install._wrap_command(once, runner=runner) == once

    def test_the_real_target_is_still_findable(self, install, runner):
        out = install._wrap_command(_canonical(), runner=runner)
        target = install._hook_target_script(out)
        assert target is not None
        assert target.name == "bash-guard.py"


class TestMangledCommandsAreRepaired:
    """A mangled command contains "hook-run.py" but is NOT wrapped."""

    def test_mangled_is_not_mistaken_for_wrapped(self, install, runner):
        # Kills the mutant that restores the blanket
        # `if "hook-run.py" in command: return command` guard, which made the
        # 29 corrupted entries permanently unhealable: the guard read the
        # planted substring as proof the work was already done.
        repaired = install._wrap_command(_mangled(runner), runner=runner)
        assert repaired != _mangled(runner)
        assert f'if "{runner}" command' not in repaired

    def test_repair_matches_wrapping_a_clean_command(self, install, runner):
        # Healing a corrupted entry and wrapping a fresh one must converge, or
        # a healed install differs from a new one.
        assert (install._wrap_command(_mangled(runner), runner=runner)
                == install._wrap_command(_canonical(), runner=runner))

    def test_repair_is_idempotent(self, install, runner):
        once = install._wrap_command(_mangled(runner), runner=runner)
        assert install._wrap_command(once, runner=runner) == once


class TestSimpleCommandsUnchanged:
    """The 21 entries that were never broken must stay exactly as they are."""

    def test_simple_command_wraps_as_before(self, install, runner):
        cmd = 'python "$CLEAN_RAG_HOME/hooks/research-gate.py"'
        out = install._wrap_command(cmd, runner=runner)
        assert out == f'python "{runner}" "$CLEAN_RAG_HOME/hooks/research-gate.py"'

    def test_simple_command_is_idempotent(self, install, runner):
        cmd = 'python "$CLEAN_RAG_HOME/hooks/research-gate.py"'
        once = install._wrap_command(cmd, runner=runner)
        assert install._wrap_command(once, runner=runner) == once

    @pytest.mark.parametrize("cmd", ["", "echo hello", "ls -la"])
    def test_commands_without_a_script_are_untouched(self, install, runner, cmd):
        assert install._wrap_command(cmd, runner=runner) == cmd


class TestTheTwoBuildersAgree:
    """setup.py emits the wrapped form; install.py must not re-wrap it."""

    def test_runner_path_is_the_same_in_both_files(self, setup, install):
        # If these drift, a hook wrapped by one looks unwrapped to the other and
        # gets a second runner spliced in.
        assert str(setup.HOOK_RUNNER) == str(install.HOOK_RUNNER)

    def test_py_cmd_output_is_already_wrapped(self, setup, runner):
        out = setup._py_cmd("bash-guard.py")
        assert not out.lstrip().startswith(f'if "{runner}"')
        assert out.count(runner) == 4

    def test_install_wrap_is_a_no_op_on_setup_output(self, setup, install, runner):
        # The contract that lets both mechanisms coexist. Without it, every
        # install adds another runner to every hook.
        out = setup._py_cmd("bash-guard.py")
        assert install._wrap_command(out, runner=runner) == out


class TestStaleDetectionSurvivesTheWrapper:
    """The runner sits in front of the real script now."""

    def test_env_var_target_is_not_stale(self, setup):
        assert setup._hook_command_stale(setup._py_cmd("bash-guard.py")) is False

    def test_missing_absolute_target_is_stale(self, setup, runner):
        # Kills the mutant that reads the first .py in the command: that is the
        # runner, which always exists, so every hook would report healthy.
        cmd = f'python "{runner}" "C:/Development/MyApp/scripts/not-here.py"'
        assert setup._hook_command_stale(cmd) is True

    def test_existing_absolute_target_is_not_stale(self, setup, runner):
        real = str(REPO / "scripts" / "setup.py").replace("\\", "/")
        assert setup._hook_command_stale(f'python "{runner}" "{real}"') is False

    def test_removed_scripts_still_match_through_the_wrapper(self, setup):
        # _remove_deleted_script_hooks matches by basename substring, so the
        # wrapper must not hide the target from it.
        dead = setup._py_cmd("lt-precompact.py")
        assert any(name in dead for name in setup._REMOVED_HOOK_SCRIPTS)
