"""Hook logs must not grow without limit, and rotating must never raise.

code-pattern-inject.log reached 60916 lines before this existed. Each hook is its
own short lived process, so the usual RotatingFileHandler is the wrong tool: two
of them crossing the threshold together race the same rename, and on Windows that
raises PermissionError on every emit.
"""
import sys
from pathlib import Path

import pytest

CLEAN_RAG = Path(__file__).resolve().parents[1]
HOOKS = CLEAN_RAG / "hooks"
for p in (str(CLEAN_RAG), str(HOOKS)):
    if p not in sys.path:
        sys.path.insert(0, p)

from _log_rotate import DEFAULT_MAX_BYTES, trim_if_large  # noqa: E402


def test_small_log_is_left_alone(tmp_path):
    log = tmp_path / "a.log"
    log.write_text("short\n", encoding="utf-8")
    assert trim_if_large(log, max_bytes=1024) is False
    assert log.read_text(encoding="utf-8") == "short\n"
    assert not (tmp_path / "a.log.1").exists()


def test_oversized_log_is_moved_aside(tmp_path):
    log = tmp_path / "a.log"
    log.write_text("x" * 5000, encoding="utf-8")
    assert trim_if_large(log, max_bytes=1000) is True
    assert not log.exists(), "the live log should have been moved, not copied"
    assert (tmp_path / "a.log.1").read_text(encoding="utf-8") == "x" * 5000


def test_rotation_keeps_exactly_one_generation(tmp_path):
    log = tmp_path / "a.log"
    previous = tmp_path / "a.log.1"
    previous.write_text("older", encoding="utf-8")
    log.write_text("y" * 5000, encoding="utf-8")

    assert trim_if_large(log, max_bytes=1000) is True
    assert previous.read_text(encoding="utf-8") == "y" * 5000, "did not replace .1"
    assert not (tmp_path / "a.log.2").exists(), "generations must not accumulate"


def test_missing_file_is_not_an_error(tmp_path):
    assert trim_if_large(tmp_path / "nope.log") is False


def test_directory_in_place_of_a_file_is_not_an_error(tmp_path):
    d = tmp_path / "a.log"
    d.mkdir()
    assert trim_if_large(d, max_bytes=1) is False


def test_exactly_at_the_threshold_does_not_rotate(tmp_path):
    """Boundary. The check is > max_bytes, so equal must be left alone."""
    log = tmp_path / "a.log"
    log.write_bytes(b"z" * 1000)
    assert trim_if_large(log, max_bytes=1000) is False
    assert log.exists()


def test_one_byte_over_the_threshold_rotates(tmp_path):
    log = tmp_path / "a.log"
    log.write_bytes(b"z" * 1001)
    assert trim_if_large(log, max_bytes=1000) is True


def test_a_locked_target_does_not_raise(tmp_path, monkeypatch):
    """The Windows case: another hook holds the file, so the rename fails.

    The point of the whole module is that this degrades to "not rotated this
    time" instead of raising inside a PreToolUse hook.
    """
    log = tmp_path / "a.log"
    log.write_text("q" * 5000, encoding="utf-8")

    import _log_rotate

    def boom(*_a, **_k):
        raise PermissionError(32, "The process cannot access the file")

    monkeypatch.setattr(Path, "rename", boom)
    assert _log_rotate.trim_if_large(log, max_bytes=1000) is False
    assert log.exists(), "the log must survive a failed rotation"


def test_default_cap_matches_the_server_log_cap():
    """server/app.py uses 5 MB for server.log. One number, not two."""
    assert DEFAULT_MAX_BYTES == 5 * 1024 * 1024


@pytest.mark.parametrize("hook", ["code-pattern-inject.py", "rag-enforce.py"])
def test_hook_calls_the_rotator_before_configuring_logging(hook):
    """Order matters. Rotating after the handler opens the file does nothing."""
    text = (HOOKS / hook).read_text(encoding="utf-8")
    assert "trim_if_large" in text, f"{hook} does not rotate its log"
    assert text.index("trim_if_large") < text.index("logging.basicConfig"), (
        f"{hook} rotates after opening the log, which has no effect"
    )
