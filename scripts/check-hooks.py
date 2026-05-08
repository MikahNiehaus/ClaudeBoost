"""Check if a hook exists in Claude settings."""
import json, sys, os
hook_name = sys.argv[1] if len(sys.argv) > 1 else "PreToolUse"
settings_path = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
with open(settings_path, encoding="utf-8") as f:
    s = json.load(f)
assert hook_name in s.get("hooks", {}), f"{hook_name} not found"
print(f"{hook_name} hooks: OK")
