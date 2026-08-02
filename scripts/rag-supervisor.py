#!/usr/bin/env python3
"""rag-supervisor.py — Process supervisor for RAG servers.

Manages both the main RAG server (port 8612) and clean-rag server (port 8613)
as child processes. Restarts them on crash with exponential backoff.

Usage:
    python rag-supervisor.py start           # start supervisor + both servers
    python rag-supervisor.py start --only rag      # only main RAG server
    python rag-supervisor.py start --only clean-rag  # only clean-rag server
    python rag-supervisor.py stop            # stop supervisor + all children
    python rag-supervisor.py status          # show supervisor and child status

The supervisor itself runs as a detached background process. It writes
.supervisor.json with PIDs, restart counts, and uptime so other scripts
can check health without HTTP calls.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

BOOST_HOME = Path(os.environ.get("CLAUDEBOOST_HOME", Path(__file__).resolve().parent.parent))
LOCAL_APPDATA = os.environ.get("LOCALAPPDATA", "")
RAG_INDEX_DIR = Path(os.environ.get(
    "RAG_INDEX_DIR",
    str(Path(LOCAL_APPDATA) / "rag-server-index") if LOCAL_APPDATA else str(BOOST_HOME / "mcp-rag-server" / ".rag-index"),
))

SUPERVISOR_JSON = RAG_INDEX_DIR / ".supervisor.json"
SUPERVISOR_LOG = RAG_INDEX_DIR / "supervisor.log"
SUPERVISOR_PID = RAG_INDEX_DIR / ".supervisor.pid"

# Backoff config
INITIAL_BACKOFF_S = 1.0
MAX_BACKOFF_S = 30.0
STABLE_THRESHOLD_S = 60.0  # reset backoff after this many seconds of stable running

logger = logging.getLogger("rag-supervisor")


class ManagedServer:
    """A child server process with auto restart and exponential backoff."""

    def __init__(self, name: str, cmd: list[str], env: dict, cwd: str, port: int):
        self.name = name
        self.cmd = cmd
        self.env = env
        self.cwd = cwd
        self.port = port
        self.proc: subprocess.Popen | None = None
        self.pid: int = 0
        self.restart_count: int = 0
        self.backoff_s: float = INITIAL_BACKOFF_S
        self.last_start: float = 0.0
        self.started_at: float = 0.0
        self.stopped = False
        self._lock = threading.Lock()

    def start(self) -> None:
        """Launch the child process."""
        with self._lock:
            if self.proc and self.proc.poll() is None:
                logger.info("[%s] already running (pid=%d)", self.name, self.proc.pid)
                return
            self._launch()

    def _launch(self) -> None:
        """Internal: spawn the child process."""
        log_path = RAG_INDEX_DIR / f"{self.name}.log"
        RAG_INDEX_DIR.mkdir(parents=True, exist_ok=True)
        log_file = open(log_path, "a", encoding="utf-8")

        kwargs: dict = {
            "cwd": self.cwd,
            "env": self.env,
            "stdin": subprocess.DEVNULL,
            "stdout": log_file,
            "stderr": log_file,
        }
        # On Windows, don't use DETACHED_PROCESS for children; the supervisor
        # itself is already detached and needs to monitor child exit via wait().
        # CREATE_NO_WINDOW prevents console popups.
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        try:
            self.proc = subprocess.Popen(self.cmd, **kwargs)
            self.pid = self.proc.pid
            self.last_start = time.monotonic()
            if self.started_at == 0.0:
                self.started_at = time.time()
            logger.info(
                "[%s] started (pid=%d, port=%d, restart_count=%d)",
                self.name, self.pid, self.port, self.restart_count,
            )
        except Exception:
            logger.exception("[%s] failed to start", self.name)
            self.proc = None
            self.pid = 0

    def stop(self) -> None:
        """Stop the child process."""
        with self._lock:
            self.stopped = True
            if self.proc and self.proc.poll() is None:
                logger.info("[%s] stopping (pid=%d)", self.name, self.pid)
                try:
                    self.proc.terminate()
                    try:
                        self.proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.proc.kill()
                        self.proc.wait(timeout=3)
                except Exception:
                    logger.exception("[%s] error stopping process", self.name)

    def monitor_loop(self) -> None:
        """Block forever, restarting the child on crash. Run in a thread."""
        while not self.stopped:
            if self.proc is None:
                with self._lock:
                    if not self.stopped:
                        self._launch()
                if self.proc is None:
                    time.sleep(self.backoff_s)
                    continue

            # Wait for child to exit
            try:
                exit_code = self.proc.wait()
            except Exception:
                exit_code = -1

            if self.stopped:
                break

            uptime = time.monotonic() - self.last_start

            # Ran long enough to be stable? Reset backoff for quick restart.
            if uptime >= STABLE_THRESHOLD_S:
                self.backoff_s = INITIAL_BACKOFF_S
                logger.info(
                    "[%s] crashed after %.0fs stable running (exit=%s). Restarting immediately.",
                    self.name, uptime, exit_code,
                )
            else:
                logger.warning(
                    "[%s] exited after %.1fs (exit=%s). Waiting %.1fs before restart.",
                    self.name, uptime, exit_code, self.backoff_s,
                )
                time.sleep(self.backoff_s)
                self.backoff_s = min(self.backoff_s * 2, MAX_BACKOFF_S)

            self.restart_count += 1
            with self._lock:
                self.proc = None
                self.pid = 0

    def status_dict(self) -> dict:
        alive = self.proc is not None and self.proc.poll() is None
        return {
            "name": self.name,
            "pid": self.pid if alive else 0,
            "port": self.port,
            "alive": alive,
            "restart_count": self.restart_count,
            "backoff_s": self.backoff_s,
            "started_at": self.started_at,
        }


def _build_rag_server(port: int = 8612) -> ManagedServer:
    """Build the main RAG server (Starlette/uvicorn) managed process."""
    python = sys.executable
    src_dir = BOOST_HOME / "mcp-rag-server" / "src"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(src_dir)
    env.pop("DISABLE_TELEMETRY", None)
    env["TQDM_DISABLE"] = "1"
    env["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    env["TOKENIZERS_PARALLELISM"] = "false"
    env["TRANSFORMERS_VERBOSITY"] = "error"
    env.setdefault("OMP_NUM_THREADS", "1")
    env.setdefault("MKL_NUM_THREADS", "1")
    env.setdefault("OPENBLAS_NUM_THREADS", "1")

    cmd = [python, "-m", "rag_server", "--http", "--port", str(port)]
    return ManagedServer(
        name="rag-server",
        cmd=cmd,
        env=env,
        cwd=str(src_dir),
        port=port,
    )


def _build_clean_rag_server(port: int = 8613) -> ManagedServer:
    """Build the clean-rag server (aiohttp) managed process."""
    python = sys.executable
    clean_rag_home = BOOST_HOME / "clean-rag"
    server_script = str(clean_rag_home / "server" / "__main__.py")
    env = os.environ.copy()
    env["CLEAN_RAG_HOME"] = str(clean_rag_home)
    env["TQDM_DISABLE"] = "1"
    env["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
    env["TOKENIZERS_PARALLELISM"] = "false"
    env.setdefault("OMP_NUM_THREADS", "1")
    env.setdefault("MKL_NUM_THREADS", "1")

    cmd = [python, server_script]
    return ManagedServer(
        name="clean-rag",
        cmd=cmd,
        env=env,
        cwd=str(clean_rag_home),
        port=port,
    )


def _write_supervisor_state(servers: list[ManagedServer]) -> None:
    """Write .supervisor.json with current state of all managed servers."""
    state = {
        "supervisor_pid": os.getpid(),
        "updated_at": time.time(),
        "servers": [s.status_dict() for s in servers],
    }
    try:
        SUPERVISOR_JSON.parent.mkdir(parents=True, exist_ok=True)
        SUPERVISOR_JSON.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        logger.debug("Failed to write supervisor state", exc_info=True)


def _state_writer_loop(servers: list[ManagedServer], interval: float = 10.0) -> None:
    """Periodically write supervisor state to disk. Run in a daemon thread."""
    while True:
        _write_supervisor_state(servers)
        time.sleep(interval)


def _read_supervisor_state() -> dict | None:
    if not SUPERVISOR_JSON.exists():
        return None
    try:
        return json.loads(SUPERVISOR_JSON.read_text(encoding="utf-8"))
    except Exception:
        return None


sys.path.insert(0, str(Path(__file__).resolve().parent))
from proc_utils import is_pid_alive as _is_pid_alive  # noqa: E402
from proc_utils import port_in_use as _port_in_use  # noqa: E402


def cmd_start(args) -> int:
    """Start the supervisor and managed servers."""
    only = getattr(args, "only", None)

    # Port check FIRST, before trusting any recorded PID.
    #
    # This is the guard that actually stops duplicates. session-primer.py runs
    # rag-server-start.py whenever the server looks down, which lands here, so
    # every session and every agent spawn is a chance to start another
    # supervisor. Each supervisor launches its own managed servers and each of
    # those loads its own embedding model at 1 to 2 GB. Nine rag_server
    # processes totalling ~3 GB were observed from exactly this, because the
    # only guard was a PID check that failed toward "not running" under load.
    wanted = []
    if only in (None, "rag"):
        wanted.append(("rag", 8612))
    if only in (None, "clean-rag"):
        wanted.append(("clean-rag", 8613))

    already = [(name, port) for name, port in wanted if _port_in_use(port)]
    if already and len(already) == len(wanted):
        for name, port in already:
            print(f"{name} already serving on port {port}. Not starting a second one.")
        return 0

    state = _read_supervisor_state()
    if state:
        sup_pid = state.get("supervisor_pid", 0)
        if _is_pid_alive(sup_pid):
            print(f"Supervisor already running (pid={sup_pid})")
            for s in state.get("servers", []):
                status = "alive" if s.get("alive") else "dead"
                print(f"  {s['name']}: pid={s.get('pid', 0)} port={s['port']} {status} restarts={s.get('restart_count', 0)}")
            return 0

    # Launch the supervisor itself as a detached background process
    python = sys.executable
    env = os.environ.copy()
    supervisor_cmd = [python, __file__, "_run"]
    if only:
        supervisor_cmd.extend(["--only", only])

    RAG_INDEX_DIR.mkdir(parents=True, exist_ok=True)
    log_file = open(SUPERVISOR_LOG, "a", encoding="utf-8")

    kwargs: dict = {
        "env": env,
        "stdin": subprocess.DEVNULL,
        "stdout": log_file,
        "stderr": log_file,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS

    proc = subprocess.Popen(supervisor_cmd, **kwargs)

    try:
        SUPERVISOR_PID.write_text(str(proc.pid), encoding="utf-8")
    except Exception:
        pass

    print(f"Supervisor started (pid={proc.pid})")

    # Wait for servers to come up
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        time.sleep(2)
        state = _read_supervisor_state()
        if state:
            servers = state.get("servers", [])
            all_alive = all(s.get("alive") for s in servers)
            if servers and all_alive:
                for s in servers:
                    print(f"  {s['name']}: pid={s.get('pid', 0)} port={s['port']} alive")
                return 0
        print(".", end="", flush=True)

    print("\nSupervisor started but servers may still be loading. Check: python rag-supervisor.py status")
    return 0


def cmd_stop(args) -> int:
    """Stop the supervisor and all managed servers."""
    state = _read_supervisor_state()
    sup_pid = 0

    if state:
        sup_pid = state.get("supervisor_pid", 0)
    if not sup_pid and SUPERVISOR_PID.exists():
        try:
            sup_pid = int(SUPERVISOR_PID.read_text(encoding="utf-8").strip())
        except Exception:
            pass

    if not sup_pid or not _is_pid_alive(sup_pid):
        print("Supervisor not running.")
        for f in [SUPERVISOR_JSON, SUPERVISOR_PID]:
            try:
                f.unlink(missing_ok=True)
            except Exception:
                pass
        return 0

    print(f"Stopping supervisor (pid={sup_pid})...")

    try:
        if sys.platform == "win32":
            # taskkill /T kills the entire process tree
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(sup_pid)],
                capture_output=True, timeout=10,
            )
        else:
            os.kill(sup_pid, signal.SIGTERM)
            for _ in range(20):
                time.sleep(0.5)
                if not _is_pid_alive(sup_pid):
                    break
            if _is_pid_alive(sup_pid):
                os.kill(sup_pid, signal.SIGKILL)
    except Exception as e:
        print(f"Error stopping supervisor: {e}")

    # Clean up any child processes still alive
    if state:
        for s in state.get("servers", []):
            child_pid = s.get("pid", 0)
            if child_pid and _is_pid_alive(child_pid):
                try:
                    if sys.platform == "win32":
                        subprocess.run(
                            ["taskkill", "/F", "/PID", str(child_pid)],
                            capture_output=True, timeout=5,
                        )
                    else:
                        os.kill(child_pid, signal.SIGTERM)
                except Exception:
                    pass

    for f in [SUPERVISOR_JSON, SUPERVISOR_PID]:
        try:
            f.unlink(missing_ok=True)
        except Exception:
            pass

    print("Supervisor stopped.")
    return 0


def cmd_status(args) -> int:
    """Show supervisor and server status."""
    state = _read_supervisor_state()
    if not state:
        print("Supervisor not running (no state file).")
        return 1

    sup_pid = state.get("supervisor_pid", 0)
    alive = _is_pid_alive(sup_pid)
    updated = state.get("updated_at", 0)
    age_s = time.time() - updated if updated else 0

    if not alive:
        print(f"Supervisor not running (pid={sup_pid} is dead, state is {age_s:.0f}s old).")
        return 1

    print(f"Supervisor: pid={sup_pid} (state updated {age_s:.0f}s ago)")
    for s in state.get("servers", []):
        status = "alive" if s.get("alive") else "DEAD"
        restarts = s.get("restart_count", 0)
        backoff = s.get("backoff_s", 0)
        started = s.get("started_at", 0)
        uptime = time.time() - started if started else 0
        line = f"  {s['name']}: pid={s.get('pid', 0)} port={s['port']} {status} restarts={restarts}"
        if uptime > 0:
            line += f" uptime={uptime:.0f}s"
        if restarts > 0:
            line += f" backoff={backoff:.1f}s"
        print(line)
    return 0


def cmd_run(args) -> None:
    """Internal: run the supervisor in foreground (called by cmd_start detached)."""
    RAG_INDEX_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.FileHandler(SUPERVISOR_LOG, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

    logger.info("Supervisor starting (pid=%d)", os.getpid())

    only = getattr(args, "only", None)
    servers: list[ManagedServer] = []

    if only != "clean-rag":
        servers.append(_build_rag_server())
    if only != "rag":
        servers.append(_build_clean_rag_server())

    if not servers:
        logger.error("No servers to manage. Exiting.")
        return

    try:
        SUPERVISOR_PID.write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        pass

    for s in servers:
        s.start()

    _write_supervisor_state(servers)

    # State writer thread: updates .supervisor.json every 10s
    state_thread = threading.Thread(
        target=_state_writer_loop,
        args=(servers,),
        daemon=True,
        name="state-writer",
    )
    state_thread.start()

    # Monitor threads: one per server, restarts on crash
    for s in servers:
        t = threading.Thread(
            target=s.monitor_loop,
            daemon=True,
            name=f"monitor-{s.name}",
        )
        t.start()

    # Handle shutdown signals
    shutdown_event = threading.Event()

    def _shutdown_handler(signum, frame):
        logger.info("Supervisor received signal %s, shutting down...", signum)
        for s in servers:
            s.stop()
        shutdown_event.set()

    signal.signal(signal.SIGTERM, _shutdown_handler)
    signal.signal(signal.SIGINT, _shutdown_handler)
    if sys.platform == "win32":
        try:
            signal.signal(signal.SIGBREAK, _shutdown_handler)
        except (AttributeError, ValueError):
            pass

    try:
        shutdown_event.wait()
    except KeyboardInterrupt:
        logger.info("Supervisor interrupted, shutting down...")
        for s in servers:
            s.stop()

    _write_supervisor_state(servers)
    logger.info("Supervisor exited.")

    try:
        SUPERVISOR_PID.unlink(missing_ok=True)
    except Exception:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="RAG server supervisor")
    sub = parser.add_subparsers(dest="command")

    start_p = sub.add_parser("start", help="Start supervisor and servers")
    start_p.add_argument("--only", choices=["rag", "clean-rag"], help="Only manage one server")

    sub.add_parser("stop", help="Stop supervisor and all servers")
    sub.add_parser("status", help="Show supervisor status")

    run_p = sub.add_parser("_run", help=argparse.SUPPRESS)
    run_p.add_argument("--only", choices=["rag", "clean-rag"])

    args = parser.parse_args()

    if args.command == "start":
        return cmd_start(args)
    elif args.command == "stop":
        return cmd_stop(args)
    elif args.command == "status":
        return cmd_status(args)
    elif args.command == "_run":
        cmd_run(args)
        return 0
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
