"""Adversarial findings against the new Go/gremlins branch of server/mutation.py.

Every fixture below is real, captured gremlins v0.6.0 JSON output (go1.26.1
darwin/arm64), not invented data. See the report bodies for provenance: the
"ground truth" fixture was captured with a generous --timeout-coefficient so
the tests actually run to completion; the "flaky" fixture is the exact same
source and test suite, unchanged, captured moments later with the tool's real
defaults (the invocation _run_gremlins actually makes, no flags overridden).

These are behavioral contracts, not implementation details: they assert on the
score/killed/survived numbers the module reports and on which directories
_go_targets picks, not on internal call sequences.
"""
import contextlib
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.mutation import (  # noqa: E402
    DEFAULT_TIMEOUT_S,
    _GO_MAX_PACKAGES,
    _go_targets,
    _parse_gremlins_report,
    run_mutation,
)


# === Finding 1 (Critical): TIMED OUT counted as killed can fabricate a score ===
#
# livetest/pkg/thing.go:
#     func Threshold(v int) bool {
#         if v > 10 { return true }
#         return false
#     }
# livetest/pkg/thing_test.go only exercises Threshold(100), so the boundary
# mutant (`>` -> `>=`) is genuinely never caught -- a real, provable gap.
# Ground truth, captured with --timeout-coefficient 30 so both mutants get to
# run to completion:
GROUND_TRUTH_REPORT = {
    "files": [{
        "file_name": "thing.go",
        "mutations": [
            {"type": "CONDITIONALS_NEGATION", "status": "KILLED", "line": 7, "column": 7},
            {"type": "CONDITIONALS_BOUNDARY", "status": "LIVED", "line": 7, "column": 7},
        ],
    }],
}
# The exact same unchanged source and tests, captured seconds later with
# gremlins' real defaults (no --timeout-coefficient override -- this is what
# _run_gremlins's argv actually invokes). Reproduced 3/3 times in a row on a
# quiet machine, no artificial CPU load required:
FLAKY_DEFAULT_REPORT = {
    "files": [{
        "file_name": "thing.go",
        "mutations": [
            {"type": "CONDITIONALS_NEGATION", "status": "TIMED OUT", "line": 7, "column": 7},
            {"type": "CONDITIONALS_BOUNDARY", "status": "TIMED OUT", "line": 7, "column": 7},
        ],
    }],
}


def _score(killed, survived):
    total = killed + survived
    return round(100 * killed / total, 1) if total else None


def _exclusions(argv):
    """The -E regexps in an argv, in order."""
    return [argv[i + 1] for i, a in enumerate(argv) if a == "-E"]


def _gremlins_argvs(root, changed):
    """Every argv a real gremlins binary would have been handed for this call."""
    seen = []

    def fake_run(argv, cwd, timeout=None):
        seen.append(list(argv))
        Path(argv[argv.index("-o") + 1]).write_text('{"files": []}')

        class P:
            returncode = 0
            stdout = ""
            stderr = ""
        return P()

    with patch("server.mutation._gremlins_bin", return_value="/fake/gremlins"), \
         patch("server.mutation._run", side_effect=fake_run):
        run_mutation(str(root), changed)
    return seen


def _flag(argv, name):
    """The value following a flag in an argv, or None if the flag is absent."""
    return argv[argv.index(name) + 1] if name in argv else None


