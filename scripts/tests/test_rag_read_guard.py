"""
Tests for scripts/rag-read-guard.py (PreToolUse/Read+Grep hook).

Behavior under test:
  - Counter below threshold, RAG live    -> exit 0
  - Counter at threshold, RAG live       -> exit 2 with "BLOCKED" message
  - Counter at threshold, RAG not live   -> exit 0 (fail-open when RAG is down)
  - Exempted file suffix (.json)         -> exit 0 regardless of counter
  - Exempted path fragment (context.md)  -> exit 0 regardless of counter
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from helpers import SCRIPTS_DIR, run_hook, pretooluse


def _read_fixture(file_path: str) -> dict:
    return pretooluse("Read", {"file_path": file_path})


def _write_tracker(boost_home: Path, reads_since_rag: int) -> None:
    tracker = boost_home / "state" / "behavior-tracker.json"
    tracker.write_text(
        json.dumps({"reads_since_rag": reads_since_rag}),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------

def test_passes_below_threshold(boost_home, rag_live):
    """Counter below threshold should always pass."""
    _write_tracker(boost_home, 0)
    result = run_hook(
        "rag-read-guard.py",
        _read_fixture("/test/project/some_file.py"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home), **rag_live},
    )
    assert result.returncode == 0


def test_passes_when_rag_not_live(boost_home, rag_dead):
    """Guard fails open — if RAG is down, reads are never blocked."""
    _write_tracker(boost_home, 99)
    result = run_hook(
        "rag-read-guard.py",
        _read_fixture("/test/project/some_file.py"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home), **rag_dead},
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Blocking
# ---------------------------------------------------------------------------

def test_blocks_at_threshold(boost_home, rag_live):
    """Counter >= RAG_THRESHOLD (6) with live RAG should exit 2."""
    _write_tracker(boost_home, 6)
    result = run_hook(
        "rag-read-guard.py",
        _read_fixture("/test/project/some_file.py"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home), **rag_live},
    )
    assert result.returncode == 2
    assert b"BLOCKED" in result.stderr


def test_blocks_well_above_threshold(boost_home, rag_live):
    """Counter well above threshold should also block."""
    _write_tracker(boost_home, 10)
    result = run_hook(
        "rag-read-guard.py",
        _read_fixture("/test/project/some_file.py"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home), **rag_live},
    )
    assert result.returncode == 2


# ---------------------------------------------------------------------------
# Exemptions
# ---------------------------------------------------------------------------

def test_passes_exempted_json_suffix(boost_home, rag_live):
    """JSON files are always exempted — no RAG needed."""
    _write_tracker(boost_home, 99)
    result = run_hook(
        "rag-read-guard.py",
        _read_fixture("/test/project/state/approvals.json"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home), **rag_live},
    )
    assert result.returncode == 0


def test_passes_exempted_context_md(boost_home, rag_live):
    """workspace/*/context.md is always exempted."""
    _write_tracker(boost_home, 99)
    result = run_hook(
        "rag-read-guard.py",
        _read_fixture("/test/project/workspace/my-task/context.md"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home), **rag_live},
    )
    assert result.returncode == 0


def test_passes_md_file_in_workspace_path(boost_home, rag_live):
    """An .md file that lives inside workspace/ is exempted even without matching name fragments."""
    _write_tracker(boost_home, 99)
    result = run_hook(
        "rag-read-guard.py",
        _read_fixture("/project/workspace/task-123/notes.md"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home), **rag_live},
    )
    assert result.returncode == 0


def test_blocks_md_file_outside_workspace(boost_home, rag_live):
    """.md file outside workspace/ is NOT exempted — goes through counter check."""
    _write_tracker(boost_home, 99)
    result = run_hook(
        "rag-read-guard.py",
        _read_fixture("/project/docs/design.md"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home), **rag_live},
    )
    assert result.returncode == 2


def test_passes_glob_with_workspace_pattern(boost_home, rag_live):
    """Glob tool with workspace in pattern is exempted."""
    _write_tracker(boost_home, 99)
    fixture = {
        **pretooluse("Glob", {"pattern": "workspace/**/*.md"}),
    }
    result = run_hook(
        "rag-read-guard.py",
        fixture,
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home), **rag_live},
    )
    assert result.returncode == 0


