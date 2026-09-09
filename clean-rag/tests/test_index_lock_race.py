"""acquire_index_lock() must give exactly one caller the lock, ever.

CLAUDE.md's claim: "All three take acquire_index_lock() so they can't race
each other," where the three are the per-edit hook, the 10 minute sweep, and
on demand /index-project. A fourth caller exists too: cli/reindex_batch.py
runs as its own OS process and takes the identical lock.

acquire_index_lock() (indexing.py) is check-then-act with no OS level
exclusivity between the two halves: it calls ``_INDEX_LOCK_PATH.exists()``,
optionally reads and validates the PID inside, and only then calls
``write_text()`` to claim it. Nothing atomic sits between the check and the
write -- no ``O_CREAT | O_EXCL``, no ``msvcrt.locking``, no file lock library.
Two callers can both observe "not locked" and both write, and the second
write silently overwrites the first caller's claim, so both believe they
hold an exclusive lock while writing to the same manifest.json and chroma
collection.

Reproduced here with real threads hitting the real function (no mocking of
the function under test), which is representative of the true failure: file
I/O releases the GIL, so two Python threads calling this racing for real is
the same failure shape as two OS processes doing it (cli/reindex_batch.py
started twice, or once alongside the server's own sweep).
"""
import subprocess
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_concurrent_acquire_never_grants_the_lock_twice(tmp_path, monkeypatch):
    from server import indexing

    lock_path = tmp_path / "index-lock.json"
    monkeypatch.setattr(indexing, "_INDEX_LOCK_PATH", lock_path)

    n_threads = 40
    barrier = threading.Barrier(n_threads)
    results: list[bool] = []
    results_lock = threading.Lock()

    def worker():
        barrier.wait()  # maximize the chance every thread hits the race window
        acquired = indexing.acquire_index_lock(operation="race")
        with results_lock:
            results.append(acquired)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    acquired_count = sum(results)
    assert acquired_count == 1, (
        f"{acquired_count} of {n_threads} concurrent callers believed they "
        f"held the exclusive index lock (expected exactly 1). "
        f"acquire_index_lock()'s exists-check-then-write is not atomic, so "
        f"two callers (e.g. cli/reindex_batch.py run twice, or run alongside "
        f"the server's own 10 minute sweep) can both pass the check and both "
        f"start writing the same project's manifest.json/chroma collection "
        f"at once -- the exact half-written-index failure the lock exists to "
        f"prevent."
    )


#: Child process body for the cross process case. Written to disk by the test
#: so the child inherits nothing from pytest's own process except the
#: interpreter, and every path it uses is passed in explicitly.
#:
#: The winner sleeps before releasing. Without that it exits immediately, the
#: lock is genuinely stale a millisecond later, and the next caller is correct
#: to take it -- which measures stale lock recovery, not exclusivity.
_CHILD_SOURCE = '''
import sys, time
from pathlib import Path

sys.path.insert(0, sys.argv[1])
lock_path, barrier_dir, n_procs = Path(sys.argv[2]), Path(sys.argv[3]), int(sys.argv[4])

from server import indexing
indexing._INDEX_LOCK_PATH = lock_path

# File based barrier. Interpreter startup alone varies by seconds across eight
# processes, which is long enough for a winner to finish and release before the
# last contender has even imported, so without this the race never happens.
barrier_dir.mkdir(parents=True, exist_ok=True)
(barrier_dir / ("ready-%d" % time.time_ns())).write_text("1")
deadline = time.time() + 120
while len(list(barrier_dir.iterdir())) < n_procs and time.time() < deadline:
    time.sleep(0.001)

got = indexing.acquire_index_lock(operation="xproc")
print("ACQUIRED" if got else "BUSY", flush=True)
if got:
    time.sleep(5.0)
    indexing.release_index_lock()
'''


def test_concurrent_processes_never_grant_the_lock_twice(tmp_path):
    """The lock's real job is cross process, not cross thread.

    cli/reindex_batch.py takes this lock from its own OS process, and the
    server's 10 minute sweep takes it from another, so a thread level result
    proves nothing about the case CLAUDE.md actually claims: "All three take
    acquire_index_lock() so they can't race each other."

    Real interpreters, no threading, no shared GIL. Measured against the
    exists-then-write version this reports 2 of 8 winners; against an atomic
    O_EXCL claim it reports 1.
    """
    clean_rag_home = str(Path(__file__).resolve().parents[1])
    child = tmp_path / "lock_contender.py"
    child.write_text(_CHILD_SOURCE, encoding="utf-8")

    n_procs = 8
    args = [
        sys.executable, str(child), clean_rag_home,
        str(tmp_path / "index-lock.json"), str(tmp_path / "barrier"), str(n_procs),
    ]
    procs = [
        subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for _ in range(n_procs)
    ]
    outs = []
    for p in procs:
        stdout, stderr = p.communicate(timeout=180)
        assert p.returncode == 0, f"contender failed: {stderr}"
        outs.append(stdout.strip())

    acquired = outs.count("ACQUIRED")
    assert acquired == 1, (
        f"{acquired} of {n_procs} separate OS processes believed they held the "
        f"exclusive index lock (expected exactly 1); results were {outs}. Two "
        f"indexers holding it at once write the same manifest.json and chroma "
        f"collection, which is the half written index the lock exists to prevent."
    )


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v", "-s"]))
