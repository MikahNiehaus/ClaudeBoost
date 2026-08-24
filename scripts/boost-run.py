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
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from rag_port import rag_port

# Was 8612, the retired bundled server. rag_port reads the live number from
# clean-rag's own config so this file cannot drift out of date again.
PORT = rag_port()
BASE = f"http://127.0.0.1:{PORT}"

BOOST_HOME = Path(os.environ.get("CLAUDEBOOST_HOME") or Path(__file__).resolve().parent.parent)
SCRIPTS = BOOST_HOME / "scripts"
STATE = BOOST_HOME / "state"
PY = sys.executable


def _number_or_zero(value) -> float:
    """A count from a JSON body, tolerant of a string or a missing field.

    /status is parsed straight off the wire, so a field can arrive as "12"
    rather than 12. Comparing a str to an int raises, and a health check that
    raises reports nothing at all.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


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
    # Points at clean-rag now; mcp-rag-server was the retired 8612 server and
    # its tree is gone, so this loop was iterating over nothing.
    cleared = 0
    for p in (BOOST_HOME / "clean-rag").rglob("__pycache__"):
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
    # clean-rag's own control CLI. This used to call scripts/rag-server-start.py,
    # which started the retired 8612 server; both that script and the server it
    # started are gone.
    rc, start_out = _run(
        [PY, str(BOOST_HOME / "clean-rag" / "cli" / "server_ctl.py"), "start"],
        timeout=90,
    )
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

    # The HTTP layer answers before the embedding model has loaded, so indexing
    # below would fire against a cold model. There is no /warmup route on
    # clean-rag; it reports the three states directly on /status, so poll that:
    # "ready" once the model is in, "failed" when the load raised and no amount
    # of waiting will help, "warming_up" while it is still coming.
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        try:
            status = _get("/status", timeout=5)
        except Exception as e:
            print(f"  RAG: status check failed — {e}")
            break
        state = status.get("status")
        if state == "ready":
            break
        if state == "failed":
            print(f"  RAG: model will not load — {status.get('last_error', 'unknown')}")
            break
        time.sleep(3)
    else:
        print("  RAG: model still warming after 180s, continuing anyway")

    out["ready"] = True
    out["status"] = status
    # Reports indexed projects, which is what clean-rag's /status actually
    # returns. It used to print `collections.knowledge` and `collections.agents`
    # chunk counts; those were the retired 8612 server's shape, and both the
    # collections and the directories behind them are gone.
    projects = status.get("projects", {})
    print(
        f"  RAG: ready | model={status.get('code_embedding_model')} "
        f"| {projects.get('count', 0)} project(s) indexed "
        f"| {status.get('ram_mb', 0)} MB"
    )

    # Sentinel — lets the session-primer hook stop nagging about RAG.
    try:
        (_temp_dir() / "claudeboost_rag_ok").touch()
    except Exception as e:
        print(f"  (sentinel write failed: {e})")

    # The scope rebuild loop that lived here healed a dimension mismatch on the
    # knowledge and agents collections. Those were 8612 concepts: clean-rag has
    # no scopes, and it reports a per project provenance mismatch through
    # `stale_projects` on a search instead, which names the project and the
    # model it was built with.
    out["healed"] = []
    # Two things were wrong here and each hid the other.
    #
    # `entries` is a dict keyed by project hash, not a list, so iterating it
    # yielded the keys. Calling .get on a str raised AttributeError and took
    # the whole of /boost down before it printed a single check.
    #
    # And `incomplete` is not a field clean-rag writes. An entry carries
    # project_path, files_indexed, chunks_created, graph, indexed_at, server
    # and source. So even with the iteration fixed the test could never fire.
    # files_indexed is the real signal, and it is the one rag-enforce already
    # keys on in _has_real_index: a registered project with nothing behind it.
    entries = status.get("projects", {}).get("entries", {})
    values = entries.values() if isinstance(entries, dict) else entries
    stale = [
        e for e in values
        if isinstance(e, dict) and not _number_or_zero(e.get("files_indexed"))
    ]
    if stale:
        names = ", ".join(
            str(e.get("project_path", "?")).rsplit("/", 1)[-1] for e in stale[:3]
        )
        print(f"  {len(stale)} project(s) registered with an empty index ({names}); "
              f"run /index-project on them, searches over them return nothing")

    # Index the ClaudeBoost codebase (incremental).
    try:
        idx = _post("/index-project", {"project_path": str(BOOST_HOME)}, timeout=600)
        g = idx.get("graph", {})
        print(
            f"  index(self): {idx.get('files_indexed', 0)} files, {idx.get('chunks_created', 0)} chunks, "
            f"graph {g.get('resolved', '?')}/{g.get('edges', '?')}, failed {idx.get('files_failed', 0)}"
        )
        out["self_index"] = idx
    except Exception as e:
        print(f"  index(self): FAILED — {e}")

    # A "memories" scope index used to run here. Scopes were an 8612 concept and
    # clean-rag has none; memory files are read directly from disk by the
    # session hooks, not searched, so there is nothing to index.

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

    # Verify telemetry sentinels are wired (added by telemetry feature).
    # These sit inside existing event types so check-hooks.py won't catch them.
    try:
        import json
        settings_path = Path.home() / ".claude" / "settings.json"
        s = json.loads(settings_path.read_text(encoding="utf-8"))
        hooks_cfg = s.get("hooks", {})
        all_hook_text = json.dumps(hooks_cfg)
        for sentinel in ("telemetry-session.py", "telemetry-hook.py"):
            if sentinel not in all_hook_text:
                missing.append(f"telemetry:{sentinel}")
        if any(h.startswith("telemetry:") for h in missing):
            print("  telemetry hooks: MISSING — run setup.py")
        else:
            print("  telemetry hooks: present")
    except Exception:
        pass

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


# Mirrors setup.py's MCP_SERVERS table. Kept as (name, fix-hint) pairs rather
# than imported so /boost verify stays a standalone script with no import path
# into scripts/setup.py. Adding a server there means adding it here too.
MCP_SERVERS_EXPECTED: list[tuple[str, str]] = [
    ("mcp-debugger", "claude mcp add mcp-debugger --scope user -- npx -y @debugmcp/mcp-debugger stdio"),
    ("playwright", "claude mcp add playwright --scope user -- npx -y @playwright/mcp@latest"),
    ("test-coverage", "claude mcp add test-coverage --scope user -- npx -y test-coverage-mcp"),
    ("chrome-devtools", "claude mcp add chrome-devtools --scope user -- npx -y chrome-devtools-mcp@latest"),
    # mdb (native GDB/LLDB) is optional — setup.py only registers it if the
    # clone and its deps both land, so a missing one is not a health failure.
]


def parse_mcp_list(stdout: str) -> dict[str, str]:
    """Map each server name in `claude mcp list` output to its OWN status text.

    Mirrors setup.py's parse_mcp_list for the same standalone-script reason as
    MCP_SERVERS_EXPECTED above. Real output is a header line then one server
    per line, `<name>: <command-or-url> - <status>`:

        mcp-debugger: npx -y @debugmcp/mcp-debugger stdio - ✔ Connected
        claude.ai GitHub: https://api.githubcopilot.com/mcp - ! Needs authentication

    Names can contain spaces and commands can contain colons, so the name is
    everything before the FIRST ": " and the status everything after the LAST
    " - ". Matching a bare substring against the whole output instead reports
    "mdb" registered when only an unrelated "cmdb" is.
    """
    servers: dict[str, str] = {}
    for line in stdout.splitlines():
        name, sep, rest = line.partition(": ")
        if not sep or not name.strip():
            continue
        _, dash, status = rest.rpartition(" - ")
        servers[name.strip()] = status.strip() if dash else ""
    return servers


def step_mcp_debugger() -> str:
    """Health-check every debugging MCP server. Worst status wins."""
    rc, out = _run(["claude", "mcp", "list"], timeout=20)
    if rc == 127:
        print("  MCP servers: not checked (claude CLI not on PATH)")
        return "unknown"

    servers = parse_mcp_list(out)
    worst = "connected"
    for name, fix in MCP_SERVERS_EXPECTED:
        status = servers.get(name)
        if status is None:
            print(f"  {name}: NOT registered — {fix}")
            worst = "missing"
        elif re.search(r"\bconnected\b", status, re.IGNORECASE):
            print(f"  {name}: connected")
        else:
            print(f"  {name}: registered but not healthy ({status})")
            if worst != "missing":
                worst = "unhealthy"

    if "mdb" in servers:
        print("  mdb: registered (native GDB/LLDB, optional)")

    return worst


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
    print(f"\n--- RAG (port {PORT}) ---")
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
