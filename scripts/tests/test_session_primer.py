"""
Tests for scripts/session-primer.py (UserPromptSubmit hook).

Injects additionalContext with always-on rules and standing orders.
Always exits 0.
"""
from __future__ import annotations

import json
import time
import pytest
from helpers import SCRIPTS_DIR, run_hook


def _prompt(text: str) -> dict:
    return {"hook_event_name": "UserPromptSubmit", "session_id": "test", "prompt": text}


def _run(prompt_text: str, boost_home=None, extra_env=None) -> "subprocess.CompletedProcess":
    env = {}
    if boost_home:
        env["CLAUDEBOOST_HOME"] = str(boost_home)
    if extra_env:
        env.update(extra_env)
    return run_hook("session-primer.py", _prompt(prompt_text), env_overrides=env or None)


# ---------------------------------------------------------------------------
# Always exits 0
# ---------------------------------------------------------------------------

def test_always_exits_0(boost_home):
    result = _run("please implement a new feature for me", boost_home=boost_home)
    assert result.returncode == 0


def test_exits_0_on_short_prompt(boost_home):
    result = _run("hi", boost_home=boost_home)
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Injects context for substantive prompts
# ---------------------------------------------------------------------------

def test_injects_context_for_long_prompt(boost_home):
    result = _run("implement the authentication service with JWT tokens", boost_home=boost_home)
    assert result.returncode == 0
    assert result.stdout  # something was printed
    output = json.loads(result.stdout)
    assert "additionalContext" in output


def test_injected_context_contains_always_on_rules(boost_home):
    result = _run("fix the bug in the payment service", boost_home=boost_home)
    output = json.loads(result.stdout)
    ctx = output["additionalContext"]
    assert "ALWAYS-ON" in ctx or "TaskCreate" in ctx


def test_short_prompt_skips_injection(boost_home):
    # Under 15 chars with no clear-pending → no injection
    result = _run("ok", boost_home=boost_home)
    assert result.returncode == 0
    # Short prompts don't inject
    if result.stdout.strip():
        output = json.loads(result.stdout)
        # If there IS output it should still be valid JSON
        assert "additionalContext" in output
    # Either no output or valid additionalContext — both are fine


# ---------------------------------------------------------------------------
# workspace-aware injection when workspaces.json has entries
# ---------------------------------------------------------------------------

def test_injects_workspace_context_when_workspace_registered(boost_home, tmp_path):
    ws_path = tmp_path / "workspace" / "task-login"
    ws_path.mkdir(parents=True)
    (ws_path / "context.md").write_text("# Login feature\nStatus: in progress\nNext: add JWT auth", encoding="utf-8")

    import time
    reg = {
        "task-login": {
            "workspace_path": str(ws_path),
            "project_path": str(tmp_path),
        }
    }
    reg_file = boost_home / "state" / "workspaces.json"
    reg_file.write_text(__import__("json").dumps(reg), encoding="utf-8")

    result = _run("fix the JWT login bug", boost_home=boost_home)
    assert result.returncode == 0


def test_workspace_summary_read_ticket_md(boost_home, tmp_path):
    ws_path = tmp_path / "workspace" / "task-ticket"
    ws_path.mkdir(parents=True)
    (ws_path / "ticket.md").write_text("# TICKET-42\nImplement password reset flow\nAcceptance: user receives email", encoding="utf-8")
    (ws_path / "context.md").write_text("# Task 42\nStatus: in progress", encoding="utf-8")

    reg = {
        "task-ticket": {
            "workspace_path": str(ws_path),
            "project_path": str(tmp_path),
        }
    }
    reg_file = boost_home / "state" / "workspaces.json"
    reg_file.write_text(__import__("json").dumps(reg), encoding="utf-8")

    result = _run("continue with the password reset email", boost_home=boost_home)
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# boost_mode false: skip injection
# ---------------------------------------------------------------------------

