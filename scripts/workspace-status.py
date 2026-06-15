"""
workspace-status.py  —  Show or switch active workspace for the current project.

Usage:
  python workspace-status.py              # print table of workspaces
  python workspace-status.py <ws-id>      # switch active workspace
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Reconfigure stdout to UTF-8 so box-drawing chars work on Windows terminals.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _home() -> Path:
    return Path(os.environ.get("CLAUDEBOOST_HOME") or Path(__file__).parent.parent)


def _relative_time(ts: float) -> str:
    diff = time.time() - ts
    if diff < 60:
        return "just now"
    if diff < 3600:
        return f"{int(diff // 60)}m ago"
    if diff < 86400:
        return f"{int(diff // 3600)}h ago"
    return f"{int(diff // 86400)}d ago"


def _trunc(s: str, n: int) -> str:
    if len(s) <= n:
        return s
    return s[: n - 3] + "..."


def _workspace_last_edit(ws_path: Path) -> float:
    """Max mtime of any file directly inside the workspace directory."""
    if not ws_path.is_dir():
        return 0.0
    try:
        return max(
            (e.stat().st_mtime for e in os.scandir(ws_path) if e.is_file()),
            default=0.0,
        )
    except OSError:
        return 0.0


def _parse_context(context_path: Path) -> tuple[str, str, float]:
    """Return (status, description, mtime). Description from ## Goal, falls back to ## Next Step."""
    if not context_path.exists():
        return "UNKNOWN", "—", 0.0

    mtime = os.path.getmtime(context_path)
    status = "UNKNOWN"
    description = "—"

    try:
        text = context_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return status, description, mtime

    lines = text.splitlines()
    in_goal = False
    in_next_step = False

    for i, line in enumerate(lines):
        stripped_line = line.strip()

        if stripped_line.startswith("## Status"):
            in_goal = False
            in_next_step = False
            rest = stripped_line[len("## Status"):].strip().lstrip("—").strip()
            if rest:
                status = rest.split()[0]
            else:
                for j in range(i + 1, min(i + 5, len(lines))):
                    nxt = lines[j].strip()
                    if nxt and not nxt.startswith("#"):
                        status = nxt.split()[0].rstrip("—,;:")
                        break
            continue

        if stripped_line == "## Goal":
            in_goal = True
            in_next_step = False
            continue

        if stripped_line == "## Next Step" and description == "—":
            in_next_step = True
            in_goal = False
            continue

        if stripped_line.startswith("##"):
            in_goal = False
            in_next_step = False
            continue

        if in_goal or in_next_step:
            val = stripped_line.lstrip("0123456789.*- ").strip()
            if val:
                description = val
                in_goal = False
                in_next_step = False

    return status, description, mtime


def _normalize_path(p: str) -> str:
    """Normalize a path for comparison: lower-case, forward slashes, no trailing slash."""
    return p.replace("\\", "/").rstrip("/").lower()


def show_table() -> None:
    home = _home()
    reg_path = home / "state" / "workspaces.json"

    if not reg_path.exists():
        print("No workspaces.json found — no workspaces registered yet.")
        return

    try:
        registry: dict = json.loads(reg_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Error reading workspaces.json: {exc}", file=sys.stderr)
        sys.exit(1)

    cwd = _normalize_path(os.getcwd())
    cb_home = _normalize_path(str(home))

    def _matches(entry: dict) -> bool:
        pp = _normalize_path(entry.get("project_path", ""))
        return not pp or pp in (cwd, cb_home)

    filtered = {k: v for k, v in registry.items() if _matches(v)}
    if not filtered:
        filtered = registry

    rows = []
    for ws_id, entry in filtered.items():
        ws_path = Path(entry.get("workspace_path", ""))
        context_path = ws_path / "context.md"
        _, description, _ = _parse_context(context_path)
        last_edit = _workspace_last_edit(ws_path)
        rows.append({
            "id": ws_id,
            "description": description,
            "last_edit": last_edit,
        })

    rows.sort(key=lambda r: r["last_edit"] if r["last_edit"] > 0 else float("-inf"), reverse=True)

    last_edited_id = rows[0]["id"] if rows and rows[0]["last_edit"] > 0 else ""

    W_WS = 42
    W_NX = 62
    W_UP = 10

    header = (
        f"{'':1}  "
        f"{'WORKSPACE':<{W_WS}}  "
        f"{'DESCRIPTION':<{W_NX}}  "
        f"{'EDITED':<{W_UP}}"
    )
    divider = "─" * len(header)

    print()
    print(header)
    print(divider)

    for r in rows:
        marker = "✎" if r["id"] == last_edited_id else " "
        ws_col = _trunc(r["id"], W_WS)
        nx_col = _trunc(r["description"], W_NX)
        up_col = _relative_time(r["last_edit"]) if r["last_edit"] > 0 else "—"

        print(
            f"{marker}  "
            f"{ws_col:<{W_WS}}  "
            f"{nx_col:<{W_NX}}  "
            f"{up_col:<{W_UP}}"
        )

    last_edit_label = (
        f"{last_edited_id} ({_relative_time(rows[0]['last_edit'])})" if last_edited_id else "(none)"
    )
    print()
    print(f"  {len(rows)} workspace(s)  |  last edited: {last_edit_label}")
    print()


def switch_workspace(ws_id: str) -> None:
    home = _home()
    reg_path = home / "state" / "workspaces.json"
    active_path = home / "state" / "active-workspace.json"

    if not reg_path.exists():
        print(f"Error: workspaces.json not found at {reg_path}", file=sys.stderr)
        sys.exit(1)

    try:
        registry: dict = json.loads(reg_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Error reading workspaces.json: {exc}", file=sys.stderr)
        sys.exit(1)

    if ws_id not in registry:
        print(f"Error: workspace '{ws_id}' not found in registry.", file=sys.stderr)
        print(f"Known workspaces: {', '.join(registry.keys())}", file=sys.stderr)
        sys.exit(1)

    entry = registry[ws_id]
    payload = {
        "workspace": ws_id,
        "workspace_path": entry.get("workspace_path", ""),
        "project_path": entry.get("project_path", ""),
    }

    try:
        active_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError as exc:
        print(f"Error writing active-workspace.json: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Switched to: {ws_id}")


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        switch_workspace(sys.argv[1])
    else:
        show_table()