class TestTimedOutFabricatesScore:
    def test_ground_truth_is_fifty_percent(self):
        """Sanity: the real, correct score for this package is 50% -- one
        genuine kill, one genuine survivor (the boundary condition gap)."""
        killed, survived, _, _ = _parse_gremlins_report(GROUND_TRUTH_REPORT, ".")
        assert (killed, survived) == (1, 1), (killed, survived)
        assert _score(killed, survived) == 50.0

    def test_default_timeout_reports_the_gap_as_fully_killed(self):
        """This is the bug. Under gremlins' real default timeout coefficient,
        the SAME source and the SAME test suite -- nothing about the code
        changed -- reports the identical two mutants as fully "killed"
        (100%), silently erasing the one real, provable coverage gap. A
        fabricated 100% score is exactly what the module's own header calls
        "worse than no score": it tells a caller the boundary condition is
        covered when it demonstrably is not.
        """
        killed, survived, _, _ = _parse_gremlins_report(FLAKY_DEFAULT_REPORT, ".")
        score = _score(killed, survived)
        # This assertion fails on the current code: _GREMLINS_KILLED =
        # {"KILLED", "TIMED OUT"} means both mutants land in `killed`, so
        # `score` comes back 100.0 here, not close to the ground truth 50.0.
        assert score != 100.0, (
            f"TIMED OUT silently counted a real survivor as killed: "
            f"reported {score}% for a package whose real kill rate is 50%"
        )

    def test_run_mutation_end_to_end_reports_the_same_fabricated_score(self):
        """End-to-end through run_mutation(), not just the parser, using a
        mocked gremlins binary that returns the real captured flaky report
        verbatim -- confirms the fabrication survives all the way to the
        caller-visible result."""
        import json as _json

        def fake_run(argv, cwd, timeout=None):
            o_idx = argv.index("-o")
            Path(argv[o_idx + 1]).write_text(_json.dumps(FLAKY_DEFAULT_REPORT))

            class P:
                returncode = 0
                stdout = ""
                stderr = ""
            return P()

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "go.mod").write_text("module x\n\ngo 1.26\n")
            (root / "thing.go").write_text("package x\n")
            with patch("server.mutation._gremlins_bin", return_value="/fake/gremlins"), \
                 patch("server.mutation._run", side_effect=fake_run):
                result = run_mutation(str(root), ["thing.go"])

        assert result["has_tool"] is True
        # Same bug, visible at the public API: a package with one real,
        # uncaught mutant is reported at a perfect score.
        assert result["score"] != 100.0, result

    def test_the_run_is_configured_off_the_defaults_that_manufacture_timeouts(self):
        """Excluding timeouts stops them fabricating a score. This stops them
        happening, and without it the score still moves with ambient load.

        gremlins' DefaultTimeoutCoefficient is 3 (executor.go:39) and there is no
        flat floor to go with it -- a mutant gets 3x the coverage run and nothing
        more, which on a package whose tests take 80ms is under one recompile.
        Measured over six real packages, three runs each, counting packages that
        produced at least one spurious TIMED OUT: defaults 5 of 6, workers=2
        coefficient=10 zero of 6, in less wall clock than the defaults because a
        timing out mutant burns its whole budget first.
        """
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "go.mod").write_text("module x\n\ngo 1.26\n")
            (root / "thing.go").write_text("package x\n")
            argvs = _gremlins_argvs(root, ["thing.go"])

        argv = argvs[0]
        coefficient = _flag(argv, "--timeout-coefficient")
        assert coefficient is not None and int(coefficient) > 3, (
            f"the run is left on gremlins' default timeout coefficient of 3: {argv!r}"
        )
        # Contention is the other half: gremlins defaults to one worker per core,
        # and every worker compiles and runs the suite at once.
        workers = _flag(argv, "--workers")
        assert workers is not None and 1 <= int(workers) <= (os.cpu_count() or 1), (
            f"workers is absent or above the tool's own default: {argv!r}"
        )
        # --test-cpu is the trap in gremlins' own workers doc: at --test-cpu 4 a
        # mutant whose true status is LIVED came back KILLED, which fabricates a
        # score by a different route than the timeouts do.
        assert "--test-cpu" not in argv, argv


