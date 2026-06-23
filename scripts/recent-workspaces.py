"""
List the 5 most recently active workspaces (by context.md mtime).
Output format: wid|workspace_path|project_path (one per line).
Used by /workspace Phase 0.75 to offer piggyback on an existing workspace.
"""
import json, os, pathlib, sys

home = pathlib.Path(os.environ.get('CLAUDEBOOST_HOME', ''))
if not home or not home.exists():
    sys.exit(0)
reg_path = home / 'state' / 'workspaces.json'
if not reg_path.exists():
    sys.exit(0)
reg = json.loads(reg_path.read_text(encoding='utf-8'))
recent = []
for wid, entry in reg.items():
    ctx = pathlib.Path(entry.get('workspace_path', '')) / 'context.md'
    if ctx.exists():
        recent.append((ctx.stat().st_mtime, wid, entry.get('workspace_path', ''), entry.get('project_path', '')))
recent.sort(reverse=True)
for _, wid, wpath, ppath in recent[:5]:
    print(f"{wid}|{wpath}|{ppath}")
