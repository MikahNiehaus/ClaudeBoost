"""A stamp must stop covering a file whose contents changed, whatever its mtime.

check_file_verified invalidated on `mtime > stamp.at`, which asks a clock
whether the file moved. Clocks move both ways. Backdating the mtime after a
real edit, a restored or synced file, skew between two machines, or an editor
that preserves mtime on save all leave rewritten code reading as still
verified, and the gate then goes quiet about it.

git answers the same question about its index the same way, in
Documentation/technical/racy-git.adoc: when the cached stat data cannot settle
whether a file changed, it also compares the contents. The fix records a
content hash at stamp time and checks it alongside the timestamp, so it only
ever invalidates more than the timestamp did.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1] / "hooks"
import sys  # noqa: E402

sys.path.insert(0, str(HOOKS))

import verifier_state as vs  # noqa: E402

SESSION = "content-invalidation"


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """_clean_rag_home reads the env var on every call, so no reload is needed."""
    monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
    return tmp_path


def _stamp(target: Path, cwd: str = "") -> None:
    report = (
        "Ran the suite.\n\n"
        "```\n$ python -m pytest -q\n1 passed in 0.01s\n```\n\n"
        f"VERIFIED: {target.as_posix()}\n"
    )
    vs.record_verifier(SESSION, report, "bad-cop", cwd=cwd)


def test_a_backdated_edit_no_longer_reads_as_verified(tmp_path):
    target = tmp_path / "add.py"
    target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    _stamp(target)
    assert vs.check_file_verified(SESSION, str(target))[0] is True

    # A real arithmetic-operator mutation, same byte count, mtime pushed back.
    target.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    past = time.time() - 3600
    os.utime(target, (past, past))

    ok, reason = vs.check_file_verified(SESSION, str(target))
    assert ok is False, f"a rewritten file still read as verified: {reason}"
    assert "contents changed" in reason


def test_an_exact_mtime_restore_no_longer_reads_as_verified(tmp_path):
    """The editor-preserves-mtime case: the timestamp is put back exactly."""
    target = tmp_path / "app.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    before = target.stat()
    _stamp(target)

    target.write_text("VALUE = 2\n", encoding="utf-8")
    os.utime(target, (before.st_atime, before.st_mtime))

    ok, reason = vs.check_file_verified(SESSION, str(target))
    assert ok is False, f"an mtime-preserving edit still read as verified: {reason}"


def test_an_untouched_file_still_reads_as_verified(tmp_path):
    """The fix must not invalidate everything. A file nobody touched keeps its
    stamp."""
    target = tmp_path / "stable.py"
    target.write_text("STABLE = True\n", encoding="utf-8")
    _stamp(target)
    ok, reason = vs.check_file_verified(SESSION, str(target))
    assert ok is True, reason


def test_a_relative_covers_entry_is_hashed_against_the_payload_cwd(tmp_path):
    """Agents write covers entries relative to the repo root, and the hook
    passes its payload cwd so they resolve."""
    (tmp_path / "pkg").mkdir()
    target = tmp_path / "pkg" / "mod.py"
    target.write_text("X = 1\n", encoding="utf-8")

    report = (
        "```\n$ python -m pytest -q\n1 passed\n```\n\n"
        "VERIFIED: pkg/mod.py\n"
    )
    vs.record_verifier(SESSION, report, "bad-cop", cwd=str(tmp_path))
    assert vs.check_file_verified(SESSION, str(target))[0] is True

    target.write_text("X = 2\n", encoding="utf-8")
    os.utime(target, (time.time() - 3600,) * 2)
    ok, reason = vs.check_file_verified(SESSION, str(target))
    assert ok is False, f"a relative covers entry was not content checked: {reason}"


def test_a_glob_covers_entry_keeps_the_timestamp_rule(tmp_path):
    """No hash is recorded for a glob, so the older rule still applies to it
    and nothing regressed for that shape."""
    target = tmp_path / "globbed.py"
    target.write_text("Y = 1\n", encoding="utf-8")

    report = (
        "```\n$ python -m pytest -q\n1 passed\n```\n\n"
        f"VERIFIED: {tmp_path.as_posix()}/*.py\n"
    )
    vs.record_verifier(SESSION, report, "bad-cop", cwd=str(tmp_path))
    assert vs.check_file_verified(SESSION, str(target))[0] is True

    target.write_text("Y = 2\n", encoding="utf-8")
    ok, reason = vs.check_file_verified(SESSION, str(target))
    assert ok is False, f"the timestamp rule stopped working for a glob: {reason}"
    assert "edited again since" in reason


def test_a_record_written_before_hashes_existed_still_reads(tmp_path):
    """Backward compatibility: a stamp with no `hashes` key falls back to the
    timestamp rule rather than raising."""
    import json

    target = tmp_path / "legacy.py"
    target.write_text("Z = 1\n", encoding="utf-8")
    record = vs._record_path(SESSION)
    record.write_text(
        json.dumps({
            "session_id": SESSION,
            "stamps": [{
                "agent": "bad-cop",
                "at": time.time() + 60,
                "covers": [target.as_posix()],
            }],
        }),
        encoding="utf-8",
    )
    ok, reason = vs.check_file_verified(SESSION, str(target))
    assert ok is True, reason