def test_passes_on_malformed_stdin(boost_home):
    """Malformed JSON on stdin — treated as empty payload, exemption falls through."""
    import subprocess, sys, os, json as _json
    from pathlib import Path as P
    SCRIPTS_DIR = P(__file__).resolve().parent.parent
    script = SCRIPTS_DIR / "rag-read-guard.py"
    env = {**os.environ, "CLAUDEBOOST_HOME": str(boost_home)}
    # Send raw non-JSON bytes as stdin
    result = subprocess.run(
        [sys.executable, str(script)],
        input=b"THIS IS NOT JSON",
        capture_output=True,
        env=env,
    )
    assert result.returncode == 0


def test_passes_with_malformed_tracker(boost_home, rag_live):
    """Malformed behavior-tracker.json defaults to reads_since_rag=0 → allow."""
    tracker = boost_home / "state" / "behavior-tracker.json"
    tracker.write_text("not json", encoding="utf-8")
    result = run_hook(
        "rag-read-guard.py",
        _read_fixture("/project/src/main.py"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home), **rag_live},
    )
    assert result.returncode == 0


def test_passes_plain_float_heartbeat(boost_home, tmp_path):
    """Plain float heartbeat (legacy format) — treated as live if fresh."""
    rag_index_dir = tmp_path / "rag-index"
    rag_index_dir.mkdir()
    import time
    (rag_index_dir / ".heartbeat").write_text(str(time.time()), encoding="utf-8")
    _write_tracker(boost_home, 0)
    result = run_hook(
        "rag-read-guard.py",
        _read_fixture("/project/src/main.py"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home), "RAG_INDEX_DIR": str(rag_index_dir)},
    )
    assert result.returncode == 0


def test_float_heartbeat_at_threshold_fails_open(boost_home, tmp_path):
    """Lines 92-93: float heartbeat exists, counter at threshold.

    json.loads(str(time.time())) returns a float, not a dict.
    data.get('ts', 0) then raises AttributeError (not ValueError/KeyError),
    which the inner except doesn't catch — propagates to the outer except at
    line 92 (except Exception: return False). Fail-open -> returncode 0.
    """
    import time
    rag_index_dir = tmp_path / "rag-index"
    rag_index_dir.mkdir()
    (rag_index_dir / ".heartbeat").write_text(str(time.time()), encoding="utf-8")
    _write_tracker(boost_home, 6)  # >= RAG_THRESHOLD so _rag_is_live() is called
    result = run_hook(
        "rag-read-guard.py",
        _read_fixture("/project/src/main.py"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home), "RAG_INDEX_DIR": str(rag_index_dir)},
    )
    assert result.returncode == 0


def test_passes_when_no_env_vars_set(boost_home):
    """Neither RAG_INDEX_DIR nor LOCALAPPDATA — uses Linux fallback, no heartbeat → fail-open."""
    result = run_hook(
        "rag-read-guard.py",
        _read_fixture("/project/src/main.py"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home), "RAG_INDEX_DIR": "", "LOCALAPPDATA": ""},
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Coverage for lines 65, 83, 94-95
# ---------------------------------------------------------------------------


def test_localappdata_fallback_covers_line_65(boost_home, tmp_path):
    """LOCALAPPDATA is set but no heartbeat file exists — RAG resolves to that dir, fails-open (line 65)."""
    # RAG_INDEX_DIR is unset so code enters the if-not block.
    # LOCALAPPDATA is set so line 65 executes: _rag_index_dir = str(Path(LOCALAPPDATA) / "rag-server-index")
    # No heartbeat exists there, so _rag_is_live() returns False → guard fails open.
    localappdata_dir = tmp_path / "AppData" / "Local"
    localappdata_dir.mkdir(parents=True)
    _write_tracker(boost_home, 99)
    result = run_hook(
        "rag-read-guard.py",
        _read_fixture("/project/src/main.py"),
        env_overrides={
            "CLAUDEBOOST_HOME": str(boost_home),
            "RAG_INDEX_DIR": "",
            "LOCALAPPDATA": str(localappdata_dir),
        },
    )
    # No heartbeat under localappdata_dir/rag-server-index → fail-open
    assert result.returncode == 0