# === Finding 2 (High): a run must never be pointed at a path that panics =====
#
# The finding is real; its diagnosis was not, so the assertion has been replaced
# with one for the property that actually holds rather than weakened. The original
# form asserted `"." not in _go_targets(root, ["main.go"])`, on the theory that
# the module root is the dangerous target and a package directory is safe. Two
# experiments against the real binary (gremlins v0.6.0, go1.26.1 darwin/arm64)
# falsify that theory:
#
#   1. The root is not what triggers the crash. A *package level* target panics
#      identically if it contains a directory whose name ends in .go:
#        gremlins unleash ./internal/foo   (internal/foo/testdata/fixture.go/ exists)
#        -> panic: runtime error: invalid memory address or nil pointer dereference
#           go/ast.Walk(...) engine.go:129     exit 2, no report
#      engine.go:103 walks with fs.WalkDir and discards the DirEntry, so it judges
#      "this is Go source" from the extension alone, hands a *directory* to
#      parser.ParseFile, gets a nil ast.File back and calls ast.Inspect(nil, ...).
#      vendor/github.com/nats-io/nats.go is one such directory, which is why every
#      module vendoring NATS reproduces it.
#   2. Refusing "." would not have fixed even the root case. The enumeration
#      fallback the original cites as the already-guarded branch emits "." itself:
#      _go_targets(<single package module>, []) -> ['.', './sub'].
#
# "." also has to stay legal: a single package Go module has no other target, and
# the ticket asked for Go mutation testing, not for it everywhere except flat
# modules. So the contract is containment at the invocation, which is what these
# assert, for the root case and equally for the package case the original assumed
# safe. Confirmed end to end on a module with a top level nats.go directory:
# unguarded, exit 2 and no report; contained, exit 0 and the package's true 50%.
class TestEveryRunIsContainedToItsTarget:
    def test_a_root_level_change_does_not_walk_the_whole_module(self):
        """A .go file at the module root may target "." -- but never bare. The
        walk must be held to the root package, so the vendor/ tree that carries
        the crashing nats.go directory is never reached."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "go.mod").write_text("module x\n\ngo 1.26\n")
            (root / "main.go").write_text("package main\n")
            (root / "vendor" / "github.com" / "nats-io" / "nats.go").mkdir(parents=True)
            argvs = _gremlins_argvs(root, ["main.go"])

        assert len(argvs) == 1, argvs
        rules = _exclusions(argvs[0])
        # re.search mirrors Go regexp.MatchString, which is what gremlins applies
        # to each walk path (relative to the target) in exclusion/rules.go.
        assert any(re.search(r, "vendor/github.com/nats-io/nats.go") for r in rules), (
            f"nothing in {rules!r} keeps the walk out of vendor/ -- this argv "
            "reaches the directory that panics gremlins in go/ast.Walk"
        )
        assert not any(re.search(r, "main.go") for r in rules), (
            f"{rules!r} excludes the changed file itself, so the run measures nothing"
        )

    def test_a_nested_package_target_is_contained_too(self):
        """The case the original assertion assumed was already safe. A package
        directory is not inherently safe: whatever sits below it gets walked."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "go.mod").write_text("module x\n\ngo 1.26\n")
            (root / "internal" / "foo").mkdir(parents=True)
            (root / "internal" / "foo" / "foo.go").write_text("package foo\n")
            argvs = _gremlins_argvs(root, ["internal/foo/foo.go"])

        assert len(argvs) == 1 and argvs[0][2] == "./internal/foo", argvs
        rules = _exclusions(argvs[0])
        assert any(re.search(r, "testdata/fixture.go") for r in rules), (
            f"nothing in {rules!r} keeps the walk inside ./internal/foo -- a "
            "package level target panics on a testdata/fixture.go/ directory "
            "exactly as a module root does"
        )
        assert not any(re.search(r, "foo.go") for r in rules), rules

    def test_a_dot_go_directory_beside_the_source_is_excluded_by_name(self):
        """The one place containment cannot reach: a .go named directory at the
        target's own top level, whose walk path carries no separator at all."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "go.mod").write_text("module x\n\ngo 1.26\n")
            (root / "main.go").write_text("package main\n")
            (root / "nats.go").mkdir()          # a DIRECTORY whose name ends .go
            argvs = _gremlins_argvs(root, ["main.go"])

        rules = _exclusions(argvs[0])
        assert any(re.search(r, "nats.go") for r in rules), (
            f"{rules!r} lets gremlins parse the directory nats.go as a source "
            "file: nil ast.File, panic in ast.Inspect, exit 2, no report"
        )
        assert not any(re.search(r, "main.go") for r in rules), rules


# === Finding 3 (High): a test-only change silently mutates the whole module ===
#
# Real reproduction against assets/vehicle-settings (9 real Go packages):
#   _go_targets(root, ["internal/config/config_test.go"])
#   -> ['./cmd/server', './internal/adapter/httpapi', './internal/adapter/jwt',
#       './internal/adapter/nats', './internal/adapter/postgres',
#       './internal/config', './internal/domain', './internal/observability',
#       './internal/service']
# One changed test file, in one package, produced targets for every package
# in the module -- exactly the "whole repo run is far too slow" scenario the
# module's own header says this scoping exists to avoid, and it silently
# spends the entire shared time budget mutating unrelated packages like
# cmd/server that were never touched.
class TestTestOnlyChangeStaysScopedToItsOwnPackage:
    def test_single_test_file_change_targets_only_its_own_package(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "go.mod").write_text("module x\n\ngo 1.26\n")
            (root / "pkgA").mkdir()
            (root / "pkgA" / "a.go").write_text("package pkgA\n")
            (root / "pkgA" / "a_test.go").write_text("package pkgA\n")
            (root / "pkgB").mkdir()
            (root / "pkgB" / "b.go").write_text("package pkgB\n")

            targets = _go_targets(root, ["pkgA/a_test.go"])

        # This assertion fails on the current code: naming only a test file
        # in pkgA falls through to the "nothing named" enumeration fallback,
        # which walks the *entire module* and returns every package
        # (including the untouched pkgB), not just pkgA.
        assert targets == ["./pkgA"], (
            f"a change to only pkgA's test file scoped to {targets!r} "
            "instead of just ['./pkgA'] -- it silently expanded to the "
            "whole module"
        )


# === Re-check finding 1 (Critical): a shared budget scored only what it ran ===
#
# Reproduced against the pre-fix module with three changed packages. pkgA really
# does score 5 of 5; pkgB and pkgC never ran, because the one deadline shared
# across the loop was spent before their turn. The result came back:
#   {"score": 100.0, "killed": 5, "survived": 0, "total": 5,
#    "error": "./pkgB: skipped, the 600s budget was spent; ./pkgC: skipped, ..."}
# No numeric field separated that from "all three measured, all perfect" -- the
# two unmeasured packages existed only as prose glued onto `error`, and `score`
# is the field this module exists to make trustworthy. 600s is shared across up
# to _GO_MAX_PACKAGES packages and a real package's compile, test and mutate
# cycle runs to minutes, so this is the ordinary case, not a corner.
#
# The contract these assert: a score is published only for a run that measured
# everything it was asked for, and what went unmeasured is a field a caller can
# branch on, not a sentence it would have to parse.
class _BudgetSpentAfterTheFirstTarget:
    """Stands in for `time` inside the module, so no test waits out 600s.

    The first two reads are the deadline and the first target's own remaining
    check; every read after that lands past the budget, which is exactly what a
    first package that ate the whole budget looks like to the loop.
    """

    def __init__(self):
        self._reads = 0
        self._t0 = time.monotonic()

    def monotonic(self):
        self._reads += 1
        return self._t0 if self._reads <= 2 else self._t0 + DEFAULT_TIMEOUT_S + 1


def _report(**status_counts):
    """A gremlins report with the given count of each mutant status."""
    mutations = []
    for status, n in status_counts.items():
        status = status.replace("_", " ").upper()
        mutations += [{"type": "CONDITIONALS_NEGATION", "status": status, "line": i}
                      for i in range(n)]
    return {"files": [{"file_name": "a.go", "mutations": mutations}]}


def _module(root, packages):
    (root / "go.mod").write_text("module x\n\ngo 1.26\n")
    for pkg in packages:
        (root / pkg).mkdir(parents=True, exist_ok=True)
        (root / pkg / "a.go").write_text(f"package {Path(pkg).name}\n")


def _run_with(root, changed, per_target, clock=None):
    """run_mutation with a stubbed gremlins: per_target(target) -> report or rc."""

    def fake_run(argv, cwd, timeout=None):
        outcome = per_target(argv[2])

        class P:
            returncode = outcome if isinstance(outcome, int) else 0
            stdout = ""
            stderr = "panic: nil deref"

        if not isinstance(outcome, int):
            Path(argv[argv.index("-o") + 1]).write_text(json.dumps(outcome))
        return P()

    with contextlib.ExitStack() as stack:
        stack.enter_context(
            patch("server.mutation._gremlins_bin", return_value="/fake/gremlins"))
        stack.enter_context(patch("server.mutation._run", side_effect=fake_run))
        if clock is not None:
            stack.enter_context(patch("server.mutation.time", clock))
        return run_mutation(str(root), changed)


class TestAPartiallyMeasuredRunCannotPassAsACompleteOne:
    def test_packages_the_budget_never_reached_withhold_the_score(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _module(root, ["pkgA", "pkgB", "pkgC"])
            result = _run_with(root, ["pkgA/a.go", "pkgB/a.go", "pkgC/a.go"],
                               lambda target: _report(killed=5),
                               clock=_BudgetSpentAfterTheFirstTarget())

        assert result["score"] is None, (
            f"reported {result['score']}% as the score of a three package change "
            f"of which two packages were never run: {result}"
        )
        assert result["incomplete"] is True, result
        assert [(u["target"], u["reason"]) for u in result["unmeasured"]] == [
            ("./pkgB", "budget_exhausted"), ("./pkgC", "budget_exhausted")], result
        # The measurement that did happen is still handed back rather than
        # thrown away: a caller that wants the score of what ran can divide.
        assert (result["killed"], result["survived"], result["total"]) == (5, 0, 5)
        assert result["has_tool"] is True

    def test_a_package_that_crashed_withholds_the_score_too(self):
        """Same root cause, a different reason for the gap: the loop scored the
        subset that produced a report. gremlins' AST panic exits 2 and writes no
        report, so pkgB is as unmeasured as one the clock never reached."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _module(root, ["pkgA", "pkgB"])
            result = _run_with(
                root, ["pkgA/a.go", "pkgB/a.go"],
                lambda target: 2 if target == "./pkgB" else _report(killed=5))

        assert result["score"] is None, result
        assert result["incomplete"] is True, result
        assert [(u["target"], u["reason"]) for u in result["unmeasured"]] == [
            ("./pkgB", "failed")], result
        assert "exit 2" in result["error"], result

    def test_mutants_lost_to_the_clock_are_a_field_not_only_prose(self):
        """The one shortfall the pre-fix code did handle, now reported the same
        way as every other: no score, and a machine readable reason."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _module(root, ["pkgA"])
            result = _run_with(root, ["pkgA/a.go"],
                               lambda target: _report(killed=1, timed_out=1))

        assert result["score"] is None, result
        assert result["incomplete"] is True, result
        assert result["unmeasured"][0]["reason"] == "mutants_timed_out", result
        assert result["killed"] == 1

    def test_a_run_that_measured_everything_still_publishes_its_score(self):
        """The other half of the contract. Withholding a score is how a partial
        run stays honest; doing it to a complete one would throw away the
        measurement this endpoint exists to produce."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _module(root, ["pkgA", "pkgB"])
            result = _run_with(root, ["pkgA/a.go", "pkgB/a.go"],
                               lambda target: _report(killed=3, lived=1))

        assert result["score"] == 75.0, result
        assert result["incomplete"] is False and result["unmeasured"] == [], result
        assert result["error"] is None, result

    def test_more_packages_than_the_ceiling_are_reported_not_dropped(self):
        """_GO_MAX_PACKAGES is a real ceiling, so it is also a real shortfall:
        scoring the first 20 of 22 packages is the same fabrication one branch
        over, and the enumeration used to apply it with no trace in the result."""
        packages = [f"pkg{i:02d}" for i in range(_GO_MAX_PACKAGES + 2)]
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _module(root, packages)
            enumerated = _run_with(root, [], lambda target: _report(killed=5))
            named = _run_with(root, [f"{p}/a.go" for p in packages],
                              lambda target: _report(killed=5))

        for result in (enumerated, named):
            assert result["score"] is None, result
            assert [u["reason"] for u in result["unmeasured"]] == ["package_limit"] * 2, result
            assert result["killed"] == 5 * _GO_MAX_PACKAGES, result


