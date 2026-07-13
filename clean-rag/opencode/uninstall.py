#!/usr/bin/env python3
"""Uninstall clean-rag's OpenCode integration.

Reverses install.py: drops the clean-rag MCP entry from OpenCode's config, and
removes the plugin and the two agent files it copied in. Leaves the rest of the
config untouched, and does not touch OpenCode itself or any dependency.

All paths derived, none hardcoded.
"""

import json
import os
import sys
from pathlib import Path


def clean_rag_home() -> Path:
    env = os.environ.get("CLEAN_RAG_HOME")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent


def opencode_config_dir() -> Path:
    return Path.home() / ".config" / "opencode"


def config_file(cfg_dir: Path) -> Path:
    json_path = cfg_dir / "opencode.json"
    jsonc_path = cfg_dir / "opencode.jsonc"
    if json_path.exists():
        return json_path
    if jsonc_path.exists():
        return jsonc_path
    return json_path


def main() -> int:
    home = clean_rag_home()
    cfg_dir = opencode_config_dir()
    cfg_path = config_file(cfg_dir)

    # Remove the MCP entry, if the config is there and parseable.
    if cfg_path.exists():
        text = cfg_path.read_text(encoding="utf-8").strip()
        try:
            config = json.loads(text) if text else {}
        except json.JSONDecodeError as e:
            print(f"WARNING: {cfg_path} is not valid JSON ({e}); left it alone.")
            config = None

        if config is not None:
            mcp = config.get("mcp", {})
            if "clean-rag" in mcp:
                del mcp["clean-rag"]
                if not mcp:
                    config.pop("mcp", None)
                cfg_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
                print(f"removed MCP server 'clean-rag' from {cfg_path}")
            else:
                print(f"no clean-rag MCP entry in {cfg_path}")
    else:
        print(f"no OpenCode config at {cfg_path}")

    # Remove the plugin and agent files we shipped.
    targets = [cfg_dir / "plugin" / "research-gate.js"]
    agents_src = home / "opencode" / "agents"
    if agents_src.exists():
        for md in agents_src.glob("*.md"):
            targets.append(cfg_dir / "agents" / md.name)

    for path in targets:
        if path.exists():
            path.unlink()
            print(f"removed: {path}")
        else:
            print(f"already gone: {path}")

    print("\nDone. The clean-rag OpenCode integration is uninstalled.")
    print("OpenCode itself and its dependencies were left untouched.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
