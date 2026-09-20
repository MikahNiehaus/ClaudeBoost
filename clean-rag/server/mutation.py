"""Mutation testing runner for clean-rag.

The unit test runner (app.py `_run_project_tests`) answers "do the tests pass".
That is a different question from "do the tests actually catch bugs": a happy
path test passes on broken code too. Mutation testing is the domain blind way to
prove a test bites, deliberately break the code and confirm a test goes red. This
runs the language's real mutation tool scoped to the changed files (a whole repo
run is far too slow) and reports the kill score.

No tool for the language, or none installed: report that absence, never fake a
score. A missing tool is a real answer; a fabricated 0 percent is a lie.

Security: the changed file list is model provided, so it is untrusted. Every path
is resolved and confirmed to live inside the project root and to exist, any path
carrying shell metacharacters is rejected, and every tool runs with shell=False on
an argv list. One Windows caveat drives a design choice here: a .cmd shim (npx.cmd)
is launched through cmd.exe by the OS even when shell=False, and cmd.exe can then
reparse the arguments, so where a real entry point exists we invoke node.exe
against the tool's .js directly instead of the .cmd. See _run_stryker.

Findings that shaped the parsing (verify empirically before trusting a parser, the
tool versions drift): mutmut 3.x always exits 0, so the emoji summary line is the
only signal; StrykerJS exit code is meaningless without a configured threshold, so
we read reports/mutation/mutation.json; cargo-mutants is the one tool whose exit
code is load bearing (2 means survivors were found).
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

# Mutation runs the whole suite once per mutant, so even a handful of files takes
# minutes, not seconds. This is the hard outer backstop; each tool also gets a
# timeout of its own where it supports one.
DEFAULT_TIMEOUT_S = 600

# A path argument carrying any of these could be reparsed by a Windows .cmd shim
# even under shell=False, so such a path is rejected outright, on top of the root
# containment check below.
_SHELL_META = set('&|<>^%!"`$;()')

_JS_EXTS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}

# gremlins reports seven mutant statuses and none of its own aggregate fields can
# be trusted as a score; see _run_gremlins. A NOT COVERED mutant counts as
# survived for the same reason _run_stryker counts Stryker's "NoCoverage": code no
# test executes is code no test protects.
#
# TIMED OUT is where this deliberately parts company with _run_stryker, which does
# count Stryker's "Timeout" as a kill. Stryker can afford to, because its budget
# has a floor: netTime * timeoutFactor plus a flat timeoutMS of 5000. gremlins has
# no floor at all. executor.go gives a mutant coverage_elapsed *
# DefaultTimeoutCoefficient (3) and nothing more, so on a package whose tests take
# 80ms the entire budget is a quarter of a second, less than one recompile, and a
# mutant times out because the machine was busy rather than because a test
# noticed. That is not a hypothetical: at the defaults, five of six real packages
# measured here reported mutants TIMED OUT, including one whose true score is 50
# percent and which this module would have published as a flawless 100 percent.
# So a timed out mutant is undetermined: it scores nothing either way, and
# _run_gremlins declines to publish a score at all for a run that produced one.
# Dropping the mutant and scoring what is left is not the safe half measure it
# looks like -- it moves the number in whichever direction the lost mutants would
# have pushed it, so a package whose truth is 50 percent still reads 100 percent
# if the survivor is the mutant that timed out. A score is reported when the
# measurement is complete, and the counts plus the shortfall are reported when it
# is not. gremlins agrees with itself here: report.go scores efficacy as
# killed/(killed+lived) and leaves
# timedOut out of both halves. So do the other two parsers in this file, which
# count only cargo-mutants' CaughtMutant/MissedMutant and only mutmut's killed and
# survived emoji. NOT VIABLE (did not compile) and RUNNABLE (dry run, never
# executed) are evidence of nothing either way and score nothing either.
_GREMLINS_KILLED = {"KILLED"}
_GREMLINS_SURVIVED = {"LIVED", "NOT COVERED"}
_GREMLINS_UNDETERMINED = {"TIMED OUT"}

# Excluding timeouts from the score stops them fabricating one; configuring the
# run stops them happening. Both numbers below are measured over six real packages
# (four in a production Go service), three repetitions each, counting packages that
# produced at least one spurious TIMED OUT:
#     workers=NumCPU coef=3  (the tool's defaults)  5 of 6
#     workers=2      coef=5                         4 of 6
#     workers=4      coef=10                        2 of 6
#     workers=2      coef=10                        0 of 6
# The last row is also the fastest, 3.8s against 10.9s at the defaults on the
# largest package, because a mutant that times out burns its whole budget first.
# The coefficient is a ceiling rather than a delay, so raising it costs wall clock
# only on a mutant that really does hang. Never more workers than the tool would
# have used itself. gremlins' workers doc pairs --workers with --test-cpu, but
# --test-cpu is deliberately not passed: at --test-cpu 4 a mutant whose true
# status is LIVED was reported KILLED, which is the exact fabrication above by
# another route.
_GREMLINS_WORKERS = min(2, os.cpu_count() or 1)
_GREMLINS_TIMEOUT_COEFFICIENT = 10

# engine.go:103 walks the target with fs.WalkDir, discards the DirEntry, and
# decides "this is Go source" from the extension alone. A *directory* whose name
# ends in .go is therefore handed to parser.ParseFile, which returns a nil
# ast.File, and ast.Inspect(nil, ...) panics: exit 2, no report, nothing scored.
# vendor/github.com/nats-io/nats.go is one such directory and every module
# vendoring NATS has it. The module root is not the trigger and scoping is not the
# cure: a package level target containing testdata/fixture.go/ panics identically,
# so both are guarded the same way instead. -E takes filepath regexps matched
# against the walk path relative to the target, so "/" excludes everything below
# the target directory, which fixes every nested case and keeps a run inside
# exactly the package it was asked for. The target's own top level is the one
# place "/" cannot reach, so a .go named directory sitting there is excluded by
# name. Verified both ways on go1.26.1: unguarded, exit 2 and no report; guarded,
# exit 0 and the package's true score.
_GO_CONTAIN_BELOW_TARGET = "/"

# Vendored, fixture and third party trees are not this project's code and its
# tests were never meant to cover them, so they are never a mutation target --
# whether a caller named one or the enumeration below found it. The Go tool draws
# the same line: "./... does not match packages in subdirectories of ./vendor or
# ./mycode/vendor", and "Directory and file names that begin with "." or "_" are
# ignored by the go tool, as are directories named "testdata"" (go help packages,
# go1.26.1). gremlins adds a harder reason: it panics on a .go named directory,
# and vendor/github.com/nats-io/nats.go is one (see _GO_CONTAIN_BELOW_TARGET).
# The skip reads path elements below the project root, so a caller who really
# does want to mutate such a tree can still point project_path at it.
_GO_SKIP_DIRS = {"vendor", "testdata", "node_modules", ".git"}

# Ceiling on packages mutated in one request. The changed file list is model
# provided, so the number of packages it names is untrusted the same way its
# contents are; anything past this is reported unmeasured rather than dropped.
_GO_MAX_PACKAGES = 20


def _result(has_tool, tool, *, score=None, killed=0, survived=0, total=0,
            survivors=None, error=None, rejected=None, unmeasured=None):
    """One result shape for every backend, and one place a score is withheld.

    `unmeasured` carries every part of the request that produced no measurement:
    a package skipped when the shared budget ran out, one that crashed, mutants
    that timed out. While it is non empty the score is None, because a number
    computed over the part that finished reads as if it covered the whole change.
    Doing that here rather than at each call site is the point: a backend cannot
    forget it. The counts still go back, so a caller keeps the partial
    measurement it paid for, and `incomplete` is the field it branches on
    (GitHub's search API sets the same contract for partial data, the matches it
    found plus incomplete_results: true, docs.github.com/en/rest/search).
    Stryker's report schema does the counting half of this: a mutant still
    Pending is reported in the totals and kept out of the score's denominator
    entirely, score being detected/valid
    (stryker-mutator.io/docs/mutation-testing-elements/mutant-states-and-metrics).
    """
    unmeasured = list(unmeasured or [])
    out = {
        "has_tool": has_tool,
        "tool": tool,
        "score": None if unmeasured else score,
        "killed": killed,
        "survived": survived,
        "total": total,
        "survivors": survivors or [],
        "incomplete": bool(unmeasured),
        "unmeasured": unmeasured,
        "error": error,
    }
    if rejected:
        out["rejected_files"] = rejected
    return out


def _absent(tool, how_to_install, rejected=None):
    return _result(False, tool, error=f"{tool} is not installed. {how_to_install}",
                   rejected=rejected)


def _validate_files(project_root: Path, changed_files):
    """Return (relative posix paths inside root, rejected). The input is untrusted.

    Anything that escapes the project root, does not exist, or carries a shell
    metacharacter is rejected rather than passed to a subprocess.
    """
    root = project_root.resolve()
    ok, rejected = [], []
    for raw in changed_files or []:
        if not raw or any(c in _SHELL_META for c in str(raw)):
            rejected.append(raw)
            continue
        try:
            cand = Path(raw)
            resolved = cand.resolve() if cand.is_absolute() else (root / cand).resolve()
            resolved.relative_to(root)  # ValueError if outside the root
        except (ValueError, OSError):
            rejected.append(raw)
            continue
        if not resolved.is_file():
            rejected.append(raw)
            continue
        ok.append(resolved.relative_to(root).as_posix())
    return ok, rejected


def _run(argv, cwd, timeout=DEFAULT_TIMEOUT_S):
    env = {**os.environ, "CI": "true"}
    return subprocess.run(
        argv, cwd=str(cwd), shell=False, capture_output=True, text=True,
        timeout=timeout, env=env, errors="replace",
    )


def run_mutation(project_path: str, changed_files=None):
    """Run the right mutation tool for this project, scoped to changed_files.

    Blocking (subprocess), so callers run it in an executor. Dispatch is by the
    extensions of the changed files first (that is what actually changed), falling
    back to project markers when no files were named.
    """
    root = Path(project_path)
    if not root.is_dir():
        return _result(False, "none", error=f"not a directory: {project_path}")

    valid, rejected = _validate_files(root, changed_files or [])
    if (changed_files or []) and not valid:
        # Files were named but every one was rejected. Do not fall through to a
        # whole repo run, that would mutate far more than asked and bury the
        # rejection. Report it instead.
        return _result(False, "none", rejected=rejected,
                       error="every named file was rejected (outside the project "
                             "root, missing, or an unsafe path); nothing to mutate")
    exts = {Path(f).suffix.lower() for f in valid}

    if (exts & _JS_EXTS) or (not valid and (root / "package.json").is_file()):
        return _run_stryker(root, valid, rejected)
    if ".rs" in exts or (not valid and (root / "Cargo.toml").is_file()):
        return _run_cargo_mutants(root, valid, rejected)
    if ".go" in exts or (not valid and (root / "go.mod").is_file()):
        return _run_gremlins(root, valid, rejected)
    if ".py" in exts or (not valid and (root / "pyproject.toml").is_file()):
        return _run_mutmut(root, valid, rejected)
    if ".java" in exts or (not valid and ((root / "pom.xml").is_file() or (root / "build.gradle").is_file())):
        return _detect_pit(root, rejected)

    return _result(False, "none", rejected=rejected,
                   error="no supported language detected (python, js/ts, rust, go, java)")


def _run_stryker(root, files, rejected):
    """StrykerJS. Prefer node.exe against the real entry over the npx/.cmd shim.

    Score comes from reports/mutation/mutation.json, not the exit code (Stryker
    only exits nonzero when a configured threshold is broken, which we do not set).
    """
    node = shutil.which("node")
    entry = root / "node_modules" / "@stryker-mutator" / "core" / "bin" / "stryker.js"
    if node and entry.is_file():
        argv = [node, str(entry), "run", "--reporters", "json"]
    else:
        local = root / "node_modules" / ".bin" / ("stryker.cmd" if os.name == "nt" else "stryker")
        exe = str(local) if local.is_file() else shutil.which("stryker")
        if not exe:
            return _absent("stryker", "npm i -D @stryker-mutator/core, then re-run.", rejected)
        argv = [exe, "run", "--reporters", "json"]

    if files:
        # Exclude test files from what gets mutated; Stryker does not do that for us.
        mutate = files + ["!**/*.spec.*", "!**/*.test.*"]
        argv += ["--mutate", ",".join(mutate)]

    try:
        _run(argv, root)
    except subprocess.TimeoutExpired:
        return _result(False, "stryker", rejected=rejected,
                       error=f"stryker timed out after {DEFAULT_TIMEOUT_S}s")
    except Exception as e:  # noqa: BLE001
        return _result(False, "stryker", rejected=rejected, error=f"could not run stryker: {e}")

    report = root / "reports" / "mutation" / "mutation.json"
    if not report.is_file():
        return _result(False, "stryker", rejected=rejected,
                       error="stryker produced no mutation.json report")
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return _result(False, "stryker", rejected=rejected, error=f"unreadable mutation.json: {e}")

    killed = survived = 0
    survivors = []
    for fpath, fentry in (data.get("files") or {}).items():
        for m in fentry.get("mutants", []):
            status = m.get("status", "")
            if status in ("Killed", "Timeout"):
                killed += 1
            elif status in ("Survived", "NoCoverage"):
                survived += 1
                loc = (m.get("location") or {}).get("start", {})
                survivors.append({"file": fpath, "line": loc.get("line"),
                                  "description": m.get("mutatorName", "")})
    total = killed + survived
    score = round(100 * killed / total, 1) if total else None
    return _result(True, "stryker", score=score, killed=killed, survived=survived,
                   total=total, survivors=survivors[:20], rejected=rejected)


def _run_cargo_mutants(root, files, rejected):
    """cargo-mutants. Exit code is meaningful: 0 all caught, 2 survivors found."""
    cargo = shutil.which("cargo")
    if not cargo:
        return _absent("cargo-mutants", "cargo install cargo-mutants", rejected)
    # Confirm the subcommand exists, otherwise `cargo mutants` errors confusingly.
    try:
        check = _run([cargo, "mutants", "--version"], root, timeout=30)
        if check.returncode != 0:
            return _absent("cargo-mutants", "cargo install cargo-mutants", rejected)
    except Exception:  # noqa: BLE001
        return _absent("cargo-mutants", "cargo install cargo-mutants", rejected)

    argv = [cargo, "mutants", "-e", "**/*test*"]
    for f in files:
        argv += ["-f", f]
    try:
        proc = _run(argv, root)
    except subprocess.TimeoutExpired:
        return _result(False, "cargo-mutants", rejected=rejected,
                       error=f"cargo-mutants timed out after {DEFAULT_TIMEOUT_S}s")
    except Exception as e:  # noqa: BLE001
        return _result(False, "cargo-mutants", rejected=rejected, error=f"could not run: {e}")

    outcomes = root / "mutants.out" / "outcomes.json"
    killed = survived = total = 0
    if outcomes.is_file():
        try:
            data = json.loads(outcomes.read_text(encoding="utf-8"))
            for o in data.get("outcomes", []):
                summary = o.get("summary", "")
                if summary == "CaughtMutant":
                    killed += 1
                elif summary == "MissedMutant":
                    survived += 1
            total = killed + survived
        except (OSError, json.JSONDecodeError):
            pass
    score = round(100 * killed / total, 1) if total else None
    err = None
    if total == 0:
        # Fall back to exit code when the json schema was not what we expected.
        if proc.returncode == 4:
            err = "cargo-mutants: baseline tests already fail; fix them first"
        elif proc.returncode not in (0, 2):
            err = f"cargo-mutants exited {proc.returncode}"
    return _result(True, "cargo-mutants", score=score, killed=killed, survived=survived,
                   total=total, rejected=rejected, error=err)


def _gremlins_bin():
    """gremlins installs to GOPATH/bin, which a service process's PATH often lacks."""
    found = shutil.which("gremlins")
    if found:
        return found
    candidates = []
    if os.environ.get("GOBIN"):
        candidates.append(Path(os.environ["GOBIN"]) / "gremlins")
    gopath = os.environ.get("GOPATH") or str(Path.home() / "go")
    for part in gopath.split(os.pathsep):
        if part:
            candidates.append(Path(part) / "bin" / "gremlins")
    for cand in candidates:
        try:
            if cand.is_file() and os.access(str(cand), os.X_OK):
                return str(cand)
        except OSError:
            continue
    return None


