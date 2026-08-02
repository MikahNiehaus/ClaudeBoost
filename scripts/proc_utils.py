"""Process and port probes shared by the ClaudeBoost scripts.

One definition each, because there were four copies of "is this pid alive" in
this repo and they had already drifted: two were fixed to use psutil while
`rag-server-start.py` still carried the original `tasklist` substring bug, so
the same false answer was live in one launcher and fixed in another.

Deliberately NOT shared with `clean-rag/`. That tree is installable on its own
(see clean-rag/PORTABLE_SETUP.md), so it keeps its own copy rather than growing
an import back into ClaudeBoost.

Both probes default to "yes, it exists" when they cannot tell. Every caller
here is a single instance guard, and the two wrong answers are not equally
priced: a spurious "already running" is something a human can override in
seconds, while a false "nothing running" starts a duplicate server that loads
its own 1 to 2 GB embedding model. Nine of those were observed at once.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys


def is_pid_alive(pid: int) -> bool:
    """Is *pid* a running process? True when unsure."""
    if not pid or pid <= 0:
        return False

    try:
        import psutil
    except ImportError:
        psutil = None

    if psutil is not None:
        try:
            return psutil.Process(pid).status() != psutil.STATUS_DEAD
        except psutil.NoSuchProcess:
            return False
        except psutil.AccessDenied:
            return True  # only a live process can deny access
        except Exception:
            return True

    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["tasklist", "/fi", f"PID eq {pid}", "/fo", "csv", "/nh"],
                capture_output=True, text=True, timeout=15,
            )
        except Exception:
            # Could not tell, including a timeout. Timeouts happen precisely
            # when the machine is overloaded, which is when spawning another
            # server is worst, so this must not answer "dead".
            return True
        # Compare the PID field, not the whole row: `str(pid) in stdout`
        # matched 12345 for pid 1234, and matched any column containing those
        # digits.
        for line in result.stdout.splitlines():
            fields = [f.strip().strip('"') for f in line.split('","')]
            if len(fields) >= 2 and fields[1] == str(pid):
                return True
        return False

    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except ProcessLookupError:
        return False
    except OSError:
        return True


def port_in_use(port: int, host: str = "127.0.0.1", timeout: float = 0.5) -> bool:
    """Is something already listening on *port*?

    Tests for a listener with ``connect_ex`` rather than trying to ``bind``.
    They answer different questions: bind failing also covers permissions and
    address reuse rules, which are not "a server is already up".

    The authority on single instance, because unlike a PID file it cannot go
    stale: a PID file survives a process that died badly and knows nothing
    about a server someone started by hand.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            return sock.connect_ex((host, port)) == 0
    except OSError:
        return False