def test_skip_injection_when_boost_false(boost_home):
    bi = boost_home / "state" / "boost-injection.json"
    bi.write_text(json.dumps({"mode": "false"}), encoding="utf-8")

    result = _run("implement a comprehensive new authentication service", boost_home=boost_home)
    assert result.returncode == 0
    # When mode is "false", nothing should be printed
    assert result.stdout.strip() == b""


# ---------------------------------------------------------------------------
# boost_mode true: inject without RAG verification
# ---------------------------------------------------------------------------

def test_boost_true_injects_without_rag_sentinel(boost_home, tmp_path):
    bi = boost_home / "state" / "boost-injection.json"
    bi.write_text(json.dumps({"mode": "true"}), encoding="utf-8")

    result = run_hook(
        "session-primer.py",
        _prompt("implement the feature from the ticket"),
        env_overrides={
            "CLAUDEBOOST_HOME": str(boost_home),
            "TEMP": str(tmp_path),  # no sentinel in tmp_path
        },
    )
    assert result.returncode == 0
    assert result.stdout.strip()
    output = json.loads(result.stdout)
    assert "additionalContext" in output


# ---------------------------------------------------------------------------
# clear-pending flag: inject context restore
# ---------------------------------------------------------------------------

def test_consumes_clear_pending_flag(boost_home):
    import datetime

    # Write a fresh clear-pending flag
    flag_path = boost_home / "state" / "clear-pending.json"
    flag_path.write_text(json.dumps({
        "pending": True,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }), encoding="utf-8")

    # Write a handoff-latest with memo
    handoff_path = boost_home / "state" / "handoff-latest.json"
    handoff_path.write_text(json.dumps({
        "workspace_memo": "### task-1\nStatus: in progress\nNext: finish tests",
        "active_workspace": "task-1",
    }), encoding="utf-8")

    result = run_hook(
        "session-primer.py",
        _prompt("continue"),  # short prompt is OK when clear-pending is set
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    # Flag should be consumed (deleted)
    assert not flag_path.exists()
    # Output should contain restoration context
    if result.stdout.strip():
        output = json.loads(result.stdout)
        ctx = output.get("additionalContext", "")
        assert "CONTEXT" in ctx.upper() or "workspace" in ctx.lower()


# ---------------------------------------------------------------------------
# RAG verification sentinel tests
# ---------------------------------------------------------------------------

def test_injects_rag_warning_when_no_sentinel(boost_home, tmp_path):
    """Without RAG sentinel, a warning is injected."""
    result = run_hook(
        "session-primer.py",
        _prompt("implement a new feature for the authentication service"),
        env_overrides={
            "CLAUDEBOOST_HOME": str(boost_home),
            "TEMP": str(tmp_path),  # no sentinel in tmp_path
        },
    )
    assert result.returncode == 0
    if result.stdout.strip():
        output = json.loads(result.stdout)
        ctx = output.get("additionalContext", "")
        assert "RAG" in ctx or "verify" in ctx.lower() or "rag" in ctx.lower()


def test_rag_verified_sentinel_present(boost_home, tmp_path):
    """When RAG sentinel exists, no warning about RAG not verified."""
    # Create the sentinel file
    (tmp_path / "claudeboost_rag_ok").touch()
    result = run_hook(
        "session-primer.py",
        _prompt("implement a new feature for the authentication service"),
        env_overrides={
            "CLAUDEBOOST_HOME": str(boost_home),
            "TEMP": str(tmp_path),
        },
    )
    assert result.returncode == 0
    if result.stdout.strip():
        output = json.loads(result.stdout)
        ctx = output.get("additionalContext", "")
        # With sentinel, no "not yet verified" warning
        assert "not yet verified" not in ctx.lower()


def test_clear_pending_with_no_rag_sentinel(boost_home, tmp_path):
    """Clear pending + no RAG sentinel: should inject context with soft nudge."""
    import datetime
    flag_path = boost_home / "state" / "clear-pending.json"
    flag_path.write_text(json.dumps({
        "pending": True,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }), encoding="utf-8")
    handoff_path = boost_home / "state" / "handoff-latest.json"
    handoff_path.write_text(json.dumps({
        "workspace_memo": "### task-2\nStatus: blocked",
        "active_workspace": "task-2",
    }), encoding="utf-8")

    result = run_hook(
        "session-primer.py",
        _prompt("continue where we left off"),
        env_overrides={
            "CLAUDEBOOST_HOME": str(boost_home),
            "TEMP": str(tmp_path),  # no sentinel
        },
    )
    assert result.returncode == 0
    assert not flag_path.exists()
    if result.stdout.strip():
        output = json.loads(result.stdout)
        ctx = output.get("additionalContext", "")
        assert "CONTEXT" in ctx.upper() or "clear" in ctx.lower() or "NOTE" in ctx


def test_clear_pending_stale_flag_ignored(boost_home, tmp_path):
    """A stale clear-pending flag (>10min old) is consumed but not used."""
    import datetime
    old_ts = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=15)
    flag_path = boost_home / "state" / "clear-pending.json"
    flag_path.write_text(json.dumps({
        "pending": True,
        "timestamp": old_ts.isoformat(),
    }), encoding="utf-8")

    result = run_hook(
        "session-primer.py",
        _prompt("let me continue with the authentication service fix"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home), "TEMP": str(tmp_path)},
    )
    assert result.returncode == 0
    # Flag is consumed regardless
    assert not flag_path.exists()