def _in_skipped_dir(rel_parts):
    """True if a project relative path sits inside a never mutated directory."""
    return any(part in _GO_SKIP_DIRS for part in rel_parts[:-1])


def _go_targets(root, files):
    """Package directories to mutate, one per changed .go file.

    gremlins takes a single path and rejects a second ("accepts at most 1 arg"),
    so several changed packages mean several runs. A _test.go path maps to its own
    package directory like any other file. gremlins mutates source and never
    tests, but a changed test is the single best reason to ask whether that
    package's tests still bite, and dropping the path instead left a test only
    change with nothing named at all, which fell through to the enumeration below
    and silently mutated every package in the module.

    A named path inside a _GO_SKIP_DIRS tree is dropped exactly as the
    enumeration drops it: the list is untrusted, so the exclusion cannot live
    only on the branch this module builds itself. Naming one and nothing else
    therefore yields no target at all, and still does not fall through to the
    enumeration -- the caller scoped this run, and an empty scope is the answer.
    """
    named = [f for f in files if f.endswith(".go")]
    seen = []
    for f in named:
        if _in_skipped_dir(Path(f).parts):
            continue
        parent = Path(f).parent.as_posix()
        rel = "." if parent in ("", ".") else "./" + parent
        if rel not in seen:
            seen.append(rel)
    if named:
        return seen

    # Nothing named: enumerate real package directories rather than pointing
    # gremlins at the module root, which segfaults (see _GO_SKIP_DIRS). The
    # _GO_MAX_PACKAGES ceiling is applied by the caller, which is the only place
    # that can report what it cut instead of quietly scoring the rest.
    found = []
    for path in sorted(root.rglob("*.go")):
        if path.name.endswith("_test.go"):
            continue
        rel_parts = path.relative_to(root).parts
        if _in_skipped_dir(rel_parts):
            continue
        parent = path.parent.relative_to(root).as_posix()
        rel = "." if parent in ("", ".") else "./" + parent
        if rel not in found:
            found.append(rel)
    return found


