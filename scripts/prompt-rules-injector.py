#!/usr/bin/env python3
"""
prompt-rules-injector.py — UserPromptSubmit hook.

Injects the real clean-rag search contract and the behavioural rules into every
user prompt, so Claude always knows where to search and what rules to follow.

This block used to describe four "RAG tiers" against port 8612 with a `scope`
parameter, a `POST /index` route and a `POST /context` route. None of that
exists. 8612 was retired (see clean-rag/CLAUDE.md, "Why the KB is gone"), the
live server takes `sources` rather than `scope`, and only three of those four
tiers were ever registered as searchable projects: the KB directories are files
on disk that nothing ever indexed.

Because this text lands in front of every single turn, it outranked the correct
guidance in CLAUDE.md and taught the dead API to 16 command files. Keep it
honest: state only what the server actually serves, name the port, and read the
port from clean-rag's own config rather than writing it down again here.

Intent override: if the user opened Claude in a directory that isn't the
project they're working in, they can set an override so the injector uses
the correct project path. Set via /edit-state or manually in
state/intent-override.json → {instance_id: "C:/correct/project"}.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


from hook_session_state import digest, read_payload, read_state, session_key, write_state
from workspace_identity import get_instance_id


def _resolve_project_path(boost_home: Path, instance_id: str, cwd: str) -> str:
    """Return the effective project path, honouring any intent override."""
    override_path = boost_home / "state" / "intent-override.json"
    try:
        overrides = json.loads(override_path.read_text(encoding="utf-8"))
        override = overrides.get(instance_id) or overrides.get("default")
        if override and isinstance(override, str):
            return override.replace("\\", "/").rstrip("/")
    except Exception:
        pass
    return cwd


def _active_workspace_id(boost_home: Path, instance_id: str, project_path: str) -> str | None:
    """Read the active workspace ID for this project from the per-instance file."""
    inst_path = boost_home / "state" / "ws-instance" / f"{instance_id}.json"
    try:
        data = json.loads(inst_path.read_text(encoding="utf-8"))
        cwd_norm = project_path.replace("\\", "/").rstrip("/")
        if "workspace_id" not in data:
            ws = data.get(cwd_norm)
            if ws is None:
                cwd_lower = cwd_norm.lower()
                for key, val in data.items():
                    if isinstance(val, str) and key.replace("\\", "/").rstrip("/").lower() == cwd_lower:
                        ws = val
                        break
            return str(ws) if ws else None
        stored = data.get("cwd", "").replace("\\", "/").rstrip("/")
        ws = data.get("workspace_id") if stored.lower() == project_path.lower() else None
        return str(ws) if ws else None
    except Exception:
        return None


def _rag_port(boost_home: Path) -> int:
    """The clean-rag port, from clean-rag's own config rather than a literal.

    Hardcoding it here is how this file came to advertise 8612 long after that
    server was retired. `clean-rag/server/config.py` owns the number, and
    `clean-rag/cli/server_ctl.py:37-42` already imports it exactly this way.
    """
    try:
        root = str(boost_home / "clean-rag")
        if root not in sys.path:
            sys.path.insert(0, root)
        from server.config import STANDALONE_PORT
        return int(STANDALONE_PORT)
    except Exception:
        return 8613


def _is_indexed(boost_home: Path, project_path: str) -> bool:
    """Is this project in clean-rag's registry?

    Advertising a `project:` source for something never indexed is how the old
    block sent every search at nothing. Say so instead.
    """
    registry = boost_home / "clean-rag" / "state" / "projects.json"
    try:
        entries = json.loads(registry.read_text(encoding="utf-8"))
    except Exception:
        return True  # cannot tell, do not cry wolf
    target = project_path.replace("\\", "/").rstrip("/").lower()
    return any(
        str(e.get("project_path", "")).replace("\\", "/").rstrip("/").lower() == target
        for e in entries.values()
    )


def _project_kb_exists(project_path: str) -> bool:
    return (Path(project_path) / ".claudeboost" / "knowledge").is_dir()


def _workspace_kb_exists(project_path: str, workspace_id: str) -> bool:
    return (Path(project_path) / "workspace" / workspace_id / "knowledge").is_dir()


def main() -> None:
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    payload = read_payload(raw)

    boost_home = Path(os.environ.get("CLAUDEBOOST_HOME") or Path(__file__).parent.parent)
    cwd = os.getcwd().replace("\\", "/").rstrip("/")
    instance_id = get_instance_id()
    project_path = _resolve_project_path(boost_home, instance_id, cwd)
    workspace_id = _active_workspace_id(boost_home, instance_id, project_path)

    project_kb_path = f"{project_path}/.claudeboost/knowledge/"
    workspace_kb_path = (
        f"{project_path}/workspace/{workspace_id}/knowledge/"
        if workspace_id else None
    )

    has_project_kb = _project_kb_exists(project_path)
    has_workspace_kb = workspace_id and _workspace_kb_exists(project_path, workspace_id)

    RAG_BASE = f"http://127.0.0.1:{_rag_port(boost_home)}"
    boost_path = str(boost_home).replace("\\", "/").rstrip("/")
    project_indexed = _is_indexed(boost_home, project_path)

    lines = [
        f"[RAG — one server, {RAG_BASE}]",
        f"Search: POST {RAG_BASE}/search",
        f'  {{"query":"...","sources":["project:{project_path}"],"mode":"both","limit":8}}',
        "  Takes `sources`, a list of `project:<absolute path>`. There is no `scope`"
        " parameter. `mode: \"both\"` runs vector similarity and import graph together"
        " and is what you want on a code search; they surface different files.",
        f"  This project: project:{project_path}"
        f"{'' if project_indexed else '   [NOT INDEXED, see /index-project below]'}",
        f"  How ClaudeBoost itself works (agents, skills, hooks): project:{boost_path}",
        f"Index a project: POST {RAG_BASE}/index-project {{\"project_path\":\"...\"}}",
        f"Outside sources: POST {RAG_BASE}/web-search, /github-search, /github-file,"
        " /stackoverflow-search. Survey with snippets, fetch a full page only when"
        " you need the substance.",
    ]

    # Only mention a KB directory that is really there, and say plainly that it
    # is a directory to read rather than a search source. These used to be
    # advertised as searchable tiers; nothing ever indexed them, so every call
    # against them returned nothing.
    kb_notes = []
    if has_project_kb:
        kb_notes.append(f"  {project_kb_path}  (project research docs)")
    if has_workspace_kb:
        kb_notes.append(f"  {workspace_kb_path}  (task docs for {workspace_id})")
    if kb_notes:
        lines.append(
            "Directories to READ, not search. They are not registered projects,"
            " so a project: source naming them returns nothing:"
        )
        lines += kb_notes
    elif workspace_id is None:
        lines.append("No workspace active (run /ws <id> to set one).")

    lines += [
        "When spawning an agent, give it the search line above verbatim. Agents"
        " get this same injected block, so do not paste a different one.",
    ]

    # The [Rules] paragraph that used to sit here (plain writing, no dashes,
    # confirm before irreversible actions, keep context.md current) moved into
    # CLAUDE.md under "Always on rules". It was identical on every prompt, so
    # every turn paid to carry another copy of it. CLAUDE.md is read once into
    # the cached prefix instead.

    if workspace_id:
        lines.append(
            f"[Workspace active: {workspace_id}] Update workspace/{workspace_id}/context.md after every significant finding, decision, or file read."
        )

    block = "\n".join(lines)

    # What is left is the search contract, and it only changes when the project
    # path, the index state or the active workspace changes. Say it when it is
    # new, then stay quiet.
    key = session_key(payload)
    sig = digest(block)
    if read_state("rules", key).get("sig") == sig:
        return
    write_state("rules", key, {"sig": sig})

    print(block)


if __name__ == "__main__":
    main()
