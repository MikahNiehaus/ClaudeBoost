"""
session-primer.py emits deltas, not a fixed block, driven through the real
script end to end with the stdin payload Claude Code actually sends.

The behavior these lock down is easy to regress into "inject everything every
time", which is what this replaced: a constant 1,437 token block on every
prompt, re-read by every later request, about 86k tokens of pure repetition by
turn 60.

Two failure modes matter more than the token count and each has a test here:

- A warning that fires once and can never fire again. The old auto recovery
  touched the sentinel optimistically, so a server that never came up still
  read as healthy. Under delta emission that would silently swallow the offline
  warning for the rest of the session.
- A block whose text drifts every prompt, so the change detection never calls
  it unchanged and it reprints forever. The workspace dashboard used to echo
  the user's own message back, which did exactly that.

Run: python -m pytest tests/test_session_primer_deltas.py -v
"""

import json
import os
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PRIMER = REPO / "scripts" / "session-primer.py"


def _closed_port() -> int:
    """A port with nothing on it, so the health probe fails for real."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _StatusHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"status": "ready", "indexed_projects": []}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def live_server():
    """A stand in for clean-rag that answers GET /status."""
    srv = HTTPServer(("127.0.0.1", 0), _StatusHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv.server_address[1]
    srv.shutdown()
    srv.server_close()


@pytest.fixture
def home(tmp_path):
    """A CLAUDEBOOST_HOME with just the state files the hook reads."""
    state = tmp_path / "state"
    state.mkdir(parents=True)
    (state / "boost-injection.json").write_text(json.dumps({"mode": "verify"}))
    (state / "claudeboost-mode.json").write_text(json.dumps({"mode": "CONSULT"}))
    (state / "workspaces.json").write_text(json.dumps({}))
    (tmp_path / "CLAUDE.md").write_text("# test\n")
    return tmp_path


@pytest.fixture
def temp(tmp_path):
    d = tmp_path / "hooktmp"
    d.mkdir()
    return d


def run_primer(home, temp, prompt, port, session_id="s1"):
    """One prompt through the hook. Returns the injected context, or ''."""
    env = dict(os.environ)
    env["CLAUDEBOOST_HOME"] = str(home)
    env["TMPDIR"] = str(temp)
    env["TEMP"] = str(temp)
    env["CLEAN_RAG_PORT"] = str(port)
    payload = json.dumps({
        "prompt": prompt,
        "session_id": session_id,
        "cwd": str(home),
        "hook_event_name": "UserPromptSubmit",
    })
    proc = subprocess.run(
        [sys.executable, str(PRIMER)],
        input=payload, capture_output=True, text=True,
        env=env, cwd=str(home), timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.strip()
    if not out:
        return ""
    return json.loads(out).get("additionalContext", "")


def set_mode(home, mode):
    (home / "state" / "claudeboost-mode.json").write_text(json.dumps({"mode": mode}))


# The prompts differ on purpose. Identical text would pass even if the hook
# were keyed on the message rather than on state.
P1 = "please refactor the search module and add tests for it"
P2 = "now update the docs to match that change"
P3 = "and run the full test suite for me"


def test_steady_state_emits_only_the_pointer(home, temp, live_server):
    """Nothing changed between prompts, so nothing but the pointer is repeated."""
    run_primer(home, temp, P1, live_server)
    second = run_primer(home, temp, P2, live_server)
    third = run_primer(home, temp, P3, live_server)

    assert "CLAUDE.md" in second
    assert second == third, "steady state output must not drift between prompts"
    # Generous ceiling. The point is that it is a pointer, not a rulebook.
    assert len(second) < 200, f"steady state grew to {len(second)} chars: {second!r}"


def test_steady_state_never_restates_the_old_rules(home, temp, live_server):
    """The A to H block and the standing orders belong in CLAUDE.md now."""
    run_primer(home, temp, P1, live_server)
    later = run_primer(home, temp, P2, live_server)

    for gone in ("ALWAYS-ON RULES", "RAG STANDING ORDERS", "Human voice",
                 "Irreversible actions", "delve", "8612", "POST /context"):
        assert gone not in later, f"{gone!r} is back in the per prompt injection"


def test_offline_warning_fires_once_then_stops(home, temp):
    """A transition is worth saying. Repeating it every prompt is not."""
    dead = _closed_port()
    first = run_primer(home, temp, P1, dead)
    second = run_primer(home, temp, P2, dead)

    assert "OFFLINE" in first
    assert "OFFLINE" not in second, "offline warning repeated while nothing changed"


def test_offline_warning_can_fire_again_after_recovery(home, temp, live_server):
    """
    The regression that motivated probing the server instead of the sentinel.

    Auto recovery touches the sentinel before the daemon is up. If online were
    read from that file, one failed launch would mark the session healthy
    forever and this second warning would never appear.
    """
    dead = _closed_port()
    assert "OFFLINE" in run_primer(home, temp, P1, dead)
    assert "back online" in run_primer(home, temp, P2, live_server)
    assert "OFFLINE" in run_primer(home, temp, P3, dead)


def test_back_online_is_silent_on_the_first_prompt(home, temp, live_server):
    """A healthy server at session start is the normal case, not news."""
    first = run_primer(home, temp, P1, live_server)
    assert "back online" not in first


def test_consult_toggle_announced_only_on_change(home, temp, live_server):
    run_primer(home, temp, P1, live_server)
    assert "AUTO" not in run_primer(home, temp, P2, live_server)

    set_mode(home, "AUTO")
    switched = run_primer(home, temp, P3, live_server)
    assert "AUTO mode is now ON" in switched

    assert "AUTO mode is now ON" not in run_primer(home, temp, P1, live_server)


def test_short_prompts_are_skipped(home, temp, live_server):
    assert run_primer(home, temp, "ok", live_server) == ""


def test_sessions_do_not_share_delta_state(home, temp):
    """
    Two conversations in parallel each need their own orientation.

    These files were keyed on os.getpid() before. A hook is a fresh process
    every prompt, so that key never repeated and the state never survived.

    Driven with the server down, because that is a signal a fresh session must
    see and a continuing one must not repeat. With the server up there is
    nothing to report either way and the test could not tell the two apart.
    """
    dead = _closed_port()
    a1 = run_primer(home, temp, P1, dead, session_id="alpha")
    a2 = run_primer(home, temp, P2, dead, session_id="alpha")
    b1 = run_primer(home, temp, P3, dead, session_id="beta")

    assert "OFFLINE" in a1
    assert "OFFLINE" not in a2, "alpha already knows, so it must not be told twice"
    assert "OFFLINE" in b1, "beta is a separate session and has not been told yet"


def test_clear_restore_survives_the_rewrite(home, temp, live_server):
    """The one shot post clear restore is not a delta and must still fire."""
    from datetime import datetime, timezone
    state = home / "state"
    (state / "clear-pending.json").write_text(json.dumps({
        "pending": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }))
    (state / "handoff-latest.json").write_text(json.dumps({
        "workspace_memo": "### ws-1\nhalfway through the port migration",
        "active_workspace": "",
        "handoff_message": "finish retiring 8612",
    }))

    out = run_primer(home, temp, P1, live_server)
    assert "POST-CLEAR CONTEXT RESTORATION" in out
    assert "halfway through the port migration" in out
    assert "finish retiring 8612" in out

    # One shot: the flag is consumed, so the next prompt is quiet again.
    assert "POST-CLEAR CONTEXT RESTORATION" not in run_primer(home, temp, P2, live_server)


def test_boost_false_emits_nothing(home, temp, live_server):
    (home / "state" / "boost-injection.json").write_text(json.dumps({"mode": "false"}))
    assert run_primer(home, temp, P1, live_server) == ""
