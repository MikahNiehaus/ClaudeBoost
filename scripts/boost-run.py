#!/usr/bin/env python3
"""boost-run.py — single-call ClaudeBoost activation orchestrator.

Runs the whole /boost flow in one process so the slash command needs exactly one
Bash call. That sidesteps the three things that used to make /boost fight itself:
  - bash-guard.py blocks bare $VAR expansion  -> we read os.environ here, no $VAR
  - bash-guard.py blocks multiline `python -c` -> this is a real file, run directly
  - macOS has no bare `python`                 -> the command calls python3 once

Invoked by .claude/commands/boost.md as:
    python3 "${CLAUDEBOOST_HOME}/scripts/boost-run.py" verify

Arguments: verify | true | false | (empty == verify)

Prints a human-readable report Claude relays to the user. Exit is always 0 for
verify/true/false — activation surfaces problems in the report rather than
hard-failing the command. A nonzero exit only happens on a usage error.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PORT = 8612
BASE = f"http://127.0.0.1:{PORT}"

BOOST_HOME = Path(os.environ.get("CLAUDEBOOST_HOME") or Path(__file__).resolve().parent.parent)
SCRIPTS = BOOST_HOME / "scripts"
STATE = BOOST_HOME / "state"
PY = sys.executable


def _temp_dir() -> Path:
    # Match session-primer.py: TEMP, then TMPDIR, then /tmp.
    return Path(os.environ.get("TEMP") or os.environ.get("TMPDIR") or "/tmp")


def _run(args: list[str], timeout: int = 60) -> tuple[int, str]:
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s"
    except FileNotFoundError as e:
        return 127, str(e)


def _get(path: str, timeout: int = 5) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read())


def _post(path: str, body: dict, timeout: int = 300) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        BASE + path, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _write_injection(mode: str) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / "boost-injection.json").write_text(
        json.dumps({"mode": mode}), encoding="utf-8"
    )


# ---------------------------------------------------------------------------


def step_banner() -> None:
    rc, out = _run([PY, str(SCRIPTS / "boost-inline.py")])
    if out:
        print(out.rstrip("\n"))
    # Clear stale bytecode so a hot-reload picks up edited server modules.
    cleared = 0
    for p in (BOOST_HOME / "mcp-rag-server").rglob("__pycache__"):
        shutil.rmtree(p, ignore_errors=True)
        cleared += 1
    print(f"  caches cleared ({cleared})")


def step_privacy() -> None:
    on = []
    for var in ("DISABLE_TELEMETRY", "DISABLE_ERROR_REPORTING"):
        on.append(f"{var}={'1' if os.environ.get(var) else 'unset'}")
    print("  privacy: " + ", ".join(on))


def step_rag() -> dict:
    """Start the server, wait for ready, heal a dim mismatch, prime + index.

    Returns a dict the report builder consumes.
    """
    out = {"ready": False}
    rc, start_out = _run([PY, str(SCRIPTS / "rag-server-start.py")], timeout=90)
    last = start_out.strip().splitlines()[-1] if start_out.strip() else ""
    print(f"  rag-server: {last or ('exit ' + str(rc))}")

    # Wait for /status ready.
    status = None
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            status = _get("/status", timeout=3)
            if status.get("status") == "ready":
                break
        except Exception:
            pass
        time.sleep(2)
    if not status or status.get("status") != "ready":
        print("  RAG: NOT READY — server did not respond. Run /rag and retry.")
        return out

    # status=ready only means the HTTP layer is up — the embedding model loads in a
    # background thread and may still be cold. Block on /warmup so the calls below
    # (heal, context, index) don't fire against a half-loaded model and 500. Then
    # re-fetch status: embedding_dimensions and dimension_mismatch only populate once
    # the model is loaded.
    try:
        warm = _post("/warmup", {}, timeout=180)
        if not warm.get("ready"):
            print(f"  RAG: model warmup did not finish — {warm.get('error', 'unknown')}")
        status = _get("/status", timeout=5)
    except Exception as e:
        print(f"  RAG: warmup failed — {e}")

    out["ready"] = True
    out["status"] = status
    cols = status.get("collections", {})
    k = cols.get("knowledge", {})
    a = cols.get("agents", {})
    print(
        f"  RAG: ready | model={status.get('model')} dim={status.get('embedding_dimensions')} "
        f"| knowledge {k.get('chunks', 0)}ch/{k.get('files', 0)}f "
        f"| agents {a.get('chunks', 0)}ch/{a.get('files', 0)}f"
    )

    # Sentinel — lets the session-primer hook stop nagging about RAG.
    try:
        (_temp_dir() / "claudeboost_rag_ok").touch()
    except Exception as e:
        print(f"  (sentinel write failed: {e})")

    # Heal a dimension mismatch (stale collection embedded with a different model).
    mismatch = [s for s in status.get("dimension_mismatch", []) if s != "memories"]
    out["healed"] = []
    if mismatch:
        print(f"  DIM MISMATCH in {mismatch} — model swap left these unqueryable. Rebuilding...")
        for scope in mismatch:
            try:
                r = _post("/index", {"scope": scope, "force": True}, timeout=600)
                print(
                    f"    rebuilt {scope}: {r.get('files_indexed', '?')} files, "
                    f"{r.get('chunks_created', '?')} chunks"
                )
                out["healed"].append(scope)
            except Exception as e:
                print(f"    rebuild {scope} FAILED: {e}")

    # Prime tiered context.
    try:
        ctx = _post(
            "/context",
            {"agent": "debug-agent", "task_description": "session start", "max_tokens": 2000},
            timeout=30,
        )
        print(f"  context: tokens={ctx.get('total_tokens_approx')} sources={ctx.get('sources_used')}")
    except Exception as e:
        print(f"  context: FAILED — {e}")

    # Index the ClaudeBoost codebase (incremental).
    try:
        idx = _post("/index", {"project_path": str(BOOST_HOME)}, timeout=600)
        g = idx.get("graph", {})
        print(
            f"  index(self): {idx.get('files_indexed', 0)} files, {idx.get('chunks_created', 0)} chunks, "
            f"graph {g.get('resolved', '?')}/{g.get('edges', '?')}, failed {idx.get('files_failed', 0)}"
        )
        out["self_index"] = idx
    except Exception as e:
        print(f"  index(self): FAILED — {e}")

    # Index memories (no-op if the memory dir is empty / absent).
    try:
        mem = _post("/index", {"scope": "memories"}, timeout=120)
        print(f"  memories: {mem.get('chunks_created', mem.get('chunks', 0))} chunks")
    except Exception as e:
        print(f"  memories: skipped — {e}")

    return out


def step_hooks() -> list[str]:
    missing = []
    for hook in ("SessionStart", "PreToolUse", "PostToolUse", "PreCompact", "UserPromptSubmit", "Stop"):
        rc, _ = _run([PY, str(SCRIPTS / "check-hooks.py"), hook], timeout=15)
        if rc != 0:
            missing.append(hook)
    if missing:
        print(f"  hooks: MISSING {missing} — run setup.py")
    else:
        print("  hooks: all 6 present")
    return missing


def step_rules() -> bool:
    rules = Path.home() / ".claude" / "CLAUDE.md"
    ok = rules.is_file()
    print("  rules: CLAUDE.md loaded" if ok else "  rules: MISSING ~/.claude/CLAUDE.md")
    return ok


def step_mode() -> str:
    mode_file = STATE / "claudeboost-mode.json"
    mode = "CONSULT"
    if mode_file.is_file():
        try:
            mode = json.loads(mode_file.read_text(encoding="utf-8")).get("mode", "CONSULT").upper()
        except Exception:
            pass
    # Session approvals never carry across sessions.
    sa = STATE / "session-approvals.json"
    if sa.is_file():
        sa.write_text(json.dumps({"sessionId": "", "approvals": []}), encoding="utf-8")
    print(f"  mode: {mode}")
    return mode


def step_mcp_debugger() -> str:
    rc, out = _run(["claude", "mcp", "list"], timeout=20)
    if rc == 127:
        print("  mcp-debugger: not checked (claude CLI not on PATH)")
        return "unknown"
    line = next((l for l in out.splitlines() if "mcp-debugger" in l.lower()), "")
    if not line:
        print("  mcp-debugger: NOT registered — claude mcp add mcp-debugger --scope user -- npx -y @debugmcp/mcp-debugger stdio")
        return "missing"
    if "connected" in line.lower() or "✓" in line:
        print("  mcp-debugger: connected")
        return "connected"
    print(f"  mcp-debugger: registered but not healthy ({line.strip()})")
    return "unhealthy"


def step_workspaces() -> list[str]:
    """Scan cwd/workspace for active tasks. cwd is the project being worked on."""
    active = []
    ws = Path.cwd() / "workspace"
    if ws.is_dir():
        for d in sorted(ws.iterdir()):
            ctx = d / "context.md"
            if not ctx.is_file():
                continue
            try:
                text = ctx.read_text(encoding="utf-8", errors="replace").lower()
            except Exception:
                continue
            if any(s in text for s in ("in progress", "plan_ready", "implemented", "blocked")):
                active.append(d.name)
    if active:
        print(f"  workspaces: ACTIVE {active}")
    else:
        print("  workspaces: none active")
    return active


def main() -> int:
    arg = (sys.argv[1] if len(sys.argv) > 1 else "verify").strip().lower()

    if arg == "true":
        _write_injection("true")
        print("Switched to: ON. Always-on rules inject on every prompt. RAG standing orders skip until /boost verify.")
        return 0
    if arg == "false":
        _write_injection("false")
        print("Switched to: OFF. No rules inject until /boost true or /boost verify.")
        return 0
    if arg not in ("verify", ""):
        print(f"Unknown argument: {arg!r}. Use: verify | true | false")
        return 2

    _write_injection("verify")

    step_banner()
    print("\n--- privacy ---")
    step_privacy()
    print("\n--- RAG (port 8612) ---")
    rag = step_rag()
    print("\n--- hooks ---")
    missing_hooks = step_hooks()
    print("\n--- rules ---")
    rules_ok = step_rules()
    print("\n--- mode ---")
    mode = step_mode()
    print("\n--- mcp-debugger ---")
    step_mcp_debugger()
    print("\n--- workspaces ---")
    active = step_workspaces()

    # Closing banner only when the critical system (RAG) is up.
    if rag.get("ready"):
        rc, out = _run([PY, str(SCRIPTS / "boost-inline.py"), "--done"])
        if out:
            print(out.rstrip("\n"))

    # Machine-readable tail so Claude can act (e.g. read a single active workspace).
    print("\n=== BOOST_SUMMARY ===")
    print(json.dumps({
        "rag_ready": rag.get("ready", False),
        "healed_scopes": rag.get("healed", []),
        "missing_hooks": missing_hooks,
        "rules_ok": rules_ok,
        "mode": mode,
        "active_workspaces": active,
        "project_cwd": str(Path.cwd()),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
