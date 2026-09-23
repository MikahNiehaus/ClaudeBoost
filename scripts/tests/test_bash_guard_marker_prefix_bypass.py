"""An expansion this guard cannot read, joined to a literal name, reached a
protected file.

Four of the five patterns in _PROTECTED_PATH_RES are anchored on a directory
name rather than on a filename, so a word only matches them while the
directory is spelled out. `${DIR}/hooks` spells the name and not the
directory, and the guard reduced it to marker plus `/hooks`, which matches
nothing. In real bash the same word writes to the protected path, with the
prefix bound inside the same command by builtins the assignment reader does
not track. Confirmed in this project's own Git Bash:

    read -r DIR <<< ".claude"; echo "would touch: ${DIR}/hooks"
    would touch: .claude/hooks
    printf -v D2 ".claude"; echo "would touch: ${D2}/settings.json"
    would touch: .claude/settings.json

The fix reads the unknown half of the word as one of a short list of
completions (_MARKER_COMPLETIONS) and the literal half as the name that has to
be spelled. ShellCheck SC2115 judges the same shape the same way: for
`rm -rf "$x/home"` it names the literal half, /home, as what the command
reaches when the variable does not resolve.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD = REPO_ROOT / "scripts" / "bash-guard.py"


def _load_guard():
    spec = importlib.util.spec_from_file_location("bash_guard_marker_prefix", GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def guard():
    return _load_guard()


class TestAnUnreadablePrefixReachesAProtectedName:
    """No assignment appears in the command, so the prefix stays unreadable and
    only the literal name survives to be checked. Each of these reaches a
    protected file in real bash for a prefix the environment can hold.
    """

    @pytest.mark.parametrize("command", [
        "rm -rf ${DIR}/hooks",
        "echo x > ${DIR}/settings.json",
        "echo x > ${DIR}/browser-targets.local.json",
        "echo x > ${DIR}/redacted-terms.json",
        "rm -rf ${DIR}/agents",
        "rm -rf ${DIR}/scripts/tests/test_bash_guard_expanded_paths.py",
        "rm ${DIR}/clean-rag/hooks/research-gate.py",
        "rm ${DIR}bash-guard.py",
        # The name has to be spelled after the last unreadable part, not the
        # first: everything between two of them is unreadable as well.
        "rm ${A}/x/${B}/hooks",
        "cp /tmp/payload.json ${DIR}/settings.json",
        "mv ${DIR}/hooks /tmp/hooks",
    ])
    def test_the_write_is_refused(self, guard, command):
        assert guard.evaluate(command) is not None, command

    def test_the_refusal_names_the_route_that_is_open(self, guard):
        """A refusal the human cannot act on is one they route around."""
        problem = guard.evaluate("rm -rf ${DIR}/hooks")
        assert "Edit or Write tool" in problem, problem

    def test_an_unreadable_name_inside_a_protected_directory_is_refused(self, guard):
        """The other half of the same word. Here the directory is spelled and
        the name is not, which is how `rm .claude/*` is already read: by what
        holds it.
        """
        assert guard.evaluate("echo x > .claude/${NAME}") is not None
        assert guard.evaluate("echo x > .claude/commands/${NAME}.md") is None


class TestAnAssignmentTheReaderDoesNotTrack:
    """`read` and `printf -v` bind a name in real bash exactly the way `X=v`
    does, in one command, with no separate shell needed. _record_assignments
    reads the `NAME=value` word shape only, so the reference downstream stays
    unreadable, and the marker rule is what refuses it.
    """

    @pytest.mark.parametrize("command", [
        'read -r DIR <<< ".claude"; rm -rf ${DIR}/hooks',
        'read -r DIR <<< ".claude"; echo x > ${DIR}/settings.json',
        'printf -v DIR ".claude"; rm -rf ${DIR}/hooks',
    ])
    def test_the_write_is_refused(self, guard, command):
        assert guard.evaluate(command) is not None, command


class TestOrdinaryWorkOnAnEnvironmentPathStillRuns:
    @pytest.mark.parametrize("command", [
        "echo x > ${TMPDIR}/out.txt",
        "rm ${BUILD}/app.js",
        "rm -f ${OUT}/render/s-01.png",
        "rm logs/${NAME}/out.log",
        "rm ${A}/${B}/out.log",
        "rm ${LOGDIR:-logs}/*.log",
        "cat ${UNKNOWN_VAR}",
        "grep ${PATTERN} file.txt",
    ])
    def test_it_is_allowed(self, guard, command):
        """The literal half names nothing protected, so no completion of the
        unreadable half makes the word protected. Refusing these refuses every
        scratch path in the session, which is the guard nobody leaves on.
        """
        assert guard.evaluate(command) is None, command

    @pytest.mark.parametrize("command", [
        "cat ${DIR}/settings.json",
        "grep KEY ${DIR}/hooks/x.py",
        "cp ${DIR}/settings.json /tmp/x.json",
    ])
    def test_a_read_is_not_a_write(self, guard, command):
        """The rule covers write and redirect targets only. A copy leaves the
        protected file where it was, and its content is readable anyway.
        """
        assert guard.evaluate(command) is None, command


class TestWhatThisRuleGivesUp:
    """The cost, stated rather than discovered later.

    `scripts` is protected with everything beneath it, so reading an unknown
    prefix as `scripts` would make every `${VAR}/<name>` a refusal, starting
    with `${TMPDIR}/out.txt`. These two commands reach a real file under
    scripts/ for one value of the prefix, and stay allowed because no rule
    separates them from an ordinary scratch path without asking the filesystem
    what exists, which would make the verdict differ per machine.
    """

    @pytest.mark.parametrize("command", [
        "rm ${DIR}/tests/test_bash_guard_expanded_paths.py",
        "rm ${DIR}/session-primer.py",
    ])
    def test_a_tail_that_names_nothing_protected_is_allowed(self, guard, command):
        assert guard.evaluate(command) is None, command

    @pytest.mark.parametrize("command", [
        "rm ${TMPDIR}/hooks",
        "rm ${OUT}/settings.json",
        "rm ${DIST}/*.json",
        "rm -rf ${TMPDIR}/*",
    ])
    def test_a_tail_that_names_a_protected_one_is_refused_wherever_it_points(
            self, guard, command):
        """The other side of the same trade. Each of these is ordinary work on
        a directory that is not .claude, and each is refused because nothing in
        the command says which directory it is.
        """
        assert guard.evaluate(command) is not None, command
