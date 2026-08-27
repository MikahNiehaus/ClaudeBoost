"""The hook audit must find real faults and must not invent fake ones.

Both halves matter equally. The first version of this tool reported 20 problems
against a healthy config: eleven routes that were not routes (/127 lifted out of
127.0.0.1, plus /state and /logging lifted out of file paths and prose) and six
scripts that existed but whose $CLAUDEBOOST_HOME was never expanded, because the
project settings file has no env block of its own and expansion was being done
per file instead of merged.

An audit that cries wolf gets switched off, so the false positive cases below
are regression tests with the same standing as the true positive ones.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]


def _load():
    path = SCRIPTS_DIR / "audit-hooks.py"
    spec = importlib.util.spec_from_file_location("audit_hooks", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mod():
    return _load()


def _settings(tmp_path: Path, hooks: dict, env: dict | None = None) -> Path:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"env": env or {}, "hooks": hooks}, indent=2), encoding="utf-8"
    )
    return path


def _command_hook(event: str, command: str) -> dict:
    return {event: [{"matcher": "", "hooks": [{"type": "command", "command": command}]}]}


def _prompt_hook(event: str, prompt: str) -> dict:
    return {event: [{"matcher": "Always", "hooks": [{"type": "prompt", "prompt": prompt}]}]}


def _run(mod, monkeypatch, settings_path, agents=()):
    monkeypatch.setattr(mod, "SETTINGS_FILES", [settings_path])
    monkeypatch.setattr(mod, "_installed_agents", lambda: set(agents))
    return mod.audit()


def _kinds(problems):
    return {p["kind"] for p in problems}


# --- real faults it must catch -------------------------------------------

def test_missing_script_is_reported(mod, monkeypatch, tmp_path):
    s = _settings(tmp_path, _command_hook("Stop", f'python "{tmp_path / "nope.py"}"'))
    problems, _ = _run(mod, monkeypatch, s)
    assert "MISSING SCRIPT" in _kinds(problems)


def test_syntax_error_is_reported(mod, monkeypatch, tmp_path):
    broken = tmp_path / "broken.py"
    broken.write_text("def oops(:\n    pass\n", encoding="utf-8")
    s = _settings(tmp_path, _command_hook("Stop", f'python "{broken}"'))
    problems, _ = _run(mod, monkeypatch, s)
    assert "SYNTAX ERROR" in _kinds(problems)


def test_a_healthy_script_is_not_reported(mod, monkeypatch, tmp_path):
    ok = tmp_path / "fine.py"
    ok.write_text("print('hello')\n", encoding="utf-8")
    s = _settings(tmp_path, _command_hook("Stop", f'python "{ok}"'))
    problems, stats = _run(mod, monkeypatch, s)
    assert problems == []
    assert stats["scripts"] == 1


def test_mojibake_is_reported(mod, monkeypatch, tmp_path):
    s = _settings(tmp_path, _prompt_hook("SessionStart", "QUALITY â€” check this"))
    problems, _ = _run(mod, monkeypatch, s)
    assert "MOJIBAKE" in _kinds(problems)


def test_unknown_agent_is_reported(mod, monkeypatch, tmp_path):
    s = _settings(tmp_path, _prompt_hook("SessionStart", "Always use evaluator-agent."))
    problems, _ = _run(mod, monkeypatch, s, agents=("researcher", "swiper"))
    assert "UNKNOWN AGENT" in _kinds(problems)
    assert any("evaluator-agent" in p["detail"] for p in problems)


def test_an_installed_agent_is_not_reported(mod, monkeypatch, tmp_path):
    s = _settings(tmp_path, _prompt_hook("SessionStart", "Spawn research-agent first."))
    problems, _ = _run(mod, monkeypatch, s, agents=("research-agent",))
    assert "UNKNOWN AGENT" not in _kinds(problems)


def test_empty_hook_is_reported(mod, monkeypatch, tmp_path):
    hooks = {"Stop": [{"matcher": "", "hooks": [{"type": "command"}]}]}
    s = _settings(tmp_path, hooks)
    problems, _ = _run(mod, monkeypatch, s)
    assert "EMPTY HOOK" in _kinds(problems)


def test_unparseable_settings_is_reported(mod, monkeypatch, tmp_path):
    bad = tmp_path / "settings.json"
    bad.write_text("{ not json", encoding="utf-8")
    problems, _ = _run(mod, monkeypatch, bad)
    assert "UNPARSEABLE SETTINGS" in _kinds(problems)


# --- false positives it must NOT produce ---------------------------------

def test_the_server_ip_is_not_mistaken_for_a_route(mod, monkeypatch, tmp_path):
    """/127 out of 127.0.0.1 was eleven of the twenty original false findings."""
    prompt = 'Search: POST http://127.0.0.1:8613/search with {"query":"..."}'
    s = _settings(tmp_path, _prompt_hook("SessionStart", prompt))
    problems, _ = _run(mod, monkeypatch, s)
    assert not any("/127" in p["detail"] for p in problems), problems


def test_file_paths_are_not_mistaken_for_routes(mod, monkeypatch, tmp_path):
    """state/claudeboost-mode.json is a file, not /state and /claudeboost-mode."""
    prompt = (
        "Read $CLAUDEBOOST_HOME/state/claudeboost-mode.json at the start.\n"
        "Log approval to $CLAUDEBOOST_HOME/state/session-approvals.json.\n"
        "Server: http://127.0.0.1:8613\n"
        "Architectural = new endpoint, auth/validation/error/logging strategy."
    )
    s = _settings(tmp_path, _prompt_hook("SessionStart", prompt))
    problems, _ = _run(mod, monkeypatch, s)
    assert "DEAD ROUTE" not in _kinds(problems), problems


def test_env_from_another_settings_file_still_expands(mod, monkeypatch, tmp_path):
    """A project settings file has no env block but still uses $CLAUDEBOOST_HOME.

    Expanding per file left those literal and reported six existing scripts as
    missing.
    """
    script = tmp_path / "scripts" / "real.py"
    script.parent.mkdir(parents=True)
    script.write_text("print('ok')\n", encoding="utf-8")

    global_settings = tmp_path / "global.json"
    global_settings.write_text(
        json.dumps({"env": {"CLAUDEBOOST_HOME": str(tmp_path)}, "hooks": {}}),
        encoding="utf-8",
    )
    project_settings = tmp_path / "project.json"
    project_settings.write_text(
        json.dumps({"hooks": _command_hook("Stop", 'python "$CLAUDEBOOST_HOME/scripts/real.py"')}),
        encoding="utf-8",
    )

    monkeypatch.setattr(mod, "SETTINGS_FILES", [global_settings, project_settings])
    monkeypatch.setattr(mod, "_installed_agents", lambda: set())
    problems, _ = mod.audit()
    assert "MISSING SCRIPT" not in _kinds(problems), problems


def test_a_route_named_only_to_say_it_is_gone_is_not_a_fault(mod, monkeypatch, tmp_path):
    """Documenting a removed route is correct, not a fault to flag."""
    prompt = (
        "Server http://127.0.0.1:8613\n"
        "There is no /context route and no /index route; both were removed and "
        "now return 404."
    )
    s = _settings(tmp_path, _prompt_hook("SessionStart", prompt))
    problems, _ = _run(mod, monkeypatch, s)
    assert "DEAD ROUTE" not in _kinds(problems), problems


def test_a_server_that_is_down_yields_no_route_verdict(mod, monkeypatch, tmp_path):
    """No answer must mean no verdict, not "every route is dead"."""
    prompt = "Use POST http://127.0.0.1:59999/definitely-not-a-real-route please."
    s = _settings(tmp_path, _prompt_hook("SessionStart", prompt))
    problems, _ = _run(mod, monkeypatch, s)
    assert "DEAD ROUTE" not in _kinds(problems), problems


# --- the audit must be honest about its own scope ------------------------

def test_no_machine_specific_paths_in_the_tool(mod):
    """The tool ships to other machines, so it must not name this one."""
    source = (SCRIPTS_DIR / "audit-hooks.py").read_text(encoding="utf-8")
    lowered = source.lower()
    assert "users\\mniehaus" not in lowered and "users/mniehaus" not in lowered
    assert "onedrive" not in lowered
