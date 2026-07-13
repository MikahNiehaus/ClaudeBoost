#!/usr/bin/env python3
"""Install clean-rag's OpenCode integration.

Registers three things into OpenCode's global config at ~/.config/opencode:

  1. The clean-rag MCP server (type local) so OpenCode gets rag_search, code
     metrics, web search, and full context injection as tools.
  2. The research gate plugin, which blocks code edits until rag_search has run.
  3. The research and triage subagents, ported to OpenCode's agent format.

Idempotent: safe to run repeatedly. It merges the MCP entry into whatever config
already exists rather than overwriting, and it will not clobber a plugin or agent
file that the user has edited more recently than the copy shipped here.

All paths are derived, none hardcoded. clean-rag home comes from CLEAN_RAG_HOME or
the location of this file; the OpenCode config dir comes from the user's home.
"""

import json
import os
import shutil
import sys
from pathlib import Path


def clean_rag_home() -> Path:
    env = os.environ.get("CLEAN_RAG_HOME")
    if env:
        return Path(env)
    # This file lives at clean-rag/opencode/install.py, so clean-rag is two up.
    return Path(__file__).resolve().parent.parent


def opencode_config_dir() -> Path:
    return Path.home() / ".config" / "opencode"


def config_file(cfg_dir: Path) -> Path:
    """Pick the config file to edit.

    OpenCode reads opencode.json or opencode.jsonc. Edit whichever already exists
    so we don't create a second competing file; default to opencode.json when
    neither is there.
    """
    json_path = cfg_dir / "opencode.json"
    jsonc_path = cfg_dir / "opencode.jsonc"
    if json_path.exists():
        return json_path
    if jsonc_path.exists():
        return jsonc_path
    return json_path


def load_config(path: Path) -> dict:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        # Refuse to guess. Overwriting a config we can't parse would lose the
        # user's settings, and a .jsonc with real comments lands here. Tell them.
        print(f"ERROR: {path} is not valid JSON ({e}).")
        print("Fix or remove it, then run install again. Nothing was changed.")
        sys.exit(1)


def _copy_if_newer(src: Path, dst: Path) -> str:
    """Copy src to dst unless dst is a newer user edit. Returns what happened."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        if dst.stat().st_mtime > src.stat().st_mtime:
            return f"kept (yours is newer): {dst}"
        if src.read_bytes() == dst.read_bytes():
            return f"unchanged: {dst}"
    shutil.copy2(src, dst)
    return f"installed: {dst}"


def main() -> int:
    home = clean_rag_home()
    mcp_server = home / "mcp" / "opencode_mcp_server.py"
    plugin_src = home / "opencode" / "plugin" / "research-gate.js"
    agents_src = home / "opencode" / "agents"

    if not mcp_server.exists():
        print(f"ERROR: MCP server not found at {mcp_server}. Is CLEAN_RAG_HOME right?")
        return 1

    cfg_dir = opencode_config_dir()
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = config_file(cfg_dir)
    config = load_config(cfg_path)

    # Merge the MCP entry. Preserve every other server and key already present.
    python_exe = sys.executable or "python"
    config.setdefault("mcp", {})
    config["mcp"]["clean-rag"] = {
        "type": "local",
        "command": [python_exe, str(mcp_server)],
        "enabled": True,
        "environment": {"CLEAN_RAG_HOME": str(home)},
    }
    cfg_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(f"registered MCP server 'clean-rag' in {cfg_path}")
    print(f"  command: {python_exe} {mcp_server}")

    # Plugin.
    print(_copy_if_newer(plugin_src, cfg_dir / "plugin" / "research-gate.js"))

    # Agents.
    for md in sorted(agents_src.glob("*.md")):
        print(_copy_if_newer(md, cfg_dir / "agents" / md.name))

    print("\nDone. Restart OpenCode (or start a new session) to pick up the changes.")
    print("The clean-rag server must be running on port 8613 for search to work.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
