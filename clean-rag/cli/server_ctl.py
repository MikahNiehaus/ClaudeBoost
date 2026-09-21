"""Server control CLI for clean-rag.

Usage:
  python clean-rag/cli/server_ctl.py start     # windowless; CLEAN_RAG_HEADED=1 for a console
  python clean-rag/cli/server_ctl.py stop
  python clean-rag/cli/server_ctl.py restart
  python clean-rag/cli/server_ctl.py status

Or just double click runragserver.bat.

start is single instance and checks the port, so running it twice (or running
the .bat while a server is already up) is safe and does nothing.
"""

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

_CLEAN_RAG_HOME = Path(__file__).resolve().parent.parent


def _server_python() -> str:
    """The interpreter the server process runs on.

    Same shape as graphrag_client._venv_python, for the same reason: the heavy
    ML dependencies live in their own venv rather than wherever the launcher
    happens to have come from. This script itself is stdlib only, so it does not
    care which interpreter runs it; the server does.

    Falls back to sys.executable when the venv is absent, so a checkout that has
    not been installed yet still starts. That fallback is how the server ended up
    on the user's global packages in the first place, so it warns rather than
    failing silently: a broken global stack produces an import error at model
    load time, thousands of lines deep in a log, which is much harder to read
    than one line here.
    """
    scripts = "Scripts" if os.name == "nt" else "bin"
    exe = "python.exe" if os.name == "nt" else "python"
    venv_py = _CLEAN_RAG_HOME / "clean-rag-venv" / scripts / exe
    if venv_py.is_file():
        return str(venv_py)
    print(
        "[warn] clean-rag-venv not found, starting on "
        f"{sys.executable}. Run clean-rag/install.py to create it.",
        file=sys.stderr,
    )
    return sys.executable


def _state_dir() -> Path:
    # Add clean-rag root to path so server.config is importable
    _root = str(_CLEAN_RAG_HOME)
    if _root not in sys.path:
        sys.path.insert(0, _root)
    from server.config import STATE_DIR
    return STATE_DIR


def _port() -> int:
    _root = str(_CLEAN_RAG_HOME)
    if _root not in sys.path:
        sys.path.insert(0, _root)
    from server.config import STANDALONE_PORT
    return STANDALONE_PORT


