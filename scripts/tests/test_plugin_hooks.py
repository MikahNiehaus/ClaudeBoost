"""The hook table in plugin_hooks.py is the one source for hooks.json and for setup."""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import plugin_hooks  # noqa: E402
import setup  # noqa: E402

REPO = SCRIPTS_DIR.parent


@pytest.fixture(autouse=True)
def _tmp_claude_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, "CLAUDE_DIR", tmp_path)
    monkeypatch.setattr(setup, "SETTINGS_PATH", tmp_path / "settings.json")


def _handlers(settings: dict) -> list[dict]:
    return [h for groups in settings.get("hooks", {}).values() for g in groups for h in g["hooks"]]


def test_hooks_json_matches_the_table():
    assert plugin_hooks.HOOKS_JSON.read_text(encoding="utf-8") == plugin_hooks.render()


def test_table_scripts_match_what_the_installers_register():
    table = {row["script"] for row in plugin_hooks.HOOKS if "script" in row}
    setup_rows = {row["script"] for row in setup.SETUP_HOOKS if "script" in row}
    install_src = (REPO / "clean-rag" / "install.py").read_text(encoding="utf-8")
    clean_rag = set(re.findall(r'\$CLEAN_RAG_HOME/(?:hooks|scripts)/([\w-]+\.py)', install_src))
    assert table == setup_rows | clean_rag


# On tool events the matcher is a regex on the tool name, so a command filter there never fires.
TOOL_EVENTS = ("PreToolUse", "PostToolUse", "PostToolUseFailure", "PermissionRequest")


@pytest.mark.parametrize("mode", ["keep", "replace"])
def test_no_tool_matcher_is_a_command_filter(mode):
    settings: dict = {}
    setup._install_all_hooks(settings, mode)
    groups = []
    for hooks in (settings["hooks"], plugin_hooks.build()["hooks"]):
        groups += [g for event in TOOL_EVENTS for g in hooks.get(event, [])]
    assert groups or mode == "replace"
    for g in groups:
        matcher = (g.get("matcher") or "").replace(".*", "")
        assert "(" not in matcher and "*" not in matcher, matcher


def test_keep_twice_is_identical():
    settings: dict = {}
    setup._install_all_hooks(settings, "keep")
    first = json.dumps(settings, sort_keys=True)
    setup._install_all_hooks(settings, "keep")
    assert json.dumps(settings, sort_keys=True) == first


def test_replace_leaves_only_the_bootstrap_and_is_stable():
    settings: dict = {}
    setup._install_all_hooks(settings, "keep")
    setup._install_all_hooks(settings, "replace")
    first = json.dumps(settings, sort_keys=True)
    setup._install_all_hooks(settings, "replace")
    assert json.dumps(settings, sort_keys=True) == first
    assert [h["command"] for h in _handlers(settings) if "ensure-setup.py" not in h["command"]] == []


def test_replace_keeps_hooks_that_are_not_claudeboost():
    other = {"type": "command", "command": "echo mine"}
    settings = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [other]}]}}
    setup._install_all_hooks(settings, "replace")
    assert other in _handlers(settings)


def test_keep_disables_a_plugin_left_enabled_by_replace():
    settings = {"enabledPlugins": {setup.PLUGIN_ID: True}}
    setup._install_all_hooks(settings, "keep")
    assert settings["enabledPlugins"][setup.PLUGIN_ID] is False
    assert any("bash-guard.py" in h.get("command", "") for h in _handlers(settings))


def test_keep_registers_the_background_reviewer_stamp():
    settings: dict = {}
    setup._install_all_hooks(settings, "keep")
    stop = [h["command"] for g in settings["hooks"].get("SubagentStop", []) for h in g["hooks"]]
    assert len(stop) == 1 and "verifier-record.py" in stop[0]


def test_replace_keeps_a_user_prompt_that_quotes_a_sentinel():
    mine = {"type": "prompt", "prompt": "Team rule: PROCESS KILL SAFETY is handled by our wrapper."}
    settings = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [mine]}]}}
    setup._install_all_hooks(settings, "replace")
    assert mine in _handlers(settings)


def test_rerun_refreshes_the_bootstrap_timeout():
    old = {"type": "command", "command": 'python "$HOME/.claude/ensure-setup.py"', "timeout": 10000}
    settings = {"hooks": {"UserPromptSubmit": [{"hooks": [old]}]}}
    setup._install_all_hooks(settings, "keep")
    assert [h["timeout"] for h in _handlers(settings) if "ensure-setup.py" in h.get("command", "")] == [10]


@pytest.mark.parametrize("enabled, expected", [(False, "keep"), (True, "replace")])
def test_eof_at_the_prompt_keeps_the_current_mode(monkeypatch, enabled, expected):
    setup.SETTINGS_PATH.write_text(json.dumps({"enabledPlugins": {setup.PLUGIN_ID: enabled}}))
    monkeypatch.setattr(setup, "_stdin_is_console", lambda: True)

    def eof(_prompt):
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)
    assert setup._choose_hooks_mode(None) == expected


def test_null_stdin_never_prompts_and_keeps_keep(tmp_path):
    # ensure-setup.py spawns setup with stdin=DEVNULL, and Windows isatty() is True for NUL.
    code = (
        "import sys, pathlib; sys.path.insert(0, sys.argv[1]); import setup\n"
        "p = pathlib.Path(sys.argv[2]); setup.CLAUDE_DIR = p; setup.SETTINGS_PATH = p / 'settings.json'\n"
        "print('MODE', setup._choose_hooks_mode(None))\n"
    )
    env = {k: os.environ[k] for k in ("SYSTEMROOT", "PATH") if k in os.environ}
    env.update(HOME=str(tmp_path), USERPROFILE=str(tmp_path))
    proc = subprocess.run([sys.executable, "-c", code, str(SCRIPTS_DIR), str(tmp_path)],
                          stdin=subprocess.DEVNULL, capture_output=True, text=True, env=env, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert "Replace or Keep" not in proc.stdout
    assert proc.stdout.strip().endswith("MODE keep")


def test_clean_rag_wipe_keeps_a_user_handler_in_the_same_group(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("clean_rag_install", REPO / "clean-rag" / "install.py")
    install = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(install)
    path = tmp_path / "settings.json"
    monkeypatch.setattr(install, "SETTINGS_PATH", path)
    mine = {"type": "command", "command": "echo mine"}
    ours = {"type": "command", "command": 'python "$CLEAN_RAG_HOME/hooks/research-gate.py"'}
    path.write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [mine, ours]}]}}))
    install.wipe_clean_rag_hooks()
    assert _handlers(json.loads(path.read_text())) == [mine]
