"""A shell word reaches a file the word does not spell.

Two expansions run before the command does. A glob puts a metacharacter where
a letter of the protected name should be, and a brace puts several words where
one was written. Both were proven against a scratch copy of the real config in
this project's own Git Bash:

    echo x > .claude/browser-target*.local.json    overwrote it
    rm .claude/browser-target{s,q}.local.json      deleted it

The literal patterns in _PROTECTED_PATH_RES contain no such spelling, so every
one of these reached the guard's own control files unrefused. `mv` is the same
gap by a different route: the source operand went unchecked, so the `rm` that
was refused had a synonym that was not.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD = REPO_ROOT / "scripts" / "bash-guard.py"


def _load_guard():
    spec = importlib.util.spec_from_file_location("bash_guard_expanded", GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def guard():
    return _load_guard()


class TestAnExpandedWordReachesTheSameFile:
    @pytest.mark.parametrize("command", [
        "echo x > .claude/browser-target*.local.json",
        "echo x > .claude/browser-target?.local.json",
        "echo x > .claude/browser-target[s].local.json",
        "echo x > .claude/redacted-term*.local.json",
        "echo x > .claude/setting?.json",
        "echo x > .claude/settings.loc*.json",
        "rm .claude/browser-target{s,q}.local.json",
        "cp payload.py .claude/hook{s,x}/session-primer.py",
        "mv clean-rag/hook*/verifier-gate.py /tmp/x.py",
        "rm .claude/*",
        "tee scripts/bash-guar[d].py",
    ])
    def test_the_write_is_refused(self, guard, command):
        assert guard.evaluate(command) is not None, (
            f"{command!r} expands onto a file that decides what this session "
            f"may do, and was allowed because the word does not spell it"
        )

    @pytest.mark.parametrize("command", [
        "rm logs/*",
        "rm build/*.log",
        "rm -f render/s-0*.png",
        "rm clean-rag/databases/*.tmp",
        "echo x > docs/hooks-overview.md",
        "cp .claude/settings.json .claude/settings.json.bak",
    ])
    def test_an_ordinary_glob_still_runs(self, guard, command):
        """A component that is nothing but wildcards names no file in
        particular. Reading it as reaching every protected path refuses
        `rm logs/*`, and a guard that noisy is a guard somebody switches off.
        """
        assert guard.evaluate(command) is None

    @pytest.mark.parametrize("command", [
        "rm src/*.py",
        "rm tests/*.py",
        "rm docs/*.py",
        "rm build/*.py",
        "rm test-scripts/*.py",
        "rm clean-rag/cli/*.py",
        "rm -f build/*.py",
        "mv src/*.py /tmp/",
    ])
    def test_a_python_glob_in_an_unprotected_directory_still_runs(self, guard, command):
        """Python is this repo's main language, so `<dir>/*.py` is routine.

        Every one of these was refused while the guard's own file was a witness
        at any depth: the crossing `**` absorbed the word's directory and the
        word's `*` spelled `bash-guard`, so a file that is not in src/ or docs/
        decided the verdict for both.
        """
        assert guard.evaluate(command) is None

    @pytest.mark.parametrize("command", [
        "rm *.py",
        "rm -f *.py",
    ])
    def test_a_bare_python_glob_is_still_refused(self, guard, command):
        """The one glob whose directory cannot be judged, because it has none.

        `*.py` expands against the current directory, and this guard never
        learns what that is. Run inside scripts/ the word names the guard
        itself, exactly as the bare literal `rm bash-guard.py` does, and that
        one is refused too. Naming a directory clears it.
        """
        assert guard.evaluate(command) is not None

    @pytest.mark.parametrize("command", [
        "rm scripts/*.py",
        "rm clean-rag/hooks/*.py",
        "rm .claude/*.json",
        "rm scripts/tests/*.py",
    ])
    def test_a_glob_in_a_protected_directory_is_still_refused(self, guard, command):
        assert guard.evaluate(command) is not None


class TestMovingAProtectedFileIsAWrite:
    @pytest.mark.parametrize("command", [
        "mv scripts/bash-guard.py /tmp/backup.py",
        "mv .claude/settings.json /tmp/x.json",
        "mv .claude /tmp/claude-backup",
        "mv .claude/hooks /tmp/hooks",
        "mv .claude/agents /tmp/agents",
        "mv clean-rag/hooks /tmp/hooks",
        "mv scripts /tmp/scripts",
        "rm scripts",
        "mv -t /tmp scripts/bash-guard.py",
        "rsync --remove-source-files scripts/bash-guard.py /tmp/",
    ])
    def test_the_source_operand_is_refused(self, guard, command):
        """`mv <protected> elsewhere` leaves the same empty path behind as the
        `rm` the guard already refuses."""
        assert guard.evaluate(command) is not None

    def test_a_copy_leaves_the_protected_file_where_it_was(self, guard):
        """Deliberate, and the reason _DESTINATION_ONLY_COMMANDS exists.

        A copy disarms nothing: the guarded file is still there, still guarded,
        and `cat` on it is allowed anyway, so refusing the copy hides nothing
        and costs the backup this guard measured as ordinary.
        """
        assert guard.evaluate(
            "cp .claude/browser-targets.local.json /tmp/copy.json") is None
        assert guard.evaluate(
            "cp scripts/bash-guard.py /tmp/copy.py") is None

    def test_writing_to_the_copy_target_is_still_refused(self, guard):
        assert guard.evaluate("cp /tmp/payload.py scripts/bash-guard.py") is not None


class TestAVariableCarriesTheProtectedPath:
    """The spelling that defeated every protected path check, literal ones
    included, in one plain command with no glob and no brace.

    check_env_var_expansion recommends this idiom in its own refusal message
    ("variables you assign earlier in the same command are fine to reference"),
    so the ergonomic half of the guard steered toward the construction the
    security half could not read.
    """

    @pytest.mark.parametrize("command", [
        "F=scripts/bash-guard.py; rm $F",
        "F=scripts/bash-guard.py; rm ${F}",
        "A=scripts/bash-guard; rm $A.py",
        'F=.claude/settings.json; echo "{}" >> $F',
        "F=scripts/bash-guard.py; mv $F /tmp/out.py",
        "export F=scripts/bash-guard.py; rm $F",
        "A=scripts; B=bash-guard.py; rm $A/$B",
        "F=clean-rag/hooks/verifier-gate.py; echo bad > $F",
        "D=.claude/browser-targets.local.json; echo x > $D",
        "F=.env; cat $F",
        "C=scripts/bash-guard.py; tee ${C}",
        'bash -c "F=scripts/bash-guard.py; rm $F"',
    ])
    def test_the_write_is_refused(self, guard, command):
        assert guard.evaluate(command) is not None

    @pytest.mark.parametrize("command", [
        "F=build.log; rm $F",
        "D=logs; rm ${D}/*.tmp",
        "F=out.txt; echo x > $F",
        "F=notes.md; mv $F /tmp/notes.md",
        "D=render; rm -f ${D}/s-0*.png",
        "for f in logs/*.log; do rm $f; done",
        "for f in build/*.py; do rm $f; done",
    ])
    def test_a_variable_holding_an_ordinary_path_still_runs(self, guard, command):
        assert guard.evaluate(command) is None

    @pytest.mark.parametrize("command", [
        "for f in a.log scripts/bash-guard.py; do rm $f; done",
        "for f in .claude/settings.json; do echo x > $f; done",
    ])
    def test_a_loop_is_judged_on_every_path_it_iterates(self, guard, command):
        """A loop name stands for its whole list, so one protected path
        anywhere in that list is a write to it."""
        assert guard.evaluate(command) is not None

    def test_a_target_the_command_never_names_is_refused(self, guard):
        """An environment variable's value is not in the command, so no amount
        of text matching decides it. Refused the same way a command
        substitution target is, and for the same reason."""
        assert guard.evaluate("rm ${SOME_PATH_FROM_THE_ENVIRONMENT}") is not None

    def test_a_variable_directory_with_a_literal_name_still_runs(self, guard):
        """Narrowed to the whole word on purpose. A scratch path built on
        ${TEMP} is ordinary work and keeps a readable filename."""
        assert guard.evaluate("echo x > ${TEMP}/out.txt") is None

    def test_a_quoted_assignment_is_read_as_one(self, guard):
        assert guard.evaluate('F="scripts/bash-guard.py"; rm "$F"') is not None

    def test_a_single_quoted_reference_does_not_expand(self, guard):
        """The shell does not expand inside single quotes, so neither does the
        resolver: reading '$F' as its value would refuse text that stays text.
        """
        assert guard.evaluate("F=build.log; grep -r 'rm $F' docs") is None


class TestTheTwoProtectionTablesAgree:
    """_PROTECTED_PATH_RES is the authority for a literal path and
    _PROTECTED_GLOBS is the one a glob is compared against. Two tables drift.
    """

    PROTECTED = [
        "scripts/bash-guard.py",
        "c:/projects/myapp/scripts/bash-guard.py",
        "scripts/bash-guard.proposed.py",
        ".claude/settings.json",
        ".claude/settings.local.json",
        ".claude/browser-targets.local.json",
        ".claude/browser-targets.example.json",
        ".claude/redacted-terms.local.json",
        ".claude/hooks/session-primer.py",
        ".claude/agents/bad-cop.md",
        "clean-rag/hooks/verifier-gate.py",
        "scripts/tests/test_bash_guard.py",
    ]
    NOT_PROTECTED = [
        "docs/using-claudeboost.md",
        "clean-rag/server/app.py",
        "logs/output.txt",
        ".claude/commands/qa.md",
    ]

    @pytest.mark.parametrize("path", PROTECTED)
    def test_both_tables_hold_a_protected_path(self, guard, path):
        assert guard._matches_protected_literal(path), path
        assert any(
            guard._globs_overlap(guard._glob_tokens(path), witness)
            for witness in guard._PROTECTED_GLOB_TOKENS), path

    @pytest.mark.parametrize("path", NOT_PROTECTED)
    def test_neither_table_holds_an_ordinary_path(self, guard, path):
        assert not guard._matches_protected_literal(path), path
        assert not any(
            guard._globs_overlap(guard._glob_tokens(path), witness)
            for witness in guard._PROTECTED_GLOB_TOKENS), path


class TestBraceExpansion:
    @pytest.mark.parametrize("word,expected", [
        ("a{s,q}b", {"asb", "aqb"}),
        # bash leaves a brace with no comma and no range alone, so reading it
        # as an expansion would invent a path the command never names.
        ("a{s}b", {"a{s}b"}),
        ("x{1..3}", {"x1", "x2", "x3"}),
        ("{a,b}{c,d}", {"ac", "ad", "bc", "bd"}),
        ("no-braces", {"no-braces"}),
        ("unclosed{a,b", {"unclosed{a,b"}),
    ])
    def test_it_matches_what_bash_produces(self, guard, word, expected):
        assert set(guard._brace_expand(word)) == expected

    def test_a_runaway_expansion_is_bounded(self, guard):
        assert len(guard._brace_expand("{a,b}" * 20)) <= guard._BRACE_LIMIT


class TestGlobOverlap:
    @pytest.mark.parametrize("word,witness", [
        ("browser-target*.local.json", "browser-targets*.json"),
        ("bash-guar?.py", "bash-guard.py"),
        ("a/b/c.py", "**/c.py"),
        ("*.py", "bash-guard.py"),
    ])
    def test_patterns_that_share_a_path(self, guard, word, witness):
        assert guard._globs_overlap(
            guard._glob_tokens(word), guard._glob_tokens(witness, crossing=True))

    @pytest.mark.parametrize("word,witness", [
        # A * never crosses a directory separator, which is what keeps a glob
        # in one directory from reaching a protected file in another.
        ("logs/*", "logs/*/settings.json"),
        ("*.json", "bash-guard.py"),
        ("a/*.log", "**/.claude/settings*.json"),
    ])
    def test_patterns_that_share_nothing(self, guard, word, witness):
        assert not guard._globs_overlap(
            guard._glob_tokens(word), guard._glob_tokens(witness, crossing=True))


def test_the_refusal_points_at_a_tool_rule_that_exists():
    """_protected_refusal sends the human to the Edit and Write tools. That is
    only true while a rule covers the guard's own files, and none did.
    """
    settings = json.loads(
        (REPO_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    ask = set(settings["permissions"]["ask"])
    for rule in ("Edit(**/scripts/bash-guard.py)",
                 "Write(**/scripts/bash-guard.py)",
                 "Edit(**/clean-rag/hooks/**)",
                 "Write(**/clean-rag/hooks/**)"):
        assert rule in ask, rule
