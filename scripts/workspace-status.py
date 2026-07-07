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
    """Max mtime of any file inside the workspace directory tree."""
    if not ws_path.is_dir():
        return 0.0
    _SKIP = {'.git', 'node_modules', '__pycache__', '.rag-index', '.claudeboost'}
    try:
        mtimes = []
        for root, dirs, files in os.walk(ws_path):
            dirs[:] = [d for d in dirs if d not in _SKIP and not d.startswith('.')]
            for f in files:
                try:
                    mtimes.append(os.path.getmtime(os.path.join(root, f)))
                except OSError:
                    pass
        return max(mtimes, default=0.0)
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


def _scan_local_workspaces(cwd: str) -> dict[str, Path]:
    """Return {folder_name: full_path} for each dir inside <cwd>/workspace/."""
    ws_dir = Path(cwd) / "workspace"
    if not ws_dir.is_dir():
        return {}
    return {d.name: d for d in ws_dir.iterdir() if d.is_dir() and not d.name.startswith('.')}


def _fuzzy_match(query: str, candidates: list[str]) -> list[str]:
    """Return candidates whose name contains query as a substring (case-insensitive)."""
    q = query.lower()
    return [c for c in candidates if q in c.lower()]


def show_table() -> None:
    home = _home()
    reg_path = home / "state" / "workspaces.json"
    cwd = os.getcwd()
    cwd_norm = _normalize_path(cwd)
    cb_home = _normalize_path(str(home))

    registry: dict = {}
    if reg_path.exists():
        try:
            registry = json.loads(reg_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"Error reading workspaces.json: {exc}", file=sys.stderr)
            sys.exit(1)

    def _matches(entry: dict) -> bool:
        pp = _normalize_path(entry.get("project_path", ""))
        return not pp or pp in (cwd_norm, cb_home)

    filtered = {k: v for k, v in registry.items() if _matches(v)}
    if not filtered and registry:
        filtered = registry

    # Merge in local workspace folders from <cwd>/workspace/
    local_dirs = _scan_local_workspaces(cwd)
    merged: dict[str, dict] = dict(filtered)
    for name, path in local_dirs.items():
        if name not in merged:
            merged[name] = {"workspace_path": str(path), "project_path": cwd, "_local_only": True}

    rows = []
    for ws_id, entry in merged.items():
        ws_path = Path(entry.get("workspace_path", ""))
        context_path = ws_path / "context.md"
        _, description, _ = _parse_context(context_path)
        last_edit = _workspace_last_edit(ws_path)
        rows.append({
            "id": ws_id,
            "description": description,
            "last_edit": last_edit,
            "local_only": entry.get("_local_only", False),
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
        local_tag = " (local)" if r.get("local_only") else ""
        ws_col = _trunc(r["id"] + local_tag, W_WS)
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


def _normalize_cwd() -> str:
    """Return CWD as a normalized string for use as a JSON key."""
    return os.getcwd().replace("\\", "/").rstrip("/")


def _read_instance_ws(inst_path: Path, cwd: str) -> str:
    """Read workspace for this CWD from per-instance file.

    New format: {cwd: workspace_id, ...} — each project tracked independently.
    Old format: {"workspace_id": "...", "cwd": "..."} — migrated on read.
    """
    try:
        data = json.loads(inst_path.read_text(encoding="utf-8"))
        cwd_norm = cwd.replace("\\", "/").rstrip("/")
        if "workspace_id" not in data:
            # New format
            ws = data.get(cwd_norm)
            if ws is None:
                cwd_lower = cwd_norm.lower()
                for key, val in data.items():
                    if isinstance(val, str) and key.replace("\\", "/").rstrip("/").lower() == cwd_lower:
                        ws = val
                        break
            return str(ws) if ws else ""
        # Old format — only valid if stored CWD matches
        stored = data.get("cwd", "").replace("\\", "/").rstrip("/")
        if stored.lower() == cwd_norm.lower():
            return str(data.get("workspace_id", "") or "")
        return ""
    except Exception:
        return ""


def _write_instance_ws(inst_path: Path, cwd: str, ws_id: str | None) -> None:
    """Write workspace for this CWD into the per-instance CWD-keyed map."""
    try:
        data = json.loads(inst_path.read_text(encoding="utf-8"))
        if "workspace_id" in data:
            data = {}  # migrate old single-value format
    except Exception:
        data = {}
    cwd_norm = cwd.replace("\\", "/").rstrip("/")
    if ws_id is None:
        data.pop(cwd_norm, None)
    else:
        data[cwd_norm] = ws_id
    inst_path.parent.mkdir(parents=True, exist_ok=True)
    inst_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


from workspace_identity import get_instance_id



def switch_workspace(ws_id: str) -> None:
    home = _home()
    reg_path = home / "state" / "workspaces.json"
    cwd = _normalize_cwd()

    instance_id = get_instance_id()

    if ws_id == "off":
        # Clear this CWD's entry from the per-instance file
        if instance_id:
            inst_path = home / "state" / "ws-instance" / f"{instance_id}.json"
            _write_instance_ws(inst_path, cwd, None)
        print("Cleared active workspace for this project (WS N/A)")
        return

    registry: dict = {}
    if reg_path.exists():
        try:
            registry = json.loads(reg_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"Error reading workspaces.json: {exc}", file=sys.stderr)
            sys.exit(1)

    # Exact match wins immediately
    if ws_id not in registry:
        # Fuzzy match against registered names
        fuzzy_reg = _fuzzy_match(ws_id, list(registry.keys()))

        # Also fuzzy match against local workspace folders in <cwd>/workspace/
        local_dirs = _scan_local_workspaces(cwd)
        fuzzy_local = _fuzzy_match(ws_id, list(local_dirs.keys()))

        # Merge, prefer registered matches first, deduplicate
        all_matches = list(dict.fromkeys(fuzzy_reg + [k for k in fuzzy_local if k not in fuzzy_reg]))

        if len(all_matches) == 0:
            print(f"Error: no workspace matching '{ws_id}' found.", file=sys.stderr)
            known = list(registry.keys()) + [k for k in local_dirs if k not in registry]
            print(f"Known: {', '.join(known)}", file=sys.stderr)
            sys.exit(1)

        if len(all_matches) > 1:
            print(f"Ambiguous: '{ws_id}' matches multiple workspaces: {', '.join(all_matches)}", file=sys.stderr)
            print("Be more specific.", file=sys.stderr)
            sys.exit(1)

        ws_id = all_matches[0]

        # If matched a local-only folder, auto-register it now
        if ws_id not in registry and ws_id in local_dirs:
            ws_path = str(local_dirs[ws_id])
            registry[ws_id] = {"workspace_path": ws_path, "project_path": cwd}
            reg_path.parent.mkdir(parents=True, exist_ok=True)
            reg_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
            print(f"Registered local workspace '{ws_id}' from {ws_path}")

    entry = registry[ws_id]

    # Write per-instance file — CWD-keyed map so each project tracks independently
    if instance_id:
        inst_path = home / "state" / "ws-instance" / f"{instance_id}.json"
        _write_instance_ws(inst_path, cwd, ws_id)

    print(f"Switched to: {ws_id}")


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        switch_workspace(sys.argv[1])
    else:
        show_table()
