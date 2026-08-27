"""Start memory-watcher.py detached, once per machine, then get out of the way.

A SessionStart hook cannot simply run memory-watcher.py: that script samples
forever, so the hook would either hang the session start or be killed by its
own timeout. This launches it as a detached process and returns immediately.

The "once per machine" half matters more than it looks. A SessionStart hook
fires for every Claude session, and a machine routinely has several open at
once. Six sessions starting six samplers, all appending to one file on the same
interval, would turn the thing that measures the memory problem into part of
it. memory-watcher.already_running() is the real guard; this checks it too so
the common case costs no process spawn at all.

Never blocks and never fails a session start: any problem here is reported on
stderr and exits 0. A memory sampler is diagnostics, and diagnostics that can
stop you working are worse than no diagnostics.
"""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WATCHER = HERE / "memory-watcher.py"
LOG = HERE.parent / "state" / "memory-watcher.out"


def _load_watcher():
    """Import memory-watcher.py, whose hyphen keeps it off the import path."""
    spec = importlib.util.spec_from_file_location("_memory_watcher", WATCHER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    if not WATCHER.is_file():
        print(f"memory-watcher-start: {WATCHER.name} not on this branch, skipping",
              file=sys.stderr)
        return 0

    try:
        watcher = _load_watcher()
    except Exception as e:
        # psutil missing is the expected case here, and it is not worth a word
        # at session start beyond one line.
        print(f"memory-watcher-start: cannot load watcher: {type(e).__name__}: {e}",
              file=sys.stderr)
        return 0

    try:
        running = watcher.already_running()
    except Exception as e:
        print(f"memory-watcher-start: running check failed: {type(e).__name__}: {e}",
              file=sys.stderr)
        return 0

    if running is not None:
        return 0

    LOG.parent.mkdir(parents=True, exist_ok=True)

    # Detach properly, or the sampler dies with the session that started it,
    # which defeats the point of watching across a crash.
    kwargs: dict = {"close_fds": True}
    if os.name == "nt":
        kwargs["creationflags"] = (
            subprocess.CREATE_NO_WINDOW
            | subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        kwargs["start_new_session"] = True

    try:
        with LOG.open("a", encoding="utf-8") as out:
            proc = subprocess.Popen(
                [sys.executable, str(WATCHER)],
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=out,
                **kwargs,
            )
        print(f"memory-watcher-start: started pid {proc.pid}", file=sys.stderr)
    except Exception as e:
        print(f"memory-watcher-start: launch failed: {type(e).__name__}: {e}",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
