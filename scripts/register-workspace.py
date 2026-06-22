"""
register-workspace.py — ClaudeBoost workspace registry utility.

Maintains $CLAUDEBOOST_HOME/state/workspaces.json so skills like /restore
and /clear-safe can locate project-scoped workspaces regardless of CWD.

Usage:
  python register-workspace.py <task_id> <workspace_path> [project_path] [--activate]
  python register-workspace.py --list
  python register-workspace.py --get <task_id>
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _home() -> Path:
    return Path(os.environ.get("CLAUDEBOOST_HOME") or Path(__file__).parent.parent)


def _reg_path() -> Path:
    return _home() / "state" / "workspaces.json"


def load_registry() -> dict:
    try:
        return json.loads(_reg_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_registry(reg: dict) -> None:
    p = _reg_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(reg, indent=2), encoding="utf-8")


def register(task_id: str, workspace_path: str, project_path: str = "") -> None:
    reg = load_registry()
    reg[task_id] = {
        "workspace_path": workspace_path,
        "project_path": project_path,
    }
    save_registry(reg)
    print(f"Registered: {task_id} -> {workspace_path}")


def _get_instance_id() -> str:
    session_id = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if session_id:
        return f"session-{session_id}"
    env_id = os.environ.get("CLAUDEBOOST_INSTANCE_ID", "")
    if env_id:
        return env_id
    return f"ppid-{os.getppid()}"


def activate(task_id: str, workspace_path: str, project_path: str = "") -> None:
    home = _home()
    p = home / "state" / "active-workspace.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(
            {"workspace": task_id, "workspace_path": workspace_path, "project_path": project_path},
            indent=2,
        ),
        encoding="utf-8",
    )

    # Write to per-instance file so the statusline picks it up for this session
    instance_id = _get_instance_id()
    inst_path = home / "state" / "ws-instance" / f"{instance_id}.json"
    cwd = (project_path or os.getcwd()).replace("\\", "/").rstrip("/")
    try:
        try:
            data = json.loads(inst_path.read_text(encoding="utf-8"))
            if "workspace_id" in data:
                data = {}
        except Exception:
            data = {}
        data[cwd] = task_id
        inst_path.parent.mkdir(parents=True, exist_ok=True)
        inst_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass

    print(f"Activated: {task_id}")


def get_workspace_path(task_id: str) -> str | None:
    reg = load_registry()
    entry = reg.get(task_id)
    if entry:
        return entry.get("workspace_path")
    return None


def list_workspaces() -> None:
    reg = load_registry()
    if not reg:
        print("No project-scoped workspaces registered.")
        return
    for task_id, entry in reg.items():
        wp = entry.get("workspace_path", "")
        pp = entry.get("project_path", "")
        ctx = Path(wp) / "context.md"
        tkt = Path(wp) / "ticket.md"
        if ctx.exists() or tkt.exists():
            print(f"WORKSPACE:{task_id} (project: {pp})")
            if tkt.exists():
                lines = tkt.read_text(encoding="utf-8", errors="replace").splitlines()[:5]
                print("\n".join(lines))
            print("---")


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__, file=sys.stderr)
        return 1

    if args[0] == "--list":
        list_workspaces()
        return 0

    if args[0] == "--get":
        if len(args) < 2:
            print("Usage: register-workspace.py --get <task_id>", file=sys.stderr)
            return 1
        result = get_workspace_path(args[1])
        if result:
            print(result)
            return 0
        return 1

    if len(args) < 2:
        print("Usage: register-workspace.py <task_id> <workspace_path> [project_path] [--activate]", file=sys.stderr)
        return 1

    positional = [a for a in args if not a.startswith("--")]
    do_activate = "--activate" in args

    task_id = positional[0]
    workspace_path = positional[1]
    project_path = positional[2] if len(positional) > 2 else ""

    register(task_id, workspace_path, project_path)
    if do_activate:
        activate(task_id, workspace_path, project_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
