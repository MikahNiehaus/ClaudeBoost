"""The two PLUGINS tables must stay in step.

clean-rag installs standalone, so it carries its own copy of the table the way
it carries its own copy of MCP_SERVERS. Two copies drift, and a plugin's hooks
run as the user on every prompt, so a row present in one installer and absent
from the other means two machines enforce different rules while both report a
clean install. test_mcp_server_registration.py already notices this for MCP
servers; nothing noticed it for plugins until a second row existed.

A row needs both `marketplace` and `name`. Adding the marketplace alone
registers nothing, which fails silently rather than loudly.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# `why` is prose for a human reading setup.py and changes no behaviour, so the
# two tables are allowed to disagree on it.
FUNCTIONAL_KEYS = ("name", "marketplace", "needs_node")


def _load(rel):
    path = ROOT / rel
    spec = importlib.util.spec_from_file_location(rel.replace("/", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def setup_mod():
    return _load("scripts/setup.py")


@pytest.fixture(scope="module")
def cleanrag_mod():
    return _load("clean-rag/install.py")


def _functional(plugin: dict) -> dict:
    return {k: plugin[k] for k in FUNCTIONAL_KEYS if k in plugin}


def test_installer_tables_agree(setup_mod, cleanrag_mod):
    boost = {p["name"]: _functional(p) for p in setup_mod.PLUGINS}
    portable = {p["name"]: _functional(p) for p in cleanrag_mod.PLUGINS}
    assert boost == portable, (
        "scripts/setup.py and clean-rag/install.py disagree on the plugin "
        f"table.\n  setup.py: {boost}\n  clean-rag: {portable}"
    )


@pytest.mark.parametrize("rel", ["scripts/setup.py", "clean-rag/install.py"])
def test_every_row_carries_both_halves(rel):
    for plugin in _load(rel).PLUGINS:
        assert plugin.get("marketplace"), f"{rel}: {plugin} has no marketplace"
        assert plugin.get("name"), f"{rel}: {plugin} has no name"
        marketplace_id = plugin["name"].split("@")[-1]
        repo_tail = plugin["marketplace"].split("/")[-1]
        assert marketplace_id == repo_tail, (
            f"{rel}: {plugin['name']} names marketplace {marketplace_id!r} but "
            f"the row installs {plugin['marketplace']!r}"
        )


def test_no_duplicate_rows(setup_mod, cleanrag_mod):
    for label, table in (("setup.py", setup_mod.PLUGINS),
                         ("clean-rag", cleanrag_mod.PLUGINS)):
        names = [p["name"] for p in table]
        assert len(names) == len(set(names)), f"{label} lists a plugin twice: {names}"
