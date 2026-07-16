"""
Adversarial tests for _bad_cop_ran_with_bugs() in verifier-gate.py.

Correctness properties under test:
1. Returns True iff at least one stamp has agent=="bad-cop" AND covers is falsy.
2. Returns False when no record file exists.
3. Returns False when bad-cop ran clean (non-empty covers).
4. Returns False when only good-cop stamps exist (even with empty covers).
5. Returns False on any read/parse error (fail open).
6. The block/allow decision is NOT changed, only the message changes.
7. _bump_block_count() fires BEFORE the if/else branch.
8. _record_path import from verifier_state works.

Run: python tests/test_bad_cop_detection.py
"""

import importlib.util
import json
import os
import sys
import tempfile
import hashlib
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent / "clean-rag" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

# ── import the functions under test ──────────────────────────────────────────

from verifier_state import _record_path  # property 8: must import cleanly

# Load verifier-gate (hyphenated name requires importlib)
spec = importlib.util.spec_from_file_location(
    "verifier_gate", HOOKS_DIR / "verifier-gate.py"
)
vg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vg)

_bad_cop_ran_with_bugs = vg._bad_cop_ran_with_bugs

# ── helpers ───────────────────────────────────────────────────────────────────

PASS = []
FAIL = []


def check(label: str, got, expected):
    if got == expected:
        PASS.append(label)
        print(f"  PASS  {label}")
    else:
        FAIL.append(label)
        print(f"  FAIL  {label}")
        print(f"         expected={expected!r}  got={got!r}")


def _session_id_for(tmpdir: Path) -> str:
    """Return a session_id whose _record_path() lands in tmpdir.

    _record_path hashes the session_id, then stores under
    _state_dir() which is hardwired to CLEAN_RAG_HOME/state/verifier/.
    We patch CLEAN_RAG_HOME via environment variable so the path resolves
    inside our tmpdir instead.
    """
    return "test-session-adversarial"


def _write_record(tmpdir: Path, session_id: str, stamps: list) -> Path:
    """Write a session record into tmpdir/state/verifier/ and return the path."""
    state = tmpdir / "state" / "verifier"
    state.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256((session_id or "no-session").encode()).hexdigest()[:16]
    p = state / f"session-{key}.json"
    p.write_text(json.dumps({"session_id": session_id, "stamps": stamps}), encoding="utf-8")
    return p


# ── tests run with CLEAN_RAG_HOME pointed at tmpdir ─────────────────────────

