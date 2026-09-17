"""The tail must survive the log being rotated out from under it.

A tailer that holds one fd forever passes every other test in this file and
still goes permanently silent the first time RotatingFileHandler rolls over,
which is the failure this suite exists to catch.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cli.log_tail import LogTail  # noqa: E402


@pytest.fixture
def log(tmp_path):
    p = tmp_path / "server.log"
    p.write_text("existing line\n", encoding="utf-8")
    return p


def test_reads_lines_appended_after_open(log):
    tail = LogTail(log)
    assert tail.poll() == []

    with log.open("a", encoding="utf-8") as fh:
        fh.write("one\ntwo\n")

    assert tail.poll() == ["one", "two"]
    tail.close()


def test_does_not_replay_what_was_there_before(log):
    tail = LogTail(log)
    tail.poll()
    assert "existing line" not in tail.poll()
    tail.close()


def test_holds_a_partial_line_until_its_newline_arrives(log):
    tail = LogTail(log)
    tail.poll()

    with log.open("a", encoding="utf-8") as fh:
        fh.write("half a li")
    assert tail.poll() == []

    with log.open("a", encoding="utf-8") as fh:
        fh.write("ne\n")
    assert tail.poll() == ["half a line"]
    tail.close()


def test_survives_rotation_and_reads_the_new_file(log):
    """The case that kills a tailer holding one fd."""
    tail = LogTail(log)
    tail.poll()

    with log.open("a", encoding="utf-8") as fh:
        fh.write("before rotation\n")
    assert tail.poll() == ["before rotation"]

    # What RotatingFileHandler does: rename, then create a new file same path.
    log.rename(log.with_suffix(".log.1"))
    log.write_text("after rotation\n", encoding="utf-8")

    assert tail.poll() == ["after rotation"]
    tail.close()


def test_rotation_is_detected_by_identity_not_by_size(log):
    """A replacement file smaller than the old one must still be picked up."""
    tail = LogTail(log)
    tail.poll()

    with log.open("a", encoding="utf-8") as fh:
        fh.write("x" * 500 + "\n")
    tail.poll()

    log.rename(log.with_suffix(".log.1"))
    log.write_text("tiny\n", encoding="utf-8")

    assert tail.poll() == ["tiny"]
    tail.close()


def test_a_missing_file_is_not_an_error(tmp_path):
    tail = LogTail(tmp_path / "never-created.log")
    assert tail.poll() == []
    tail.close()


def test_recovers_when_the_file_appears_later(tmp_path):
    p = tmp_path / "late.log"
    tail = LogTail(p)
    assert tail.poll() == []

    p.write_text("first\n", encoding="utf-8")
    assert tail.poll() == ["first"]
    tail.close()


def test_from_start_reads_existing_content(log):
    tail = LogTail(log, from_start=True)
    assert tail.poll() == ["existing line"]
    tail.close()


def test_a_tail_must_not_block_rotation(log):
    """The reason this module does not hold an fd, run rather than asserted.

    toolong's PollWatcher keeps one fd for the life of the tail. On Windows that
    makes the writer's own rollover fail with WinError 32, so such a tail would
    break clean-rag's logging rather than merely miss a rotation. This pins the
    platform behaviour that forced the open-read-close design.
    """
    fd = os.open(log, os.O_RDONLY)
    try:
        if sys.platform == "win32":
            with pytest.raises(PermissionError):
                log.rename(log.with_suffix(".log.1"))
        else:
            log.rename(log.with_suffix(".log.1"))
    finally:
        os.close(fd)


def test_polling_never_leaves_the_log_open(log):
    """A rotation must still succeed immediately after a poll."""
    tail = LogTail(log)
    tail.poll()

    with log.open("a", encoding="utf-8") as fh:
        fh.write("line\n")
    assert tail.poll() == ["line"]

    # This raises WinError 32 if poll() left a handle behind.
    log.rename(log.with_suffix(".log.1"))
    tail.close()


def test_a_truncated_log_is_read_from_the_start_again(log):
    tail = LogTail(log)
    tail.poll()

    with log.open("a", encoding="utf-8") as fh:
        fh.write("before truncate\n")
    assert tail.poll() == ["before truncate"]

    log.write_text("after truncate\n", encoding="utf-8")
    assert tail.poll() == ["after truncate"]
    tail.close()