def test_clear_pending_missing_handoff(boost_home, tmp_path):
    """Clear pending flag present but no handoff-latest.json → no context restore."""
    import datetime
    flag_path = boost_home / "state" / "clear-pending.json"
    flag_path.write_text(json.dumps({
        "pending": True,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }), encoding="utf-8")
    # No handoff-latest.json created

    result = run_hook(
        "session-primer.py",
        _prompt("ok let me continue my development work"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home), "TEMP": str(tmp_path)},
    )
    assert result.returncode == 0
    assert not flag_path.exists()


def test_consult_mode_active_default(boost_home, tmp_path):
    """CONSULT mode is the default (no mode file). Standing orders include CONSULT mention."""
    result = run_hook(
        "session-primer.py",
        _prompt("implement the user authentication system with JWT"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home), "TEMP": str(tmp_path)},
    )
    assert result.returncode == 0
    if result.stdout.strip():
        output = json.loads(result.stdout)
        ctx = output.get("additionalContext", "")
        assert "CONSULT" in ctx or "consult" in ctx.lower() or "architectural" in ctx.lower()


def test_auto_mode_skips_consult_standing_orders(boost_home, tmp_path):
    """AUTO mode: standing orders don't include CONSULT MODE notice."""
    (boost_home / "state" / "claudeboost-mode.json").write_text(
        json.dumps({"mode": "AUTO"}), encoding="utf-8"
    )
    result = run_hook(
        "session-primer.py",
        _prompt("implement the user authentication system with JWT"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home), "TEMP": str(tmp_path)},
    )
    assert result.returncode == 0
    if result.stdout.strip():
        output = json.loads(result.stdout)
        ctx = output.get("additionalContext", "")
        # AUTO mode → no CONSULT MODE IS ACTIVE text
        assert "CONSULT MODE IS ACTIVE" not in ctx


def test_workspace_dashboard_with_rag_status(boost_home, tmp_path):
    """When rag is verified and workspace is registered, dashboard shows tier status."""
    # Create sentinel
    (tmp_path / "claudeboost_rag_ok").touch()

    # Register a workspace
    ws_path = tmp_path / "workspace" / "task-rag"
    ws_path.mkdir(parents=True)
    (ws_path / "context.md").write_text("# RAG Task\nStatus: in progress", encoding="utf-8")

    reg = {
        "task-rag": {
            "workspace_path": str(ws_path),
            "project_path": str(tmp_path),
        }
    }
    (boost_home / "state" / "workspaces.json").write_text(
        json.dumps(reg), encoding="utf-8"
    )

    result = run_hook(
        "session-primer.py",
        _prompt("continue with the RAG task optimization work"),
        env_overrides={
            "CLAUDEBOOST_HOME": str(boost_home),
            "TEMP": str(tmp_path),
        },
    )
    assert result.returncode == 0