with tempfile.TemporaryDirectory() as _tmp:
    tmpdir = Path(_tmp)
    os.environ["CLEAN_RAG_HOME"] = str(tmpdir)
    # reload verifier_state so _state_dir() picks up the new env var
    import verifier_state
    importlib.reload(verifier_state)
    # also reload verifier_gate so it gets the reloaded _record_path
    spec2 = importlib.util.spec_from_file_location(
        "verifier_gate2", HOOKS_DIR / "verifier-gate.py"
    )
    vg2 = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(vg2)
    _bad_cop_ran_with_bugs = vg2._bad_cop_ran_with_bugs

    print("\n=== _bad_cop_ran_with_bugs() adversarial tests ===\n")

    SESSION = "test-session-adversarial"

    # ── property 2: no record file → False ───────────────────────────────────
    check("no record file → False",
          _bad_cop_ran_with_bugs(SESSION), False)

    # ── property 1a: covers=[] (empty list) → True ───────────────────────────
    _write_record(tmpdir, SESSION, [
        {"agent": "bad-cop", "at": 1.0, "covers": []}
    ])
    check("covers=[] → True",
          _bad_cop_ran_with_bugs(SESSION), True)

    # ── property 1b: covers key missing entirely → True ──────────────────────
    _write_record(tmpdir, SESSION, [
        {"agent": "bad-cop", "at": 1.0}
    ])
    check("covers key missing → True",
          _bad_cop_ran_with_bugs(SESSION), True)

    # ── property 1c: covers=None → True ──────────────────────────────────────
    # json.loads will give None; not s.get("covers") is True for None
    _write_record(tmpdir, SESSION, [
        {"agent": "bad-cop", "at": 1.0, "covers": None}
    ])
    check("covers=None → True",
          _bad_cop_ran_with_bugs(SESSION), True)

    # ── property 3: bad-cop ran clean (non-empty covers) → False ─────────────
    _write_record(tmpdir, SESSION, [
        {"agent": "bad-cop", "at": 1.0, "covers": ["some/file.py"]}
    ])
    check("bad-cop clean (non-empty covers) → False",
          _bad_cop_ran_with_bugs(SESSION), False)

    # ── property 4: only good-cop with empty covers → False ──────────────────
    _write_record(tmpdir, SESSION, [
        {"agent": "good-cop", "at": 1.0, "covers": []}
    ])
    check("good-cop with covers=[] → False",
          _bad_cop_ran_with_bugs(SESSION), False)

    # ── property 4b: agent key missing (not bad-cop) → False ─────────────────
    _write_record(tmpdir, SESSION, [
        {"at": 1.0, "covers": []}
    ])
    check("agent key missing (not bad-cop) → False",
          _bad_cop_ran_with_bugs(SESSION), False)

    # ── property 5a: malformed JSON → False (fail open) ──────────────────────
    key = hashlib.sha256((SESSION or "no-session").encode()).hexdigest()[:16]
    bad_json_path = tmpdir / "state" / "verifier" / f"session-{key}.json"
    bad_json_path.write_text("{not valid json ][", encoding="utf-8")
    check("malformed JSON → False",
          _bad_cop_ran_with_bugs(SESSION), False)

    # ── property 5b: stamps key missing → False ───────────────────────────────
    bad_json_path.write_text(json.dumps({"session_id": SESSION}), encoding="utf-8")
    check("stamps key missing → False",
          _bad_cop_ran_with_bugs(SESSION), False)

    # ── property 5c: stamps is not a list (integer) → False ──────────────────
    # BUG: _bad_cop_ran_with_bugs() raises TypeError instead of returning False.
    # record.get("stamps", []) returns 42, then `any(... for s in 42)` throws.
    # The function contract says "fail open" but it propagates an exception.
    # The only reason the gate still exits 0 is the outer __main__ except block.
    bad_json_path.write_text(json.dumps({"session_id": SESSION, "stamps": 42}), encoding="utf-8")
    try:
        result = _bad_cop_ran_with_bugs(SESSION)
        check("stamps is integer → False (FAIL: raised TypeError instead)",
              result, False)
    except TypeError as e:
        FAIL.append("stamps is integer → TypeError instead of False")
        print(f"  FAIL  stamps is integer: raised TypeError({e}) — function does not fail open")

    # ── property 5d: empty stamps list → False ───────────────────────────────
    _write_record(tmpdir, SESSION, [])
    check("empty stamps list → False",
          _bad_cop_ran_with_bugs(SESSION), False)

    # ── mixed: bad-cop clean + bad-cop with bugs → True (any is enough) ──────
    _write_record(tmpdir, SESSION, [
        {"agent": "bad-cop", "at": 1.0, "covers": ["clean/file.py"]},
        {"agent": "bad-cop", "at": 2.0, "covers": []},
    ])
    check("mixed stamps (clean + bugs) → True",
          _bad_cop_ran_with_bugs(SESSION), True)

    # ── good-cop + bad-cop-clean only → False ────────────────────────────────
    _write_record(tmpdir, SESSION, [
        {"agent": "good-cop", "at": 1.0, "covers": []},
        {"agent": "bad-cop", "at": 2.0, "covers": ["file.py"]},
    ])
    check("good-cop empty + bad-cop clean → False",
          _bad_cop_ran_with_bugs(SESSION), False)

    # ── covers=False (falsy but not list) → True ─────────────────────────────
    _write_record(tmpdir, SESSION, [
        {"agent": "bad-cop", "at": 1.0, "covers": False}
    ])
    check("covers=False (falsy non-list) → True",
          _bad_cop_ran_with_bugs(SESSION), True)

    # ── covers=0 (falsy integer) → True ──────────────────────────────────────
    _write_record(tmpdir, SESSION, [
        {"agent": "bad-cop", "at": 1.0, "covers": 0}
    ])
    check("covers=0 (falsy int) → True",
          _bad_cop_ran_with_bugs(SESSION), True)

    # ── covers={} (empty dict, falsy) → True ─────────────────────────────────
    _write_record(tmpdir, SESSION, [
        {"agent": "bad-cop", "at": 1.0, "covers": {}}
    ])
    check("covers={} (falsy empty dict) → True",
          _bad_cop_ran_with_bugs(SESSION), True)


# ── property 8: _record_path import from verifier_state ──────────────────────
print()
try:
    from verifier_state import _record_path as _rp_check
    result = _rp_check("test")
    check("_record_path importable and callable from verifier_state",
          isinstance(result, Path), True)
except Exception as e:
    FAIL.append("_record_path import")
    print(f"  FAIL  _record_path import: {e}")


# ── property 7: _bump_block_count fires BEFORE the if/else branch ─────────────
# Inspect the source directly — read the AST order from the file.
print()
gate_src = (HOOKS_DIR / "verifier-gate.py").read_text(encoding="utf-8")
lines = gate_src.splitlines()

bump_line = None
bad_cop_check_line = None
for i, line in enumerate(lines, 1):
    if "_bump_block_count(session_id)" in line and bump_line is None:
        bump_line = i
    if "_bad_cop_ran_with_bugs(session_id)" in line and bad_cop_check_line is None:
        bad_cop_check_line = i

if bump_line and bad_cop_check_line:
    check(
        f"_bump_block_count (line {bump_line}) fires BEFORE _bad_cop_ran_with_bugs (line {bad_cop_check_line})",
        bump_line < bad_cop_check_line,
        True,
    )
else:
    FAIL.append("bump/if-else ordering check")
    print(f"  FAIL  could not find lines: bump={bump_line}, bad_cop_check={bad_cop_check_line}")


# ── property 6: return code is still 2 regardless of which branch ─────────────
# Both branches must lead to `return 2`, not 0 or something else.
# Check that exactly one `return 2` comes AFTER both the if and the else blocks.
print()
return_2_after_branch = any(
    "return 2" in lines[i]
    for i in range(bad_cop_check_line or 0, len(lines))
) if bad_cop_check_line else False

check(
    "return 2 present after _bad_cop_ran_with_bugs branch (block/allow unchanged)",
    return_2_after_branch,
    True,
)

# ── summary ───────────────────────────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"Results: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED:", FAIL)
    sys.exit(1)
else:
    print("All adversarial checks passed.")
    sys.exit(0)
