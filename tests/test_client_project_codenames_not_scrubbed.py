"""No tracked file names a real client or project, in any casing.

The first scrub of these caught one identifier per file it happened to touch
and left the rest. One test redacted a client codename on one line while the
project named in the same sentence stayed, and nineteen more files still
carried one. A per-file edit cannot close this; only a sweep over everything
git tracks can.

The terms live in .claude/redacted-terms.local.json, which is gitignored, for
the reason test_bash_guard_boundary.py already states about hostnames: a test
for a leak detector must not carry the leak. Spelling the names here, in a
file whose whole subject is that they are client identifiers, would be the
worst place in the repo to put them. .claude/redacted-terms.example.json
documents the shape, and this skips when no local file exists.

Structural leaks (home directories, environment hostnames) need no list and
are covered by test_no_machine_specific_paths.py. A codename is arbitrary, so
it needs one.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TERMS_PATH = REPO_ROOT / ".claude" / "redacted-terms.local.json"
EXAMPLE_PATH = REPO_ROOT / ".claude" / "redacted-terms.example.json"


def _terms() -> list[str]:
    """Absent, unreadable or malformed means no terms, never a false pass on
    a partial list: a half-read config would quietly stop checking the rest."""
    try:
        config = json.loads(TERMS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    terms = config.get("terms")
    if not isinstance(terms, list):
        return []
    return sorted({t for t in terms if isinstance(t, str) and t.strip()})


def _tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files"],
        capture_output=True, text=True, check=True,
    ).stdout
    return [REPO_ROOT / line for line in out.splitlines() if line.strip()]


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def test_the_example_file_ships_so_the_local_one_can_be_written():
    assert EXAMPLE_PATH.is_file(), (
        f"{EXAMPLE_PATH.name} is the only documentation of the local file's "
        "shape, and the local file is gitignored."
    )
    assert isinstance(json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
                      .get("terms"), list)


def test_every_configured_term_is_absent_from_the_tracked_tree():
    terms = _terms()
    if not terms:
        pytest.skip(
            f"no {TERMS_PATH.name}; copy {EXAMPLE_PATH.name} and list the "
            "names you need kept out of this repo"
        )

    hits = []
    for path in _tracked_files():
        if not path.is_file():
            continue
        text = _read(path)
        if text is None:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            lowered = line.lower()
            for term in terms:
                if term.lower() in lowered:
                    rel = path.relative_to(REPO_ROOT).as_posix()
                    hits.append(f"  {rel}:{lineno}: [{term}] {line.strip()[:100]}")

    assert not hits, (
        f"{len(hits)} tracked line(s) name something "
        f"{TERMS_PATH.name} says must stay out of this public repo.\n"
        "Replace each with a fictitious stand-in, not another real name: "
        "Microsoft cleared Contoso, Fabrikam and Litware for this, and RFC "
        "2606 reserves example.com.\n" + "\n".join(hits)
    )


def test_the_scan_actually_covers_the_tree():
    """Guard the guard. A broken git call or filter makes the test above pass
    over an empty list."""
    assert len(_tracked_files()) > 100