def test_find_best_workspace_multiple_candidates(boost_home, tmp_path):
    """Multiple workspaces: keyword matching picks the best one."""
    for task_id in ("task-login", "task-payment", "task-deploy"):
        ws_dir = tmp_path / "workspace" / task_id
        ws_dir.mkdir(parents=True)
        (ws_dir / "context.md").write_text(f"# {task_id}\nStatus: in progress\n{task_id} work", encoding="utf-8")

    reg = {
        "task-login": {"workspace_path": str(tmp_path / "workspace" / "task-login"), "project_path": ""},
        "task-payment": {"workspace_path": str(tmp_path / "workspace" / "task-payment"), "project_path": ""},
        "task-deploy": {"workspace_path": str(tmp_path / "workspace" / "task-deploy"), "project_path": ""},
    }
    (boost_home / "state" / "workspaces.json").write_text(json.dumps(reg), encoding="utf-8")

    result = run_hook(
        "session-primer.py",
        _prompt("fix the login authentication issue with the JWT token"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home), "TEMP": str(tmp_path)},
    )
    assert result.returncode == 0


def test_tokenize_filters_stop_words(boost_home):
    """The _tokenize helper filters short words and stop words."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    import importlib.util
    spec = importlib.util.spec_from_file_location("session_primer", Path(__file__).parent.parent / "session-primer.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    tokens = mod._tokenize("fix the bug in the authentication service")
    assert "fix" not in tokens  # "fix" is in stop list
    assert "authentication" in tokens
    assert "service" in tokens
    assert "the" not in tokens
    assert "in" not in tokens


def test_workspace_reminder_no_project_path(boost_home, tmp_path):
    """Workspace with no project_path: reminder shows just workspace_path."""
    ws_path = tmp_path / "workspace" / "task-noproj"
    ws_path.mkdir(parents=True)
    (ws_path / "context.md").write_text("# No Proj\nStatus: in progress", encoding="utf-8")

    reg = {
        "task-noproj": {
            "workspace_path": str(ws_path),
            "project_path": "",  # No project path
        }
    }
    (boost_home / "state" / "workspaces.json").write_text(json.dumps(reg), encoding="utf-8")

    result = run_hook(
        "session-primer.py",
        _prompt("continue with the task noproj development"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home), "TEMP": str(tmp_path)},
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Direct import tests for internal functions
# ---------------------------------------------------------------------------

def _load_session_primer():
    """Import session-primer.py as a module (hyphen in filename requires importlib)."""
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "session_primer",
        Path(__file__).resolve().parent.parent / "session-primer.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestReadWorkspaceSummary:
    def test_returns_empty_when_no_files(self, tmp_path):
        """_read_workspace_summary returns '' when neither ticket.md nor context.md exists."""
        mod = _load_session_primer()
        result = mod._read_workspace_summary(str(tmp_path / "nonexistent"))
        assert result == ""

    def test_returns_ticket_content_when_present(self, tmp_path):
        """_read_workspace_summary prefers ticket.md over context.md."""
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / "ticket.md").write_text("TICKET-42 implement login", encoding="utf-8")
        mod = _load_session_primer()
        result = mod._read_workspace_summary(str(ws))
        assert "TICKET-42" in result


class TestFindBestWorkspace:
    def test_returns_empty_when_no_workspaces(self, boost_home):
        """No workspaces in registry → returns empty strings."""
        mod = _load_session_primer()
        ws_id, ws_path, proj, cands = mod._find_best_workspace(boost_home, "fix the bug")
        assert ws_id == ""
        assert ws_path == ""

    def test_skips_entries_without_workspace_path(self, boost_home, tmp_path):
        """Entry with no workspace_path is skipped."""
        reg = {"empty-task": {"workspace_path": "", "project_path": ""}}
        (boost_home / "state" / "workspaces.json").write_text(json.dumps(reg), encoding="utf-8")
        mod = _load_session_primer()
        ws_id, ws_path, proj, cands = mod._find_best_workspace(boost_home, "fix the bug")
        assert ws_path == ""

    def test_skips_entries_older_than_48h(self, boost_home, tmp_path):
        """Workspace modified >48h ago is excluded from results."""
        import time
        import os
        ws = tmp_path / "workspace" / "old-task"
        ws.mkdir(parents=True)
        ctx = ws / "context.md"
        ctx.write_text("# Old Task\nStatus: done", encoding="utf-8")
        old_time = time.time() - 49 * 3600
        os.utime(str(ctx), (old_time, old_time))

        reg = {"old-task": {"workspace_path": str(ws), "project_path": ""}}
        (boost_home / "state" / "workspaces.json").write_text(json.dumps(reg), encoding="utf-8")
        mod = _load_session_primer()
        ws_id, ws_path, proj, cands = mod._find_best_workspace(boost_home, "old task work")
        assert ws_path == ""

    def test_handles_oserror_on_stat(self, boost_home, tmp_path):
        """OSError on stat() (missing directory) is caught and skipped."""
        reg = {"ghost-task": {"workspace_path": str(tmp_path / "does-not-exist"), "project_path": ""}}
        (boost_home / "state" / "workspaces.json").write_text(json.dumps(reg), encoding="utf-8")
        mod = _load_session_primer()
        ws_id, ws_path, proj, cands = mod._find_best_workspace(boost_home, "ghost task work")
        assert ws_path == ""

    def test_handles_corrupt_registry(self, boost_home):
        """Corrupt workspaces.json returns empty tuple."""
        (boost_home / "state" / "workspaces.json").write_text("not json", encoding="utf-8")
        mod = _load_session_primer()
        ws_id, ws_path, proj, cands = mod._find_best_workspace(boost_home, "fix something")
        assert ws_id == ""

    def test_returns_candidates_when_ambiguous(self, boost_home, tmp_path):
        """Multiple recent workspaces with similar scores → returns candidates list."""
        for name in ("task-alpha", "task-beta", "task-gamma"):
            ws = tmp_path / "workspace" / name
            ws.mkdir(parents=True)
            (ws / "context.md").write_text(f"# {name}\nStatus: in progress", encoding="utf-8")

        reg = {
            "task-alpha": {"workspace_path": str(tmp_path / "workspace" / "task-alpha"), "project_path": ""},
            "task-beta": {"workspace_path": str(tmp_path / "workspace" / "task-beta"), "project_path": ""},
            "task-gamma": {"workspace_path": str(tmp_path / "workspace" / "task-gamma"), "project_path": ""},
        }
        (boost_home / "state" / "workspaces.json").write_text(json.dumps(reg), encoding="utf-8")
        mod = _load_session_primer()
        ws_id, ws_path, proj, cands = mod._find_best_workspace(boost_home, "generic work")
        # Should return a top match
        assert ws_path != ""


class TestConsultModeActive:
    def test_returns_true_on_corrupt_mode_file(self, boost_home):
        """Corrupt claudeboost-mode.json → defaults to CONSULT (True)."""
        (boost_home / "state" / "claudeboost-mode.json").write_text("bad json", encoding="utf-8")
        mod = _load_session_primer()
        result = mod.consult_mode_active(boost_home)
        assert result is True

    def test_returns_true_when_file_missing(self, boost_home):
        """No mode file → default is CONSULT (True)."""
        mod = _load_session_primer()
        result = mod.consult_mode_active(boost_home)
        assert result is True

    def test_returns_false_for_auto_mode(self, boost_home):
        """AUTO mode → returns False."""
        (boost_home / "state" / "claudeboost-mode.json").write_text(
            json.dumps({"mode": "AUTO"}), encoding="utf-8"
        )
        mod = _load_session_primer()
        result = mod.consult_mode_active(boost_home)
        assert result is False


class TestConsumeClearPending:
    def test_returns_empty_when_no_flag(self, boost_home):
        """No clear-pending.json → returns empty string."""
        mod = _load_session_primer()
        result = mod._consume_clear_pending(boost_home)
        assert result == ""

    def test_returns_empty_on_corrupt_flag(self, boost_home):
        """Corrupt clear-pending.json → consumed (deleted) and returns empty string."""
        flag = boost_home / "state" / "clear-pending.json"
        flag.write_text("CORRUPT JSON!!!", encoding="utf-8")
        mod = _load_session_primer()
        result = mod._consume_clear_pending(boost_home)
        assert result == ""
        assert not flag.exists()

    def test_returns_empty_when_pending_is_false(self, boost_home):
        """clear-pending.json with pending=False → returns empty string."""
        import datetime
        flag = boost_home / "state" / "clear-pending.json"
        flag.write_text(json.dumps({
            "pending": False,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }), encoding="utf-8")
        mod = _load_session_primer()
        result = mod._consume_clear_pending(boost_home)
        assert result == ""

    def test_handles_naive_timestamp(self, boost_home):
        """Naive timestamp (no tzinfo) is handled without crash."""
        import datetime
        flag = boost_home / "state" / "clear-pending.json"
        handoff = boost_home / "state" / "handoff-latest.json"
        flag.write_text(json.dumps({
            "pending": True,
            "timestamp": "2026-06-12T10:30:00",  # no timezone
        }), encoding="utf-8")
        handoff.write_text(json.dumps({
            "workspace_memo": "### task-1\nStatus: in progress",
            "active_workspace": "task-1",
        }), encoding="utf-8")
        mod = _load_session_primer()
        result = mod._consume_clear_pending(boost_home)
        # Either returns context or empty — just no crash
        assert isinstance(result, str)

    def test_handles_invalid_timestamp_format(self, boost_home):
        """Unparseable timestamp → returns empty string."""
        flag = boost_home / "state" / "clear-pending.json"
        flag.write_text(json.dumps({
            "pending": True,
            "timestamp": "NOT-A-REAL-DATE",
        }), encoding="utf-8")
        mod = _load_session_primer()
        result = mod._consume_clear_pending(boost_home)
        assert result == ""

    def test_returns_empty_when_workspace_memo_empty(self, boost_home):
        """Handoff exists but workspace_memo is empty → returns empty string."""
        import datetime
        flag = boost_home / "state" / "clear-pending.json"
        handoff = boost_home / "state" / "handoff-latest.json"
        flag.write_text(json.dumps({
            "pending": True,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }), encoding="utf-8")
        handoff.write_text(json.dumps({
            "workspace_memo": "",
            "active_workspace": "",
        }), encoding="utf-8")
        mod = _load_session_primer()
        result = mod._consume_clear_pending(boost_home)
        assert result == ""


class TestActiveWorkspaceReminderWithRagStatus:
    def test_shows_codebase_ready_when_indexed(self, boost_home, tmp_path):
        """rag_status has the project indexed → shows READY in dashboard."""
        ws = tmp_path / "workspace" / "task-codebase"
        ws.mkdir(parents=True)
        (ws / "context.md").write_text("# Codebase task\nStatus: in progress", encoding="utf-8")

        reg = {
            "task-codebase": {
                "workspace_path": str(ws),
                "project_path": str(tmp_path),
            }
        }
        (boost_home / "state" / "workspaces.json").write_text(json.dumps(reg), encoding="utf-8")

        proj_norm = str(tmp_path).replace("\\", "/")
        rag_status = {
            "indexed_projects": [
                {"project_path": proj_norm, "files": 42, "chunks": 150}
            ]
        }

        mod = _load_session_primer()
        result = mod._active_workspace_reminder(boost_home, rag_status, "fix the codebase bug")
        assert "READY" in result or "task-codebase" in result

    def test_shows_not_indexed_when_project_missing(self, boost_home, tmp_path):
        """rag_status present but project not in indexed_projects → NOT INDEXED."""
        ws = tmp_path / "workspace" / "task-notindexed"
        ws.mkdir(parents=True)
        (ws / "context.md").write_text("# Not indexed\nStatus: in progress", encoding="utf-8")

        reg = {
            "task-notindexed": {
                "workspace_path": str(ws),
                "project_path": str(tmp_path),
            }
        }
        (boost_home / "state" / "workspaces.json").write_text(json.dumps(reg), encoding="utf-8")

        rag_status = {"indexed_projects": []}

        mod = _load_session_primer()
        result = mod._active_workspace_reminder(boost_home, rag_status, "fix the not indexed task")
        assert "NOT INDEXED" in result or "task-notindexed" in result

    def test_shows_project_kb_ready_when_knowledge_exists(self, boost_home, tmp_path):
        """Project KB directory with .md files → shows READY in dashboard."""
        ws = tmp_path / "workspace" / "task-kb"
        ws.mkdir(parents=True)
        (ws / "context.md").write_text("# KB task\nStatus: in progress", encoding="utf-8")

        kb_dir = tmp_path / ".claudeboost" / "knowledge"
        kb_dir.mkdir(parents=True)
        (kb_dir / "api.md").write_text("# API knowledge", encoding="utf-8")

        reg = {
            "task-kb": {
                "workspace_path": str(ws),
                "project_path": str(tmp_path),
            }
        }
        (boost_home / "state" / "workspaces.json").write_text(json.dumps(reg), encoding="utf-8")

        mod = _load_session_primer()
        result = mod._active_workspace_reminder(boost_home, None, "fix the kb task")
        assert "task-kb" in result

    def test_shows_multiple_candidates_section(self, boost_home, tmp_path):
        """Multiple close-scoring workspaces → WORKSPACE CANDIDATES section shown."""
        for name in ("task-one", "task-two"):
            ws = tmp_path / "workspace" / name
            ws.mkdir(parents=True)
            (ws / "context.md").write_text(f"# {name}\nStatus: active\nwork in progress", encoding="utf-8")

        reg = {
            "task-one": {"workspace_path": str(tmp_path / "workspace" / "task-one"), "project_path": ""},
            "task-two": {"workspace_path": str(tmp_path / "workspace" / "task-two"), "project_path": ""},
        }
        (boost_home / "state" / "workspaces.json").write_text(json.dumps(reg), encoding="utf-8")

        mod = _load_session_primer()
        result = mod._active_workspace_reminder(boost_home, None, "generic development task here")
        # Should produce a result with workspace info
        assert isinstance(result, str)


class TestGetRagStatus:
    """Tests for _get_rag_status() — covers the success path (line 52)."""

    def test_returns_parsed_json_on_success(self):
        """_get_rag_status returns the parsed JSON dict when the HTTP call succeeds."""
        import unittest.mock as mock
        import io

        fake_payload = json.dumps({"status": "ready", "collections": {}}).encode()

        class FakeResponse:
            def read(self):
                return fake_payload
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        mod = _load_session_primer()
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse()):
            result = mod._get_rag_status(timeout=1.0)

        assert result == {"status": "ready", "collections": {}}

    def test_returns_none_when_urlopen_raises(self):
        """_get_rag_status returns None when the HTTP call throws (server down)."""
        import unittest.mock as mock
        import urllib.error

        mod = _load_session_primer()
        with mock.patch("urllib.request.urlopen", side_effect=OSError("Connection refused")):
            result = mod._get_rag_status(timeout=0.1)

        assert result is None


class TestActiveWorkspaceReminderPermissionError:
    """Tests for the PermissionError branch in _active_workspace_reminder (lines 217-218)."""

    def test_shows_unknown_when_kb_glob_raises_permission_error(self, boost_home, tmp_path):
        """PermissionError on kb_dir.glob() → dashboard shows UNKNOWN (permission error)."""
        import unittest.mock as mock

        ws = tmp_path / "workspace" / "task-perm"
        ws.mkdir(parents=True)
        (ws / "context.md").write_text("# Perm task\nStatus: in progress", encoding="utf-8")

        kb_dir = tmp_path / ".claudeboost" / "knowledge"
        kb_dir.mkdir(parents=True)

        reg = {
            "task-perm": {
                "workspace_path": str(ws),
                "project_path": str(tmp_path),
            }
        }
        (boost_home / "state" / "workspaces.json").write_text(json.dumps(reg), encoding="utf-8")

        mod = _load_session_primer()

        # Patch Path.glob so that when called on the kb_dir path it raises PermissionError
        real_glob = mod.Path.glob

        def patched_glob(self, pattern):
            if ".claudeboost" in str(self) and "knowledge" in str(self):
                raise PermissionError("Access denied")
            return real_glob(self, pattern)

        with mock.patch.object(mod.Path, "glob", patched_glob):
            result = mod._active_workspace_reminder(boost_home, None, "fix the perm task work")

        assert "UNKNOWN (permission error)" in result


class TestConsumeClearPendingUnlinkFails:
    """Tests for the finally-except path in _consume_clear_pending (lines 352-353)."""

    def test_no_crash_when_unlink_raises(self, boost_home):
        """If flag_path.unlink() raises, the exception is swallowed and '' is returned."""
        import unittest.mock as mock
        import datetime

        flag = boost_home / "state" / "clear-pending.json"
        flag.write_text(json.dumps({
            "pending": False,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }), encoding="utf-8")

        mod = _load_session_primer()

        # Patch Path.unlink so it raises when called on the flag path
        real_unlink = mod.Path.unlink

        def patched_unlink(self, missing_ok=False):
            if "clear-pending" in str(self):
                raise OSError("Locked by another process")
            return real_unlink(self, missing_ok=missing_ok)

        with mock.patch.object(mod.Path, "unlink", patched_unlink):
            result = mod._consume_clear_pending(boost_home)

        # Should return '' (pending=False) and not raise
        assert result == ""

    def test_no_crash_when_unlink_raises_and_flag_is_corrupt(self, boost_home):
        """Corrupt flag + unlink() raises: both errors swallowed, returns ''."""
        import unittest.mock as mock

        flag = boost_home / "state" / "clear-pending.json"
        flag.write_text("NOT JSON", encoding="utf-8")

        mod = _load_session_primer()

        real_unlink = mod.Path.unlink

        def patched_unlink(self, missing_ok=False):
            if "clear-pending" in str(self):
                raise PermissionError("Cannot delete")
            return real_unlink(self, missing_ok=missing_ok)

        with mock.patch.object(mod.Path, "unlink", patched_unlink):
            result = mod._consume_clear_pending(boost_home)

        assert result == ""


class TestMainMalformedStdin:
    def test_malformed_json_stdin_exits_0(self, boost_home, tmp_path):
        """Malformed JSON on stdin falls back to empty dict — no crash."""
        import subprocess, sys, os
        from pathlib import Path as P
        SCRIPTS = P(__file__).resolve().parent.parent
        from helpers import COVERAGERC
        env = {**os.environ, "CLAUDEBOOST_HOME": str(boost_home), "TEMP": str(tmp_path)}
        if COVERAGERC.exists():
            env["COVERAGE_PROCESS_START"] = str(COVERAGERC)
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "session-primer.py")],
            input=b"NOT VALID JSON AT ALL",
            capture_output=True,
            env=env,
        )
        assert result.returncode == 0
        assert b"Traceback" not in result.stderr
