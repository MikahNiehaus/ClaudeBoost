#!/usr/bin/env python3
"""One-shot script to update settings.json statusLine to use rag-statusline.py."""
import json
import sys
from pathlib import Path

settings_path = Path.home() / ".claude" / "settings.json"
with open(settings_path, encoding="utf-8") as f:
    settings = json.load(f)

interp = Path(sys.executable).as_posix()
new_cmd = f'"{interp}" "$CLAUDEBOOST_HOME/scripts/rag-statusline.py"'
settings["statusLine"] = {"type": "command", "command": new_cmd}

with open(settings_path, "w", encoding="utf-8") as f:
    json.dump(settings, f, indent=2)

print(f"statusLine updated to: {new_cmd}")