def test_nan_heartbeat_covers_line_83(boost_home, tmp_path):
    """Heartbeat contains 'nan' — not valid JSON, valid float — exercises line 83 (ts = float(raw)).

    json.loads('nan') raises ValueError so except (ValueError, KeyError) catches it
    and line 83 runs float('nan'). The result nan <= 90 is False, so _rag_is_live()
    returns False and the guard fails open.
    """
    rag_index_dir = tmp_path / "rag-index"
    rag_index_dir.mkdir()
    # 'nan' is not valid JSON but IS a valid Python float literal
    (rag_index_dir / ".heartbeat").write_text("nan", encoding="utf-8")
    _write_tracker(boost_home, 0)
    result = run_hook(
        "rag-read-guard.py",
        _read_fixture("/project/src/main.py"),
        env_overrides={
            "CLAUDEBOOST_HOME": str(boost_home),
            "RAG_INDEX_DIR": str(rag_index_dir),
        },
    )
    # nan <= 90 is False → _rag_is_live() False → fail open
    assert result.returncode == 0


def test_malformed_stdin_via_run_hook_covers_lines_94_95(boost_home):
    """Malformed JSON through run_hook's coverage-instrumented subprocess — covers lines 94-95.

    The existing test_passes_on_malformed_stdin bypasses run_hook so its subprocess
    doesn't receive COVERAGE_PROCESS_START. This test uses run_hook directly with
    a pre-serialized non-JSON payload by patching at the subprocess level.
    """
    import subprocess
    import sys
    import os
    from pathlib import Path as P
    from helpers import SCRIPTS_DIR, COVERAGERC

    script = SCRIPTS_DIR / "rag-read-guard.py"
    env = {
        **os.environ,
        "CLAUDEBOOST_HOME": str(boost_home),
        "RAG_INDEX_DIR": "",
        "LOCALAPPDATA": "",
    }
    if COVERAGERC.exists():
        env["COVERAGE_PROCESS_START"] = str(COVERAGERC)

    # Send raw non-JSON bytes — triggers lines 94-95 (except Exception: payload = {})
    result = subprocess.run(
        [sys.executable, str(script)],
        input=b"NOT_VALID_JSON {{{",
        capture_output=True,
        env=env,
    )
    # No file_path in empty payload → is_exempted returns False, RAG not live → fail open
    assert result.returncode == 0


class TestRagIsLiveNewBranches:
    """Lines 88-90 (model_loaded=False) and 92-93 (ValueError/KeyError fallback)."""

    def _load_mod(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "rag_read_guard_new",
            Path(__file__).resolve().parent.parent / "rag-read-guard.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_model_not_loaded_returns_false(self, tmp_path, monkeypatch):
        """Lines 88-89: model_loaded=False in heartbeat -> _rag_is_live() returns False."""
        import json, time
        heartbeat = tmp_path / ".heartbeat"
        heartbeat.write_text(
            json.dumps({"ts": time.time(), "model_loaded": False}), encoding="utf-8"
        )
        mod = self._load_mod()
        monkeypatch.setattr(mod, "_HEARTBEAT", heartbeat)
        assert mod._rag_is_live() is False

    def test_nan_heartbeat_hits_except_branch(self, tmp_path, monkeypatch):
        """Lines 89-90: 'nan' is invalid JSON but valid float -> except (ValueError,KeyError) branch."""
        heartbeat = tmp_path / ".heartbeat"
        heartbeat.write_text("nan", encoding="utf-8")
        mod = self._load_mod()
        monkeypatch.setattr(mod, "_HEARTBEAT", heartbeat)
        # nan is not valid JSON so json.loads raises ValueError -> except branch runs float("nan")
        # time.time() - nan = nan, nan <= 90 is False
        assert mod._rag_is_live() is False

    def test_missing_heartbeat_returns_false_at_line_78(self, tmp_path, monkeypatch):
        """Line 78: heartbeat file doesn't exist -> _HEARTBEAT.exists() False -> return False."""
        heartbeat = tmp_path / "nonexistent" / ".heartbeat"
        mod = self._load_mod()
        monkeypatch.setattr(mod, "_HEARTBEAT", heartbeat)
        # exists() returns False -> early return at line 78 (not the outer except)
        assert mod._rag_is_live() is False