def _gremlins_exclusions(target_dir):
    """-E regexps keeping one run inside one package and off gremlins' own crash.

    See _GO_CONTAIN_BELOW_TARGET for why both rules exist and what each one covers.
    A directory name reaches this from the filesystem, so it is escaped before it
    becomes a regexp: an unescapable name would otherwise fail gremlins' own
    regexp.Compile and abort the whole run.
    """
    rules = [_GO_CONTAIN_BELOW_TARGET]
    try:
        children = sorted(target_dir.iterdir())
    except OSError:
        return rules
    for child in children:
        if child.name.endswith(".go") and child.is_dir():
            rules.append("^" + re.escape(child.name) + "$")
    return rules


def _parse_gremlins_report(data, target):
    """Counts from the per mutation array, never from the top level aggregates.

    Returns (killed, survived, timed_out, survivors). A timed out mutant scores
    nothing (see _GREMLINS_UNDETERMINED) and is counted out separately so the
    caller can say how much of the package went unmeasured.
    """
    killed = survived = timed_out = 0
    survivors = []
    prefix = "" if target in (".", "") else target[2:] if target.startswith("./") else target
    for entry in data.get("files") or []:
        name = entry.get("file_name") or ""
        path = f"{prefix}/{name}" if prefix and name else (name or prefix)
        for mutant in entry.get("mutations") or []:
            status = (mutant.get("status") or "").strip().upper()
            if status in _GREMLINS_KILLED:
                killed += 1
            elif status in _GREMLINS_SURVIVED:
                survived += 1
                survivors.append({
                    "file": path,
                    "line": mutant.get("line"),
                    "description": f"{mutant.get('type', '')} ({status.lower()})",
                })
            elif status in _GREMLINS_UNDETERMINED:
                timed_out += 1
    return killed, survived, timed_out, survivors


