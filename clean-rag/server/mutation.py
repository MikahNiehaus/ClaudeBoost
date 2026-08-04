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
import shutil
import subprocess
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


def _result(has_tool, tool, *, score=None, killed=0, survived=0, total=0,
            survivors=None, error=None, rejected=None):
    out = {
        "has_tool": has_tool,
        "tool": tool,
        "score": score,
        "killed": killed,
        "survived": survived,
        "total": total,
        "survivors": survivors or [],
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
    if ".py" in exts or (not valid and (root / "pyproject.toml").is_file()):
        return _run_mutmut(root, valid, rejected)
    if ".java" in exts or (not valid and ((root / "pom.xml").is_file() or (root / "build.gradle").is_file())):
        return _detect_pit(root, rejected)

    return _result(False, "none", rejected=rejected,
                   error="no supported language detected (python, js/ts, rust, java)")


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

        # No language detected is a clean absence, not a crash.
        r = run_mutation(str(root), [])
        # a bare pyproject-less dir with a .py file dispatched to mutmut absence is fine;
        # here there is no marker and no files, so expect "none".
        assert r["has_tool"] is False, r

    print("ALL PASS")
