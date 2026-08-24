"""One line health snapshot of clean-rag plus the memory it is using.

Written for a watch loop after the phantom deletion fix went in: the fix is
test verified but had never run in production, and the open question is whether
a sweep still drives the machine toward the memory exhaustion that preceded
every bugcheck. So this reports the two things that answer that, and nothing
else, because a check that prints a page does not get read on the tenth run.

Exit code 1 when something looks wrong, so a caller can branch on it.
"""

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

HOME = Path(__file__).resolve().parents[1]
LOG = HOME / "clean-rag" / "state" / "server.log"
WATCH = HOME / "state" / "memory-watch.jsonl"
PORT = 8613


def server() -> tuple[str, float]:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{PORT}/status", timeout=8
        ) as r:
            d = json.loads(r.read())
        return d.get("status", "?"), d.get("uptime_s", 0.0)
    except Exception as e:
        return f"DOWN ({type(e).__name__})", 0.0


def memory() -> tuple[float, str]:
    """Lowest free RAM seen recently, and the biggest process at that moment."""
    if not WATCH.exists():
        return -1.0, "watcher not writing"
    rows = []
    # Only the tail matters and the file grows without bound, so read the last
    # chunk rather than the whole thing.
    with WATCH.open("rb") as fh:
        fh.seek(0, os.SEEK_END)
        fh.seek(max(0, fh.tell() - 200_000))
        for line in fh.read().decode("utf-8", "replace").splitlines()[1:]:
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    rows = [r for r in rows if "free_mb" in r]
    if not rows:
        return -1.0, "no samples"
    low = min(rows, key=lambda r: r["free_mb"])
    top = low["top"][0] if low.get("top") else {}
    return low["free_mb"], f"{top.get('name', '?')} {top.get('rss_mb', 0)} MB"


def sweeps() -> tuple[int, int, int]:
    """(sweeps seen, files dropped, could-not-drop warnings) in the log tail."""
    if not LOG.exists():
        return 0, 0, 0
    with LOG.open("rb") as fh:
        fh.seek(0, os.SEEK_END)
        fh.seek(max(0, fh.tell() - 400_000))
        tail = fh.read().decode("utf-8", "replace")
    done = len(re.findall(r"Reindex sweep done", tail))
    dropped = sum(
        int(m) for m in re.findall(r"Dropped (\d+) of \d+ deleted file", tail)
    )
    stuck = len(re.findall(r"Could not drop deleted", tail))
    return done, dropped, stuck


def main() -> int:
    status, uptime = server()
    low_mb, who = memory()
    done, dropped, stuck = sweeps()

    print(
        f"clean-rag {status} up={uptime / 60:.0f}m | "
        f"sweeps={done} dropped={dropped} stuck={stuck} | "
        f"lowest free RAM {low_mb:.0f} MB (biggest: {who})"
    )

    bad = []
    if status != "ready":
        bad.append("server not ready")
    # The pre crash logs showed the headroom guard firing at 1 MB free. 4 GB is
    # well above that and still far below the 10 GB floor measured across 4757
    # samples with the server stopped, so crossing it means something changed.
    if 0 <= low_mb < 4096:
        bad.append(f"free RAM fell to {low_mb:.0f} MB")
    # The whole point of the fix. Any recurrence is a regression, not a nit.
    if stuck:
        bad.append(f"{stuck} 'Could not drop deleted' lines are back")

    if bad:
        print("ATTENTION: " + "; ".join(bad))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