def _port_in_use(port: int) -> bool:
    """Is anything already listening on this port?

    This, not the PID file, is the real single instance guard. The PID file
    lies: it goes stale when a server dies badly, and it knows nothing about a
    server someone started by hand or from the .bat. Observed for real this
    session, "stop" cheerfully reported success while a different live process
    was still holding 8613.

    Binding is the only honest test. If the bind fails, someone's home.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        # No SO_REUSEADDR on purpose. We want this to fail when the port is taken.
        try:
            sock.bind(("127.0.0.1", port))
            return False
        except OSError:
            return True


def cmd_start(args):
    state = _state_dir()
    state.mkdir(parents=True, exist_ok=True)
    server_json = state / "server.json"

    # An explicit start is the user changing their mind, so it retires the
    # stop marker.
    _clear_stopped_by_user(state)

    def _launch_console() -> None:
        """Open cli/console.py in its own window beside the windowless server.

        The server deliberately has no console of its own, and console.py is a
        Textual app, which needs a real terminal. CREATE_NEW_CONSOLE is the flag
        that gives a child one. It cannot be combined with DETACHED_PROCESS
        (Microsoft's process creation flags reference: DETACHED_PROCESS "cannot
        be used with CREATE_NEW_CONSOLE"), which is why this is a second spawn
        rather than a flag on the server's.

        server/graphrag_client.py already opens a watchable window this exact
        way, so this follows the shape the codebase has rather than a new one.

        On by default, because the server having no visible output and the UI
        never starting meant indexing was invisible unless someone remembered
        to run a second command. CLEAN_RAG_CONSOLE=0 turns it off, which is what
        automation and CI should set.

        Never raises. A missing terminal, a headless box or a missing textual
        must not stop the server from starting, so every failure here is
        swallowed. console.py also guards its own textual import and only ever
        talks to the server over HTTP and the log file, so a dead console cannot
        affect a live server.
        """
        if os.environ.get("CLEAN_RAG_CONSOLE") == "0":
            return
        if sys.platform != "win32":
            # CREATE_NEW_CONSOLE has no POSIX equivalent that works without
            # knowing which terminal emulator is installed. Left unimplemented
            # rather than guessed at.
            return
        console_script = _CLEAN_RAG_HOME / "cli" / "console.py"
        if not console_script.exists():
            return
        try:
            subprocess.Popen(
                [_server_python(), str(console_script)],
                cwd=str(_CLEAN_RAG_HOME),
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        except Exception as exc:
            print(f"Console UI did not start ({type(exc).__name__}). Server is unaffected.")

    port = _port()

    # Single instance. Checked against the port, not the PID file.
    if _port_in_use(port):
        pid = None
        if server_json.exists():
            try:
                pid = json.loads(server_json.read_text(encoding="utf-8")).get("pid")
            except Exception:
                pass
        who = f"PID {pid}" if pid and _is_process_alive(pid) else "an unknown process"
        print(f"clean-rag server already running on port {port} ({who}). Not starting a second one.")
        # Still open the UI. Asking to start a server that is already up is
        # usually someone wanting to see it, and the console is the only way to
        # watch indexing. A closed console is not a reason to be left blind.
        _launch_console()
        return

    clean_rag_home = str(_CLEAN_RAG_HOME)
    server_script = str(_CLEAN_RAG_HOME / "server" / "__main__.py")

    env = os.environ.copy()
    env["CLEAN_RAG_HOME"] = clean_rag_home

    # Windowless by default. This reverses the earlier "headed by default"
    # decision, and the reason that decision gave has been met another way:
    # its point was that logs should be visible while they happen rather than
    # reconstructed from state/server.log afterwards. cli/console.py now shows
    # exactly those logs live, because app.py attaches a RotatingFileHandler to
    # state/server.log independently of where stdout goes. So the server's own
    # window duplicated the console and cost a second terminal.
    #
    # The other half of the old tradeoff goes away with it: a headed server
    # died when its window was closed, which is how it died on 2026-09-18.
    #
    # Set CLEAN_RAG_HEADED=1 for the raw terminal. Positive name on purpose:
    # every other flag here (CLEAN_RAG_WEB_SEARCH, CLEAN_RAG_SECURITY_SCAN,
    # CLEAN_RAG_PATTERN_INJECT) names the behaviour being asked for, and
    # CLEAN_RAG_HEADLESS was the one that named a suppressed state instead.
    headed = os.environ.get("CLEAN_RAG_HEADED") == "1"

    if sys.platform == "win32":
        if headed:
            proc = subprocess.Popen(
                [_server_python(), server_script],
                cwd=clean_rag_home,
                env=env,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NEW_CONSOLE,
            )
        else:
            # DETACHED_PROCESS, not CREATE_NO_WINDOW. Microsoft's process
            # creation flags doc: CREATE_NO_WINDOW "is ignored ... if it is
            # used with either CREATE_NEW_CONSOLE or DETACHED_PROCESS", and on
            # its own it only hides the window of a process still tied to the
            # parent's console. DETACHED_PROCESS is what lets the server
            # outlive whatever launched it. CREATE_NEW_PROCESS_GROUP on top is
            # meaningful here, it keeps console Ctrl+C from reaching the
            # server; in the headed branch above the same flag is a documented
            # no-op, left alone because it already was one.
            proc = subprocess.Popen(
                [_server_python(), server_script],
                cwd=clean_rag_home,
                env=env,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    else:
        proc = subprocess.Popen(
            [_server_python(), server_script],
            cwd=clean_rag_home,
            env=env,
            start_new_session=True,
            stdout=None if headed else subprocess.DEVNULL,
            stderr=None if headed else subprocess.DEVNULL,
        )

    # Write PID file
    server_json.write_text(json.dumps({
        "pid": proc.pid,
        "port": port,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "clean_rag_home": clean_rag_home,
    }, indent=2), encoding="utf-8")

    print(f"clean-rag server started (PID {proc.pid}, port {port})")

    # Before the /status wait below, not after, so the UI is already up while
    # the embedding model loads. That load takes about 55 seconds measured, and
    # it is the exact window where a user with no console assumes the server
    # failed, because the health check times out and nothing else says anything.
    _launch_console()

    # Wait a moment and verify it's running
    time.sleep(2)
    try:
        import httpx
        resp = httpx.get(f"http://127.0.0.1:{port}/status", timeout=5)
        if resp.status_code == 200:
            print("Server is ready.")
        else:
            print("Server started but /status returned non-200. Check logs.")
    except Exception:
        print("Server process started. Model loading may take 30-60 seconds.")


#: Written by `stop`, cleared by `start`, read by hooks/rag-enforce.py. An
#: explicit stop has to outlast the next prompt, otherwise the health check
#: sees the server down, restarts it, and the user cannot get their machine
#: back without also disabling the hook.
STOP_MARKER_NAME = "server-stopped-by-user"


def _load_write_durably():
    """Resolve ``server.durable_write.write_durably``, or None if unavailable.

    Same guard, and the same "return None rather than raise", as
    hooks/rag-enforce.py's own _load_write_durably(). The two share one contract
    about this marker, so they have to fail the same way about it. A half
    installed or partially copied clean-rag is exactly when someone reaches for
    stop, and an ImportError escaping from the middle of it loses both the
    explanation and the non zero exit that tells a script the stop did not take.
    """
    _root = str(_CLEAN_RAG_HOME)
    if _root not in sys.path:
        sys.path.insert(0, _root)
    try:
        from server.durable_write import write_durably
    except ImportError as e:
        print(
            f"ERROR: cannot import server.durable_write from {_root}: {e}",
            file=sys.stderr,
        )
        return None
    return write_durably


def _report_unrecorded_stop(marker: Path, cause: object) -> None:
    """Explain that the stop did not persist, and how to make it stick anyway."""
    print(f"ERROR: could not record the stop at {marker}: {cause}", file=sys.stderr)
    print(
        "The next prompt will see the server down, find no marker, and restart "
        f"it. Create {marker.name} in {marker.parent} by hand to keep the "
        "server down, then fix the cause above and run stop again.",
        file=sys.stderr,
    )


def _mark_stopped_by_user(state: Path) -> bool:
    """Record that the user wants the server to stay down. True if it persisted.

    Read back after writing. Durability is the entire value of this file: it
    exists so the next prompt's health check can tell "the user killed it" from
    "it died". A write that reports success but leaves nothing readable (full
    disk, a read only mount, an antivirus quarantine) is the case that gets the
    server resurrected, so the write is not trusted on its own. The read back
    lives in server.durable_write so hooks/rag-enforce.py's cooldown stamp gets
    the identical check instead of a second copy that drifts.
    """
    marker = state / STOP_MARKER_NAME
    body = f"stopped at {time.strftime('%Y-%m-%d %H:%M:%S')}\n"

    write_durably = _load_write_durably()
    if write_durably is None:
        _report_unrecorded_stop(marker, "server.durable_write is not importable")
        return False

    try:
        write_durably(marker, body)
    except OSError as e:
        _report_unrecorded_stop(marker, e)
        return False
    return True


def _clear_stopped_by_user(state: Path) -> None:
    try:
        (state / STOP_MARKER_NAME).unlink()
    except FileNotFoundError:
        pass
    except OSError as e:
        print(f"Warning: could not clear stop marker: {e}")


def _terminate_from_pid_file(server_json: Path) -> None:
    """Kill whatever the PID file names, then retire the PID file."""
    try:
        info = json.loads(server_json.read_text(encoding="utf-8"))
        pid = info.get("pid")
        if pid:
            if _is_process_alive(pid):
                os.kill(pid, signal.SIGTERM)
                print(f"Sent SIGTERM to PID {pid}")
                if sys.platform != "win32":
                    # On POSIX, SIGTERM is graceful. Wait then force kill.
                    for _ in range(10):
                        time.sleep(0.5)
                        if not _is_process_alive(pid):
                            break
                    if _is_process_alive(pid):
                        os.kill(pid, signal.SIGKILL)
                        print(f"Sent SIGKILL to PID {pid}")
                # On Windows, os.kill(SIGTERM) calls TerminateProcess (immediate)
            else:
                print(f"PID {pid} not running (stale PID file)")
    except Exception as e:
        print(f"Error stopping server: {e}")

    try:
        server_json.unlink()
    except OSError as e:
        print(f"Warning: could not remove {server_json.name}: {e}")


def cmd_stop(args) -> int:
    """Stop the server. Returns 0, or 1 if the stop did not durably persist.

    Non zero matters because the marker is the whole contract with the hook: a
    stop that was not recorded gets undone by the next prompt, and a script (or
    a person) has no other way to find that out.
    """
    state = _state_dir()
    server_json = state / "server.json"
    had_pid_file = server_json.exists()

    if had_pid_file:
        _terminate_from_pid_file(server_json)

    # Recording the intent is not conditional on there having been a PID file.
    # It goes missing routinely (a server started by hand, or one that died
    # badly), and "stop" meaning nothing in exactly those cases is how a killed
    # server comes back on the next prompt.
    if not _mark_stopped_by_user(state):
        print(
            "The server is down but the stop was NOT recorded. Self heal will "
            "bring it back on the next prompt.",
            file=sys.stderr,
        )
        return 1

    print("Server stopped." if had_pid_file else "No server PID file found. Marked as stopped.")
    return 0


def cmd_restart(args) -> int:
    """Stop then start.

    This existed as a caller before it existed as a command: rag-enforce.py
    used to shell out to "server_ctl.py restart" to restart the server behind
    the user's back, and argparse just printed help and exited 0, so it had
    never once worked. That automatic restart is gone; restart is now only ever
    run by hand.

    cmd_stop's exit code is deliberately not propagated: a restart clears the
    stop marker two lines later anyway, so failing to write it changes nothing
    here. Only a failure to come back up is a failed restart.
    """
    cmd_stop(args)
    time.sleep(2)
    return cmd_start(args) or 0


def cmd_status(args):
    port = _port()
    try:
        import httpx
        resp = httpx.get(f"http://127.0.0.1:{port}/status", timeout=5)
        data = resp.json()
        print(f"Status: {data.get('status', 'unknown')}")
        print(f"Uptime: {data.get('uptime_s', 0):.0f}s")
        print(f"Code embedding: {data.get('code_embedding_model', '?')} "
              f"(loaded: {data.get('code_embedding_loaded', False)})")
        projects = data.get("projects", {})
        print(f"Projects: {projects.get('count', 0)}")
    except Exception:
        print(f"Server not responding on port {port}")

        # Check PID file
        state = _state_dir()
        server_json = state / "server.json"
        if server_json.exists():
            try:
                info = json.loads(server_json.read_text(encoding="utf-8"))
                pid = info.get("pid")
                if pid and _is_process_alive(pid):
                    print(f"  Process {pid} is running but not responding yet (model loading?)")
                else:
                    print(f"  PID {pid} is not running. Start with: python clean-rag/cli/server_ctl.py start")
            except Exception:
                pass
        else:
            print("  No PID file. Start with: python clean-rag/cli/server_ctl.py start")


def _is_process_alive(pid: int) -> bool:
    """Is *pid* a running process?

    Defaults to True on anything ambiguous. A live server misreported as dead
    is the expensive direction: `stop` prints "stale PID file", skips the kill,
    and leaves a server running that the user believes they stopped, which is
    exactly what happened here to PID 33964 while it was still LISTENING on
    8613.

    The old version was `os.kill(pid, 0)` under `except OSError`. The signal
    itself is harmless on Windows (verified, it does not terminate), but
    PermissionError subclasses OSError, and CPython's os.kill opens the process
    with PROCESS_ALL_ACCESS, which a process in another console or at a
    different elevation can refuse. Access denied then read as "not running".
    Access denied in fact proves the opposite: only a live process can deny it.
    """
    if pid is None or pid <= 0:
        return False

    try:
        import psutil
    except ImportError:
        try:
            os.kill(pid, 0)
            return True
        except PermissionError:
            return True  # it exists, we just cannot touch it
        except (ProcessLookupError, OSError):
            return False

    try:
        proc = psutil.Process(pid)
        # A zombie has a PID and is not running, so pid_exists alone is not
        # enough on POSIX.
        return proc.status() != psutil.STATUS_DEAD
    except psutil.NoSuchProcess:
        return False
    except psutil.AccessDenied:
        return True
    except Exception:
        return True  # unknown state, assume alive rather than skip the kill


def main() -> int:
    parser = argparse.ArgumentParser(description="clean-rag server control")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser(
        "start",
        help="Start the server with no window (CLEAN_RAG_HEADED=1 for a console)",
    )
    sub.add_parser("stop", help="Stop the server")
    sub.add_parser("restart", help="Stop then start")
    sub.add_parser("status", help="Check server status")

    args = parser.parse_args()
    handlers = {
        "start": cmd_start,
        "stop": cmd_stop,
        "restart": cmd_restart,
        "status": cmd_status,
    }
    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        return 2
    # Commands that cannot fail meaningfully return None, which is 0.
    return handler(args) or 0


if __name__ == "__main__":
    sys.exit(main())