def _gremlins_measure(bin_path, root, target, report, timeout):
    """Run gremlins once over one package. Returns (report data, gap).

    Exactly one of the two is None. `gap` is the (reason, detail) pair for a run
    that measured nothing, which the caller records against the target. Empty
    report data is a real outcome and not a gap: a package with nothing mutable
    prints "No results to report." and writes no file, which is an empty
    measurement rather than a failure, and calling it one would report a working
    tool as broken. A crash leaves no file either, and the exit code is the only
    thing that tells the two apart (the AST panic exits 2).
    """
    argv = [bin_path, "unleash", target]
    for rule in _gremlins_exclusions(root / target):
        argv += ["-E", rule]
    argv += [
        "--workers", str(_GREMLINS_WORKERS),
        "--timeout-coefficient", str(_GREMLINS_TIMEOUT_COEFFICIENT),
        "-o", str(report), "--silent",
    ]
    try:
        proc = _run(argv, root, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, ("budget_exhausted", "timed out")
    except Exception as e:  # noqa: BLE001
        return None, ("failed", f"could not run: {e}")
    if not report.is_file():
        if proc.returncode == 0:
            return {}, None
        tail = ((proc.stderr or proc.stdout or "").strip().splitlines() or [""])[-1]
        return None, ("failed", f"no report (exit {proc.returncode}) {tail[:120]}")
    try:
        return json.loads(report.read_text(encoding="utf-8")), None
    except (OSError, json.JSONDecodeError) as e:
        return None, ("failed", f"unreadable report: {e}")


def _run_gremlins(root, files, rejected):
    """gremlins (Go). One run per changed package, and the score is computed here.

    Two properties of the v0.6.0 JSON report drive this parser, both established
    against the real binary rather than its documentation:

    `mutants_total` and `test_efficacy` count only KILLED plus LIVED. A mutant no
    test reaches is filed under `mutants_not_covered` and left out of both, so a
    package with 38 mutants of which 31 are unreached reports 5 total and 100
    percent efficacy. Passing that on would be precisely the fabricated score this
    module's header forbids, so every count is recomputed from the per mutation
    `files` array and an unreached mutant counts against the score.

    `file_name` is a bare name relative to the path the run was scoped to, so the
    target directory is put back before a survivor is reported.

    None of the flags on the argv is a tuning knob. Each one is load bearing and
    documented where it is defined: --workers and --timeout-coefficient stop the
    tool manufacturing timeouts (_GREMLINS_UNDETERMINED), -E keeps it inside the
    package and off the AST crash (_GO_CONTAIN_BELOW_TARGET).

    A score is published only for a run that measured everything it was asked
    for. Every package shares one budget, so a package that never got its turn,
    crashed, or lost mutants to the clock is recorded in `unmeasured`, which
    withholds the score (see _result). Before this, a three package change whose
    budget died after the first one reported that package's 100 percent as the
    score for the whole change, with the two that never ran named only in the
    prose of `error` -- no number a caller could branch on said the measurement
    covered a third of what changed. The counts still go back either way.

    One artifact: gremlins writes cover.out into the module root while gathering
    coverage. It cannot be redirected, and these Go services already ignore it.
    """
    bin_path = _gremlins_bin()
    if not bin_path:
        return _absent(
            "gremlins",
            "go install github.com/go-gremlins/gremlins/cmd/gremlins@latest "
            "(and put GOPATH/bin on PATH), then re-run.",
            rejected,
        )

    excluded = [f for f in files if f.endswith(".go") and _in_skipped_dir(Path(f).parts)]
    targets = _go_targets(root, files)
    if not targets:
        why = ("; every named Go file lives under vendor/, testdata/, "
               "node_modules/ or .git/, which are never mutated") if excluded else ""
        return _result(False, "gremlins", rejected=rejected,
                       error="no Go package directories to mutate" + why)

    killed = survived = 0
    survivors, ran, unmeasured = [], [], []

    def unmeasure(target, reason, detail):
        """Record a piece of the request that produced no measurement."""
        unmeasured.append({"target": target, "reason": reason, "detail": detail})

    requested = len(targets)
    for target in targets[_GO_MAX_PACKAGES:]:
        unmeasure(target, "package_limit",
                  f"not run, the request covers more than {_GO_MAX_PACKAGES} packages")
    targets = targets[:_GO_MAX_PACKAGES]

    # One budget for the whole request, not one per package, so a change touching
    # six packages cannot quietly run for six times the outer timeout.
    deadline = time.monotonic() + DEFAULT_TIMEOUT_S

    with tempfile.TemporaryDirectory() as tmp:
        for i, target in enumerate(targets):
            remaining = deadline - time.monotonic()
            if remaining <= 5:
                unmeasure(target, "budget_exhausted",
                          f"skipped, the {DEFAULT_TIMEOUT_S}s budget was spent")
                continue
            data, gap = _gremlins_measure(bin_path, root, target,
                                          Path(tmp) / f"gremlins-{i}.json", remaining)
            if gap:
                # A package that produced no report is an honest gap in the
                # measurement; a zero for it would be a lie.
                unmeasure(target, *gap)
                continue
            ran.append(target)
            k, s, t, surv = _parse_gremlins_report(data, target)
            killed += k
            survived += s
            survivors.extend(surv)
            if t:
                # Never silent, and never scored: see _GREMLINS_UNDETERMINED.
                unmeasure(target, "mutants_timed_out",
                          f"{t} mutant(s) timed out, so the {k + s} that finished "
                          f"are not the whole package")

    notes = [f"{u['target']}: {u['detail']}" for u in unmeasured[:5]]
    if unmeasured:
        notes.append(f"no score reported: {len(unmeasured)} of {requested} target(s) "
                     f"were not fully measured")
    if excluded:
        notes.append(f"{len(excluded)} named file(s) under vendor/, testdata/, "
                     f"node_modules/ or .git/ were not mutated")
    total = killed + survived
    # _result withholds this while anything is unmeasured; it is the score of the
    # packages that finished, which is not the score of the change.
    score = round(100 * killed / total, 1) if total else None
    err = "; ".join(notes) if notes else None
    if not ran:
        return _result(False, "gremlins", rejected=rejected, unmeasured=unmeasured,
                       error=err or "gremlins produced no report")
    return _result(True, "gremlins", score=score, killed=killed, survived=survived,
                   total=total, survivors=survivors[:20], rejected=rejected,
                   unmeasured=unmeasured, error=err)


def _run_mutmut(root, files, rejected):
    """mutmut. 3.x always exits 0, so parse the emoji summary line from stdout."""
    mutmut = shutil.which("mutmut")
    if not mutmut:
        return _absent("mutmut", "pip install mutmut", rejected)
    argv = [mutmut, "run"]
    if files:
        # Accepted by 2.x; 3.x may ignore it. Harmless either way, and we parse the
        # summary regardless. Verify scoping empirically against the pinned version.
        argv += ["--paths-to-mutate", ",".join(files)]
    try:
        proc = _run(argv, root)
    except subprocess.TimeoutExpired:
        fallback = _run_mutatest(root, files, rejected)
        if fallback is not None:
            return fallback
        return _result(False, "mutmut", rejected=rejected,
                       error=f"mutmut timed out after {DEFAULT_TIMEOUT_S}s")
    except Exception as e:  # noqa: BLE001
        return _result(False, "mutmut", rejected=rejected, error=f"could not run mutmut: {e}")

    killed, survived = _parse_mutmut_emoji((proc.stdout or "") + (proc.stderr or ""))
    total = killed + survived
    if not total:
        fallback = _run_mutatest(root, files, rejected)
        if fallback is not None:
            return fallback
    score = round(100 * killed / total, 1) if total else None
    err = None if total else "mutmut ran but produced no parseable summary; verify the installed version"
    return _result(total > 0, "mutmut", score=score, killed=killed, survived=survived,
                   total=total, rejected=rejected, error=err)


_MUTATEST_TIMEOUT_S = 120  # Fallback after mutmut; --sample-size 5 should be quick.

def _run_mutatest(root, files, rejected):
    """mutatest fallback. Bytecode-level mutation, quick spot-check."""
    mutatest_bin = shutil.which("mutatest")
    if not mutatest_bin:
        return None  # Not installed, let caller handle
    argv = [mutatest_bin, "--sample-size", "5"]
    if files:
        # mutatest uses --src for the source directory; scope to the
        # common parent of the changed Python files.
        py_files = [f for f in files if f.endswith(".py")]
        if py_files:
            parents = [Path(f).parent for f in py_files]
            common = parents[0]
            for p in parents[1:]:
                # Walk up until we find a shared ancestor of all paths
                while common != p and common not in p.parents:
                    common = common.parent
            src_dir = str(common) or "."
            argv += ["--src", src_dir]
    try:
        proc = _run(argv, root, timeout=_MUTATEST_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return _result(False, "mutatest", rejected=rejected,
                       error=f"mutatest timed out after {_MUTATEST_TIMEOUT_S}s")
    except Exception as e:  # noqa: BLE001
        return _result(False, "mutatest", rejected=rejected, error=f"could not run mutatest: {e}")

    killed, survived = _parse_mutatest_output((proc.stdout or "") + (proc.stderr or ""))
    total = killed + survived
    score = round(100 * killed / total, 1) if total else None
    return _result(total > 0, "mutatest", score=score, killed=killed, survived=survived,
                   total=total, rejected=rejected)


def _parse_mutatest_output(text):
    """Parse mutatest plain-text summary for detected/survived counts."""
    detected = survived = 0
    for line in text.splitlines():
        low = line.lower()
        if "detected" in low:
            detected = max(detected, _count_first_int(line))
        elif "survived" in low:
            survived = max(survived, _count_first_int(line))
    return detected, survived


def _count_first_int(line):
    """Extract the first integer from a line."""
    num = ""
    for ch in line:
        if ch.isdigit():
            num += ch
        elif num:
            break
    return int(num) if num else 0


def _parse_mutmut_emoji(text):
    """Killed (party) and survived (frown) counts from mutmut's summary line."""
    killed = survived = 0
    for line in text.splitlines():
        if "\U0001f389" in line or "\U0001f641" in line:  # party, frown
            killed = max(killed, _count_after(line, "\U0001f389"))
            survived = max(survived, _count_after(line, "\U0001f641"))
    return killed, survived


def _count_after(line, marker):
    idx = line.find(marker)
    if idx < 0:
        return 0
    tail = line[idx + len(marker):].strip()
    num = ""
    for ch in tail:
        if ch.isdigit():
            num += ch
        elif num:
            break
        elif ch != " ":
            break
    return int(num) if num else 0


def _detect_pit(root, rejected):
    """Java. PIT is a Maven/Gradle plugin, not a binary, so this is detect only."""
    return _result(
        False, "pitest", rejected=rejected,
        error="Java is detect only here: add the pitest-maven or gradle-pitest "
              "plugin and run mutationCoverage; wiring a build plugin is out of "
              "scope for an automated runner.",
    )


if __name__ == "__main__":
    # Self check the security critical piece, path validation, which needs no
    # mutation tool installed. Per tool output parsing has to be verified against
    # a real installed tool, which this cannot do here.
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "src").mkdir()
        good = root / "src" / "a.py"
        good.write_text("x = 1\n", encoding="utf-8")
        (root / "outside.py").write_text("y = 2\n", encoding="utf-8")

        ok, rej = _validate_files(root, ["src/a.py"])
        assert ok == ["src/a.py"], ok

        # Escape the root.
        ok, rej = _validate_files(root, ["../outside.py"])
        assert ok == [] and rej == ["../outside.py"], (ok, rej)

        # Shell metacharacter.
        ok, rej = _validate_files(root, ["src/a.py; rm -rf /"])
        assert ok == [] and len(rej) == 1, (ok, rej)

        # Does not exist.
        ok, rej = _validate_files(root, ["src/missing.py"])
        assert ok == [] and rej == ["src/missing.py"], (ok, rej)

        # Emoji summary parse.
        k, s = _parse_mutmut_emoji("Legend ... \U0001f389 120 \U0001f641 15 done")
        assert (k, s) == (120, 15), (k, s)

        # The gremlins report shape, taken from a real v0.6.0 run on
        # shop-search/internal/domain. The top level fields are the trap: they say
        # 5 mutants at 100 percent efficacy while the array holds 38 mutants of
        # which 31 were never reached. Reading them would report a package with
        # almost no effective coverage as perfect.
        report = {
            "mutants_total": 5, "mutants_killed": 5, "mutants_lived": 0,
            "mutants_not_covered": 31, "mutants_not_viable": 0,
            "test_efficacy": 100, "mutations_coverage": 13.88,
            "files": [{
                "file_name": "search.go",
                "mutations": (
                    [{"type": "CONDITIONALS_NEGATION", "status": "KILLED", "line": 1}] * 5
                    + [{"type": "CONDITIONALS_NEGATION", "status": "NOT COVERED", "line": 2}] * 31
                    + [{"type": "CONDITIONALS_NEGATION", "status": "TIMED OUT", "line": 3}] * 2
                ),
            }],
        }
        k, s, timed_out, surv = _parse_gremlins_report(report, "./internal/domain")
        # 5 KILLED scored, 31 unreached counted against the score, 2 timed out and
        # scored neither way but counted out so the caller learns the sample shrank.
        assert (k, s, timed_out) == (5, 31, 2), (k, s, timed_out)
        assert round(100 * k / (k + s), 1) == 13.9, round(100 * k / (k + s), 1)
        assert report["test_efficacy"] == 100  # what we deliberately did not report
        # file_name is a bare name; the scoped directory is put back.
        assert surv[0]["file"] == "internal/domain/search.go", surv[0]

        # A package whose every mutant timed out measured nothing at all. It must
        # not come back a perfect score: there is no score to report.
        k, s, timed_out, _ = _parse_gremlins_report(
            {"files": [{"file_name": "t.go", "mutations": [
                {"status": "TIMED OUT", "line": 1}, {"status": "TIMED OUT", "line": 2}]}]},
            ".")
        assert (k, s, timed_out) == (0, 0, 2), (k, s, timed_out)

        # NOT VIABLE and RUNNABLE are evidence of nothing, score nothing, and are
        # not timeouts either.
        k, s, timed_out, _ = _parse_gremlins_report(
            {"files": [{"file_name": "a.go", "mutations": [
                {"status": "NOT VIABLE", "line": 1}, {"status": "RUNNABLE", "line": 2}]}]},
            ".")
        assert (k, s, timed_out) == (0, 0, 0), (k, s, timed_out)

        # Targets: one per changed package, order preserved, no duplicates.
        t = _go_targets(root, ["internal/svc/a.go", "internal/svc/b.go",
                               "internal/svc/a_test.go", "cmd/server/main.go"])
        assert t == ["./internal/svc", "./cmd/server"], t
        # A change that is only tests scopes to that package, and must not fall
        # back to enumerating the module.
        assert _go_targets(root, ["internal/svc/a_test.go"]) == ["./internal/svc"], \
            _go_targets(root, ["internal/svc/a_test.go"])

        # Containment: everything below the target, plus any .go named *directory*
        # at the target's own top level, which is what panics gremlins' AST walk.
        (root / "pkgdir").mkdir()
        (root / "pkgdir" / "real.go").write_text("package p\n", encoding="utf-8")
        (root / "pkgdir" / "nats.go").mkdir()
        rules = _gremlins_exclusions(root / "pkgdir")
        assert rules == ["/", "^nats\\.go$"], rules
        assert re.match(rules[1], "nats.go") and not re.match(rules[1], "real.go")
        # A plain directory of real files needs the containment rule and no other.
        assert _gremlins_exclusions(root / "src") == ["/"], "unexpected rule"

        # Enumeration skips vendor/, the directory that segfaults gremlins.
        (root / "vendor" / "dep").mkdir(parents=True)
        (root / "vendor" / "dep" / "v.go").write_text("package dep\n", encoding="utf-8")
        (root / "pkg").mkdir()
        (root / "pkg" / "real.go").write_text("package pkg\n", encoding="utf-8")
        enumerated = _go_targets(root, [])
        assert "./pkg" in enumerated, enumerated
        assert not any("vendor" in t for t in enumerated), enumerated

        # _run_gremlins against a stubbed binary. Three outcomes that all arrive
        # as "gremlins wrote no usable score" and must not be conflated.
        (root / "gopkg").mkdir()
        (root / "gopkg" / "a.go").write_text("package gopkg\n", encoding="utf-8")

        class _Proc:
            def __init__(self, rc):
                self.returncode, self.stdout, self.stderr = rc, "", "panic: nil deref"

        def _stub(rc, payload=None):
            def run(argv, cwd, timeout=None):
                if payload is not None:
                    Path(argv[argv.index("-o") + 1]).write_text(payload, encoding="utf-8")
                return _Proc(rc)
            return run

        def _stub_bin():
            return "/stub/gremlins"

        _real_bin, _gremlins_bin = _gremlins_bin, _stub_bin
        _real_run, _run = _run, _stub(0)

        # Exit 0 and no report is "No results to report.": nothing to mutate. An
        # empty measurement, not a broken install, and not a zero score either.
        r = _run_gremlins(root, ["gopkg/a.go"], None)
        assert r["has_tool"] is True and r["score"] is None and r["error"] is None, r

        # A crash leaves no report either. The exit code is the only thing that
        # tells the two apart, and this one has to surface as a failure.
        _run = _stub(2)
        r = _run_gremlins(root, ["gopkg/a.go"], None)
        assert r["has_tool"] is False and "exit 2" in (r["error"] or ""), r

        # One kill and one mutant lost to the clock. Scoring the survivors would
        # publish 100 percent for a package that was never fully measured.
        _run = _stub(0, json.dumps({"files": [{"file_name": "a.go", "mutations": [
            {"status": "KILLED", "line": 1}, {"status": "TIMED OUT", "line": 2}]}]}))
        r = _run_gremlins(root, ["gopkg/a.go"], None)
        assert r["has_tool"] is True and r["killed"] == 1, r
        assert r["score"] is None, r
        assert "timed out" in (r["error"] or ""), r

        # Several packages, one shared budget. gopkg measures a genuine 5 of 5
        # and the clock is gone before pkgb, so half the change went unmeasured:
        # there is no score to publish, and the gap is a field a caller can
        # branch on rather than a sentence it would have to parse out of error.
        (root / "pkgb").mkdir()
        (root / "pkgb" / "b.go").write_text("package pkgb\n", encoding="utf-8")
        _run = _stub(0, json.dumps({"files": [{"file_name": "a.go", "mutations": [
            {"status": "KILLED", "line": 1}] * 5}]}))

        class _SpentBudget:
            """A clock whose first two reads are the deadline and gopkg's own
            remaining check, and whose every later read is past the budget."""

            reads = 0

            def monotonic(self):
                _SpentBudget.reads += 1
                return 0 if _SpentBudget.reads <= 2 else DEFAULT_TIMEOUT_S + 1

        _real_time, time = time, _SpentBudget()
        r = _run_gremlins(root, ["gopkg/a.go", "pkgb/b.go"], None)
        time = _real_time
        assert r["killed"] == 5 and r["score"] is None, r
        assert r["incomplete"] is True, r
        assert [(u["target"], u["reason"]) for u in r["unmeasured"]] == [
            ("./pkgb", "budget_exhausted")], r

        # A vendored path the caller named explicitly is not a target either, and
        # naming only such a path does not fall back to enumerating the module.
        assert _go_targets(root, ["vendor/dep/v.go"]) == [], \
            _go_targets(root, ["vendor/dep/v.go"])

        _gremlins_bin, _run = _real_bin, _real_run

        # No language detected is a clean absence, not a crash.
        r = run_mutation(str(root), [])
        # a bare pyproject-less dir with a .py file dispatched to mutmut absence is fine;
        # here there is no marker and no files, so expect "none".
        assert r["has_tool"] is False, r

    print("ALL PASS")
