"""Tests for setup.py's opt-in install_jev_router step."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SETUP = Path(__file__).resolve().parent.parent / "setup.py"
_spec = importlib.util.spec_from_file_location("cb_setup", _SETUP)
setup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(setup)


@pytest.fixture
def env(monkeypatch):
    """Fake which/run_cmd; record every call and warning."""
    state = {"which": {}, "rc": 0, "cmds": [], "warns": [], "oks": [],
             "installed_after": True}

    def which(name):
        if name == "jev-claude" and state["cmds"] and state["installed_after"]:
            return "/bin/jev-claude"
        return state["which"].get(name)

    def run_cmd(args):
        state["cmds"].append(args)
        return state["rc"], "npm output"

    monkeypatch.setattr(setup.shutil, "which", which)
    monkeypatch.setattr(setup, "run_cmd", run_cmd)
    monkeypatch.setattr(setup, "_warn", state["warns"].append)
    monkeypatch.setattr(setup, "_ok", state["oks"].append)
    monkeypatch.delenv("CLAUDEBOOST_WITH_JEV_ROUTER", raising=False)
    return state


def test_off_by_default(env):
    setup.install_jev_router()
    assert env["cmds"] == [] and env["oks"] == [] and env["warns"] == []


@pytest.mark.parametrize("value", ["0", "false", "OFF", " no "])
def test_falsy_values_stay_off(env, monkeypatch, value):
    monkeypatch.setenv("CLAUDEBOOST_WITH_JEV_ROUTER", value)
    env["which"] = {"npm": "/bin/npm"}
    setup.install_jev_router()
    assert env["cmds"] == [] and env["oks"] == []


def test_already_installed_never_runs_binary(env, monkeypatch):
    monkeypatch.setenv("CLAUDEBOOST_WITH_JEV_ROUTER", "1")
    env["which"] = {"jev-claude": "/bin/jev-claude", "npm": "/bin/npm"}
    setup.install_jev_router()
    assert env["cmds"] == []
    assert env["oks"] == ["jev-router already installed"]
    assert any("TypeSafe" in w for w in env["warns"])


def test_no_npm(env, monkeypatch):
    monkeypatch.setenv("CLAUDEBOOST_WITH_JEV_ROUTER", "1")
    setup.install_jev_router()
    assert env["cmds"] == [] and env["oks"] == []
    assert "npm not found" in env["warns"][0]


def test_installs(env, monkeypatch):
    monkeypatch.setenv("CLAUDEBOOST_WITH_JEV_ROUTER", "1")
    env["which"] = {"npm": "/bin/npm"}
    setup.install_jev_router()
    assert env["cmds"] == [["/bin/npm", "install", "-g", "jev-router"]]
    assert env["oks"] == ["jev-router installed"]
    assert any("JEV_API_KEY" in w for w in env["warns"])


def test_install_failure(env, monkeypatch):
    monkeypatch.setenv("CLAUDEBOOST_WITH_JEV_ROUTER", "1")
    env["which"] = {"npm": "/bin/npm"}
    env["rc"] = 1
    setup.install_jev_router()
    assert env["oks"] == []
    assert "install failed" in env["warns"][0]


def test_installed_but_not_on_path(env, monkeypatch):
    monkeypatch.setenv("CLAUDEBOOST_WITH_JEV_ROUTER", "1")
    env["which"] = {"npm": "/bin/npm"}
    env["installed_after"] = False
    setup.install_jev_router()
    assert env["oks"] == []
    assert "not on PATH" in env["warns"][0]
