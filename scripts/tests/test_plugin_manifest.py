"""The plugin manifests point only at files inside the repo that exist."""

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PLUGIN_DIR = REPO / ".claude-plugin"


def _load(name: str) -> dict:
    return json.loads((PLUGIN_DIR / name).read_text(encoding="utf-8"))


def _paths(manifest: dict) -> list[str]:
    paths = list(manifest["agents"])
    for key in ("skills", "commands"):
        value = manifest[key]
        paths.extend(value if isinstance(value, list) else [value])
    return paths


def test_plugin_name():
    assert _load("plugin.json")["name"] == "claudeboost"


def test_every_listed_path_exists_inside_the_repo():
    for rel in _paths(_load("plugin.json")):
        assert rel.startswith("./"), rel
        assert ".." not in Path(rel).parts, rel
        target = (REPO / rel).resolve()
        assert target.is_relative_to(REPO), rel
        assert target.exists(), rel


def test_every_portable_agent_is_listed():
    listed = {Path(p).name for p in _load("plugin.json")["agents"]}
    on_disk = {p.name for p in (REPO / "clean-rag" / "portable" / "agents").glob("*.md")}
    assert listed == on_disk


def test_marketplace_serves_the_repo_root_as_the_plugin():
    entries = _load("marketplace.json")["plugins"]
    assert [(e["name"], e["source"]) for e in entries] == [("claudeboost", "./")]