# === Re-check finding 2 (High): vendored code was mutated when it was named ===
#
# Reproduced against the pre-fix module: _GO_SKIP_DIRS was consulted only by the
# enumeration fallback, so changed_files=["vendor/dep/v.go"] produced the target
# ['./vendor/dep'] and gremlins was invoked straight at vendored third party
# code -- which is also the tree carrying the .go named directory that panics it.
# An ordinary `go mod vendor` bump in a diff is enough to reach it.
#
# The Go tool draws this line itself: "./... does not match packages in
# subdirectories of ./vendor or ./mycode/vendor" and directories named
# "testdata" are "ignored by the go tool" (go help packages, go1.26.1).
class TestVendoredAndFixtureCodeIsNeverMutated:
    def test_a_named_vendor_or_testdata_file_is_not_a_target(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _module(root, ["vendor/github.com/nats-io/nats", "testdata",
                           "node_modules/pkg", ".git/hooks"])
            for named in ("vendor/github.com/nats-io/nats/a.go", "testdata/a.go",
                          "node_modules/pkg/a.go", ".git/hooks/a.go"):
                assert _go_targets(root, [named]) == [], named

    def test_gremlins_is_never_invoked_against_vendor(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _module(root, ["vendor/dep"])
            argvs = _gremlins_argvs(root, ["vendor/dep/a.go"])
        assert argvs == [], f"gremlins was invoked against vendored code: {argvs!r}"

    def test_naming_only_vendor_does_not_fall_through_to_the_whole_module(self):
        """The trap in fixing this: dropping the path leaves nothing named, and
        an empty scope used to mean "enumerate the module" -- which would mutate
        every real package because the caller named a vendored one."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _module(root, ["vendor/dep", "real"])
            assert _go_targets(root, ["vendor/dep/a.go"]) == []
            result = _run_with(root, ["vendor/dep/a.go"], lambda target: _report(killed=5))

        assert result["has_tool"] is False, result
        assert "vendor" in result["error"], result
        assert result["score"] is None

    def test_a_real_package_named_beside_a_vendor_file_is_still_measured(self):
        """A vendor bump rides along in plenty of real diffs. The real package
        still gets a real score, and the file that was not mutated is said so."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _module(root, ["vendor/dep", "real"])
            result = _run_with(root, ["vendor/dep/a.go", "real/a.go"],
                               lambda target: _report(killed=3, lived=1))

        assert result["score"] == 75.0, result
        assert result["incomplete"] is False, result
        assert "not mutated" in (result["error"] or ""), result

    def test_enumeration_still_skips_all_four(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _module(root, ["vendor/dep", "testdata", "node_modules/pkg",
                           ".git/hooks", "real"])
            targets = _go_targets(root, [])
        assert targets == ["./real"], targets


# === Properties the re-check confirmed still hold ===========================
class TestAStatusThisParserDoesNotKnowCannotInflateAScore:
    def test_an_unrecognized_status_scores_nothing_either_way(self):
        """Version drift, or a corrupted report. The safe direction is out of
        both halves of the fraction, never into `killed`."""
        killed, survived, timed_out, _ = _parse_gremlins_report(
            _report(killed=1, some_future_status=2), ".")
        assert (killed, survived, timed_out) == (1, 0, 0)

    def test_a_status_merely_containing_killed_is_not_a_kill(self):
        """Matching is exact after strip and upper, not a substring test."""
        killed, survived, timed_out, _ = _parse_gremlins_report(
            {"files": [{"file_name": "a.go", "mutations": [
                {"status": "KILLED BUT ACTUALLY NOT", "line": 1}]}]}, ".")
        assert (killed, survived, timed_out) == (0, 0, 0)


class TestTheResultShapeIsTheSameWhicheverToolRan:
    def test_every_key_a_caller_reads_is_present(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _module(root, ["pkgA"])
            result = _run_with(root, ["pkgA/a.go"], lambda target: {"files": []})
        assert {"has_tool", "tool", "score", "killed", "survived", "total",
                "survivors", "incomplete", "unmeasured", "error"}.issubset(result)

    def test_an_unreadable_report_fabricates_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _module(root, ["pkgA"])

            def fake_run(argv, cwd, timeout=None):
                Path(argv[argv.index("-o") + 1]).write_text("{not valid json!!")

                class P:
                    returncode = 0
                    stdout = stderr = ""
                return P()

            with patch("server.mutation._gremlins_bin", return_value="/fake/gremlins"), \
                 patch("server.mutation._run", side_effect=fake_run):
                result = run_mutation(str(root), ["pkgA/a.go"])

        assert result["score"] is None and result["killed"] == 0, result
        assert result["unmeasured"][0]["reason"] == "failed", result

    def test_a_changed_file_that_does_not_exist_is_rejected_not_mutated(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _module(root, ["pkgA"])
            result = run_mutation(str(root), ["does/not/exist.go"])
        assert result["has_tool"] is False and result["score"] is None, result
        assert result["rejected_files"] == ["does/not/exist.go"], result
