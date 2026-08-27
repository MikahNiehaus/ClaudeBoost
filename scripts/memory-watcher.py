"""Log system and per process memory every 30s so the next spike names a culprit.

Written because a machine with 64 GB reached 1 MB free and nothing recorded what
consumed it. clean-rag's own headroom guard SAW the exhaustion
(`Waiting 5s for headroom: free RAM 1 MB`) but only logs the number, not who
took it, and Windows logged no Resource-Exhaustion-Detector 2004 event either,
so there is no record naming a process.

Appends one JSON object per sample to state/memory-watch.jsonl. Append only and
one line per sample on purpose: the machine is hard resetting, so a buffered or
rewritten file loses exactly the sample that matters. Flushed and fsynced every
write for the same reason.

Run it detached and leave it running:
    python scripts/memory-watcher.py

ponytail: fixed 30s interval and top 15 processes. Fine for catching a spike
that builds over minutes, which is what the logs show. If a spike turns out to
be sub second, sample faster.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import psutil
except ImportError:
    print("psutil is required: pip install psutil", file=sys.stderr)
    raise SystemExit(1)

INTERVAL_S = 30
TOP_N = 15

# Below this much free RAM, sample every second instead. The interesting window
# is the approach to zero, and 30s steps through it tell you almost nothing.
PRESSURE_MB = 8192
PRESSURE_INTERVAL_S = 1

OUT = Path(__file__).resolve().parents[1] / "state" / "memory-watch.jsonl"

# Only processes at least this large get identified beyond their name. A name
# alone was not enough: one process reached 27 GB and all this file recorded was
# "python.exe", which names nothing on a machine running several.
IDENTIFY_ABOVE_MB = 5120

#: Interpreters, where the executable name says nothing and the script does.
#: "python.exe" is every python process on the box; the script path is the one
#: that ballooned. Anything not on this list is identified by its own name, so
#: no argument of it is ever read.
_INTERPRETERS = {
    "python", "python3", "pythonw", "py",
    "node", "deno", "bun",
    "java", "ruby", "perl", "php",
    "pwsh", "powershell",
}

#: A token is only taken as the script if it ends in one of these. See
#: _script_of for why shape matters more than position here.
_SCRIPT_SUFFIXES = {
    ".py", ".pyw", ".js", ".mjs", ".cjs", ".ts",
    ".rb", ".pl", ".php", ".jar", ".ps1",
}


def _script_of(proc) -> str | None:
    """The script an interpreter is running, or None.

    Deliberately reads ONE token and never an argument value. Command line
    arguments routinely carry secrets (CWE-214, and argv is readable by other
    processes anyway), and this file persists indefinitely, so capturing argv
    would put a plaintext copy of every secret ever passed on this machine
    outside the OS's own access controlled process table. The first positional
    token is a path or a module name, which is what identifies the process, and
    the rest is dropped unread rather than redacted. Nothing to get wrong.

    Restricted to interpreters for the same reason: for `curl`, the first
    positional token is a URL and a URL can carry credentials. For `python` it
    is a script path. The executable name already identifies a non interpreter.

    cmdline() is why this is gated on size at all. On Windows it reads the
    target's PEB through ReadProcessMemory, far heavier than name(), and it is
    privilege dependent (psutil #799, #2366). Calling it on every process every
    30 seconds would make the watcher part of the problem it measures.
    """
    try:
        argv = proc.cmdline()
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return None
    if not argv:
        return None

    stem = Path(argv[0]).stem.lower()
    if stem not in _INTERPRETERS:
        return None

    # Allowlist by shape, rather than "the first token that is not a flag".
    # That rule leaked: in `python --api-key SECRET run.py` the flag is skipped
    # and SECRET is not itself a flag, so it was returned as the script. A test
    # caught it. Requiring a script suffix means a bare secret cannot be
    # mistaken for a path, because it does not end in one.
    for token in argv[1:]:
        if token.startswith("-"):
            continue
        if Path(token).suffix.lower() in _SCRIPT_SUFFIXES:
            return token[:260]  # MAX_PATH; longer is not a script path
    # Nothing script shaped. `python -m pytest` lands here, and so does anything
    # whose arguments are all values. Returning None is right: an unidentified
    # process is a smaller problem than a logged secret.
    return None


def sample() -> dict:
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()

    procs = []
    # Cheap attributes for everyone, the way psutil's own procs_by_memory recipe
    # does it: filter on rss first, then pay for anything expensive.
    for p in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            mi = p.info["memory_info"]
            if mi is None:
                continue
            procs.append((mi.rss, p.info["pid"], p.info["name"], p))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    procs.sort(key=lambda r: r[0], reverse=True)

    top = []
    for rss, pid, name, proc in procs[:TOP_N]:
        entry = {"pid": pid, "name": name, "rss_mb": round(rss / 1048576, 1)}
        if rss / 1048576 >= IDENTIFY_ABOVE_MB:
            script = _script_of(proc)
            if script:
                entry["script"] = script
        top.append(entry)

    return {
        "t": datetime.now(timezone.utc).isoformat(),
        "free_mb": round(vm.available / 1048576, 1),
        "used_pct": vm.percent,
        "total_mb": round(vm.total / 1048576, 1),
        # Commit is the number that actually matters on Windows: a process can
        # reserve far more than its RSS, and it is the commit limit, not RSS,
        # that a failed kernel allocation runs into.
        "swap_used_mb": round(sw.used / 1048576, 1),
        "swap_total_mb": round(sw.total / 1048576, 1),
        "top": top,
    }


def already_running() -> int | None:
    """PID of another live watcher on this same script, or None.

    This runs from a SessionStart hook, and a machine routinely has several
    Claude sessions open at once (six, on the machine this was written for).
    Without this check each session starts its own watcher, every one of them
    sampling on the same interval and appending to the same file. That is six
    times the CPU and an interleaved log, which makes the watcher part of the
    memory problem it exists to measure.

    Matched on the resolved script path rather than a PID file: a PID file goes
    stale when a watcher is killed and says nothing about one started by hand.
    The same reasoning server_ctl.py uses when it checks the port instead of its
    own PID file.
    """
    me = os.getpid()
    try:
        mine = Path(__file__).resolve()
    except OSError:
        return None

    for proc in psutil.process_iter(["pid", "name"]):
        pid = proc.info["pid"]
        if pid == me:
            continue
        # Cheap name filter first. _script_of reads the command line, which on
        # Windows goes through ReadProcessMemory, so it is not something to pay
        # for on every process.
        if Path(proc.info["name"] or "").stem.lower() not in _INTERPRETERS:
            continue
        script = _script_of(proc)
        if not script:
            continue
        try:
            if Path(script).resolve() == mine:
                return pid
        except OSError:
            continue
    return None


def main() -> int:
    other = already_running()
    if other is not None:
        print(f"memory-watcher already running (pid {other}), nothing to do",
              file=sys.stderr)
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    print(f"Sampling every {INTERVAL_S}s to {OUT}")
    print(f"Drops to {PRESSURE_INTERVAL_S}s sampling below {PRESSURE_MB} MB free.")
    print("Ctrl+C to stop.")

    while True:
        try:
            row = sample()
        except Exception as e:
            row = {
                "t": datetime.now(timezone.utc).isoformat(),
                "error": f"{type(e).__name__}: {e}",
            }

        with OUT.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

        free = row.get("free_mb")
        if free is not None and free < PRESSURE_MB:
            top = row["top"][0] if row.get("top") else {}
            print(
                f"{row['t']}  PRESSURE free={free} MB  "
                f"biggest={top.get('name')} {top.get('rss_mb')} MB"
            )
            time.sleep(PRESSURE_INTERVAL_S)
        else:
            time.sleep(INTERVAL_S)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nstopped")
