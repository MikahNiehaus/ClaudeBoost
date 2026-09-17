"""The device probe must run once per process, including under a race.

`server/config.py` resolves the compute device lazily, because the probe
imports torch and that cost about 4.7s on every `import server.config`. The
question these tests answer is what happens when two callers reach the
unresolved probe at the same moment.

`functools.cache` is not enough on its own, and the CPython docs say so:
"Call-once behavior is not guaranteed because locks are not held during the
function call." It locks the cache dict, not the call. Two callers that both
miss before either inserts both run the whole probe.

That shape is reachable here. `embedding.py::_load_model` calls `get_device()`
under a *per instance* lock, and `app.py` builds an independent
`SentenceTransformerEmbedding()` for `_doc_embedder` outside ModelCache's
`_construct_lock`, loaded on the first `docs:` request rather than warmed at
startup. Two embedder instances can therefore reach an unresolved probe at
once, most plausibly after a startup warmup failure, since a probe that raises
resolves nothing and leaves the next callers racing again.
"""
from __future__ import annotations

import importlib
import sys
import threading
import time
from pathlib import Path

CLEAN_RAG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLEAN_RAG))

from server import config  # noqa: E402

# Long enough that an unsynchronized implementation lets every released thread
# into the probe, short enough to stay cheap. The start barrier releases the
# racers within microseconds of each other, so the margin is large.
PROBE_HOLD_S = 0.25


def _restore():
    """Put the real probe back, so later tests do not see a throwaway closure."""
    real_module = importlib.reload(config)
    real_module.get_device.cache_clear()


def _run_racers(n, target):
    """Start *n* threads on *target* and join them, failing rather than hanging."""
    threads = [threading.Thread(target=target) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
        assert not t.is_alive(), "get_device() did not return under concurrency"


def test_concurrent_first_access_probes_at_most_once():
    """Eight threads reach an unresolved get_device() together. One probe runs.

    The barrier is a start gate, not a rendezvous inside the probe: a correct
    implementation admits a single thread, so anything that waits on the other
    seven in there can only complete while the defect is present.
    """
    config.get_device.cache_clear()

    n = 8
    start = threading.Barrier(n)
    calls = []
    calls_lock = threading.Lock()

    def slow_probe():
        with calls_lock:
            calls.append(1)
        time.sleep(PROBE_HOLD_S)  # hold the miss window open
        return "cpu"

    def race():
        start.wait(timeout=10)
        config.get_device()

    config._detect_device = slow_probe
    try:
        _run_racers(n, race)
    finally:
        _restore()

    assert len(calls) == 1, (
        f"_detect_device ran {len(calls)} times under concurrent first access. "
        "The probe imports torch, so every extra run is another ~4.7s and "
        "another concurrent sentence-transformers import."
    )


def test_every_racer_gets_the_resolved_device():
    """One probe still has to answer all eight callers, not just the winner."""
    config.get_device.cache_clear()

    n = 8
    start = threading.Barrier(n)
    seen = []
    seen_lock = threading.Lock()

    def slow_probe():
        time.sleep(PROBE_HOLD_S)
        return "xpu:7"

    def race():
        start.wait(timeout=10)
        device = config.get_device()
        with seen_lock:
            seen.append(device)

    config._detect_device = slow_probe
    try:
        _run_racers(n, race)
    finally:
        _restore()

    assert seen == ["xpu:7"] * n, f"racers disagreed about the device: {set(seen)}"


def test_failed_probe_is_never_cached_so_every_retry_reprobes():
    """A probe that raises resolves nothing, and the next call tries again.

    Deliberate, and the cheaper looking alternative is worse: caching the
    failure would pin the process to a wrong device for its whole life on one
    bad moment, and the process outlives the fault. The cost of retrying is
    bounded by the companion test below, which holds the retries to one at a
    time.
    """
    config.get_device.cache_clear()
    attempts = []

    def boom():
        attempts.append(1)
        raise RuntimeError("simulated probe failure")

    config._detect_device = boom
    try:
        for _ in range(3):
            try:
                config.get_device()
            except RuntimeError:
                pass
    finally:
        _restore()

    assert len(attempts) == 3, (
        f"expected each call after a raised probe to retry, got {len(attempts)}"
    )


def test_retries_after_a_failed_probe_do_not_run_at_once():
    """Retrying is per caller. Running those retries concurrently is not.

    This is the other half of the decision above. An unresolved probe leaves
    every later caller eligible to run it, so without a lock a burst of
    requests after a warmup failure means a burst of simultaneous torch
    imports. Peak concurrency of one is what makes "do not cache the failure"
    affordable.
    """
    config.get_device.cache_clear()

    n = 6
    start = threading.Barrier(n)
    lock = threading.Lock()
    peaks = []
    live = 0

    def boom():
        nonlocal live
        with lock:
            live += 1
            peaks.append(live)
        time.sleep(0.05)
        with lock:
            live -= 1
        raise RuntimeError("simulated probe failure")

    def race():
        start.wait(timeout=10)
        try:
            config.get_device()
        except RuntimeError:
            pass

    config._detect_device = boom
    try:
        _run_racers(n, race)
    finally:
        _restore()

    assert len(peaks) == n, f"expected {n} retries, got {len(peaks)}"
    assert max(peaks) == 1, (
        f"{max(peaks)} probes ran at once after a failure; retries are supposed "
        "to queue behind the lock, not stampede"
    )
