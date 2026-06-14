"""
Tests for scripts/rag-session-reset.py (SessionStart hook).

Clears the claudeboost_rag_ok sentinel. Always exits 0.
"""
from __future__ import annotations

import json
import pytest
from helpers import SCRIPTS_DIR, run_hook


def _session_start() -> dict:
    return {"hook_event_name": "SessionStart", "session_id": "test", "source": "startup"}


# ---------------------------------------------------------------------------
# Always exits 0
# ---------------------------------------------------------------------------

def test_always_exits_0(tmp_path):
    result = run_hook(
        "rag-session-reset.py",
        _session_start(),
        env_overrides={"TEMP": str(tmp_path)},
    )
    assert result.returncode == 0


def test_exits_0_when_sentinel_absent(tmp_path):
    # No sentinel file
    result = run_hook(
        "rag-session-reset.py",
        _session_start(),
        env_overrides={"TEMP": str(tmp_path)},
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Sentinel removal
# ---------------------------------------------------------------------------

def test_removes_sentinel_when_present(tmp_path):
    sentinel = tmp_path / "claudeboost_rag_ok"
    sentinel.touch()
    assert sentinel.exists()

    result = run_hook(
        "rag-session-reset.py",
        _session_start(),
        env_overrides={"TEMP": str(tmp_path)},
    )
    assert result.returncode == 0
    assert not sentinel.exists()


def test_no_error_when_sentinel_already_absent(tmp_path):
    # Sentinel was never created
    sentinel = tmp_path / "claudeboost_rag_ok"
    assert not sentinel.exists()

    result = run_hook(
        "rag-session-reset.py",
        _session_start(),
        env_overrides={"TEMP": str(tmp_path)},
    )
    assert result.returncode == 0
    assert b"error" not in result.stderr.lower()
    assert b"Traceback" not in result.stderr


# ---------------------------------------------------------------------------
# Output when sentinel was set (notification)
# ---------------------------------------------------------------------------

def test_outputs_context_when_sentinel_was_cleared(tmp_path):
    sentinel = tmp_path / "claudeboost_rag_ok"
    sentinel.touch()

    result = run_hook(
        "rag-session-reset.py",
        _session_start(),
        env_overrides={"TEMP": str(tmp_path)},
    )
    assert result.returncode == 0
    # Should print additionalContext about RAG being cleared
    if result.stdout.strip():
        output = json.loads(result.stdout)
        ctx = output.get("additionalContext", "")
        assert "RAG" in ctx


def test_silent_when_sentinel_was_not_set(tmp_path):
    # No sentinel → no notification output
    result = run_hook(
        "rag-session-reset.py",
        _session_start(),
        env_overrides={"TEMP": str(tmp_path)},
    )
    assert result.returncode == 0
    # Should produce no output (silent startup)
    assert result.stdout.strip() == b""


# ---------------------------------------------------------------------------
# Exception branch in unlink (lines 34-35): best-effort clear swallows errors
# ---------------------------------------------------------------------------

def test_unlink_exception_is_swallowed(tmp_path, monkeypatch):
    """If sentinel.unlink() raises, the hook still exits 0 (best-effort clear)."""
    import importlib.util
    import sys
    from pathlib import Path
    from unittest.mock import patch

    scripts_dir = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "rag_session_reset", scripts_dir / "rag-session-reset.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(scripts_dir))
    spec.loader.exec_module(mod)

    sentinel_path = tmp_path / "claudeboost_rag_ok"
    sentinel_path.touch()  # exists so was_set=True, then unlink raises

    with patch("pathlib.Path.unlink", side_effect=OSError("permission denied")):
        with patch.dict("os.environ", {"TEMP": str(tmp_path)}):
            rc = mod.main()

    assert rc == 0
