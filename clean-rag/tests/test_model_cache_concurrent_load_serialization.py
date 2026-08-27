"""ModelCache must never construct two embedders at the same time.

Written after clean-rag went down six times on 2026-08-26. Every failure that
day was two "ModelCache: loading" lines for DIFFERENT model ids started within
a second of each other, followed by:

    NotImplementedError: Cannot copy out of meta tensor; no data! Please use
    torch.nn.Module.to_empty() instead of torch.nn.Module.to() when moving
    module from meta to a different device.

raised out of SentenceTransformer.__init__ -> self.to(device). Roughly forty
sequential loads the same day did not fail once.

The cause is upstream and open: huggingface/transformers#41782 reproduces this
exact error with a ThreadPoolExecutor loading models on several threads, and
#22555 names the mechanism, `shutil.copy` plus `importlib.import_module` racing
on the shared transformers_modules package that trust_remote_code models are
written into. Both models this server routes to use trust_remote_code.

ModelCache had a lock per model_id, which serializes two callers wanting the
same model and does nothing at all about two callers wanting different ones.
That is precisely the failing case.

These tests use a fake embedder, so they run in milliseconds and need no model
files. What they check is the serialization, which is the part that was wrong.
Whether torch then behaves is upstream's business.
"""
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import embedding as embedding_module  # noqa: E402
from server.lang_router import ModelCache  # noqa: E402


class ConcurrencyRecordingEmbedder:
    """Stands in for SentenceTransformerEmbedding and records overlap.

    Construction is the dangerous window upstream, so the counter is raised in
    __init__ and lowered only after embed() returns. Anything that observes a
    depth above one has seen two real loads in flight together.
    """

    lock = threading.Lock()
    in_flight = 0
    max_in_flight = 0
    overlaps: list[tuple[str, str]] = []
    active: set = set()
    hold_s = 0.05

    @classmethod
    def reset(cls):
        cls.in_flight = 0
        cls.max_in_flight = 0
        cls.overlaps = []
        cls.active = set()

    def __init__(self, model_name: str):
        self._model_name = model_name
        cls = type(self)
        with cls.lock:
            cls.in_flight += 1
            cls.max_in_flight = max(cls.max_in_flight, cls.in_flight)
            for other in cls.active:
                cls.overlaps.append((other, model_name))
            cls.active.add(model_name)

    @property
    def model_name(self):
        return self._model_name

    @property
    def is_loaded(self):
        return True

    def embed(self, texts):
        # The real class does the model construction lazily inside embed(), so
        # the hold has to span this call too or the test would pass on an
        # implementation that warms up outside the lock.
        time.sleep(type(self).hold_s)
        cls = type(self)
        with cls.lock:
            cls.in_flight -= 1
            cls.active.discard(self._model_name)
        return [[0.0] * 8 for _ in texts]

    def embed_query(self, text):
        return [0.0] * 8


@pytest.fixture
def fake_embedder(monkeypatch):
    ConcurrencyRecordingEmbedder.reset()
    monkeypatch.setattr(
        embedding_module,
        "SentenceTransformerEmbedding",
        ConcurrencyRecordingEmbedder,
    )
    return ConcurrencyRecordingEmbedder


def _load_on_threads(cache, model_ids):
    """Ask for every model id at once and return (results, errors)."""
    results = {}
    errors = []
    start = threading.Barrier(len(model_ids))

    def worker(model_id):
        try:
            start.wait(timeout=5)
            results[model_id] = cache.get(model_id)
        except Exception as exc:  # noqa: BLE001 - the test reports it
            errors.append((model_id, exc))

    threads = [threading.Thread(target=worker, args=(m,)) for m in model_ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    for t in threads:
        assert not t.is_alive(), "a load thread never finished; likely a deadlock"
    return results, errors


def test_two_different_models_never_construct_at_the_same_time(fake_embedder):
    """The exact production failure: two model ids, two threads, one moment.

    Before the fix max_in_flight reached 2 here, which is the state that
    produced the meta tensor error in the real server.
    """
    cache = ModelCache(max_resident=4)
    results, errors = _load_on_threads(cache, ["model-alpha", "model-beta"])

    assert not errors, f"loads raised: {errors}"
    assert set(results) == {"model-alpha", "model-beta"}
    assert fake_embedder.max_in_flight == 1, (
        f"two constructions overlapped (max_in_flight="
        f"{fake_embedder.max_in_flight}, pairs={fake_embedder.overlaps}). "
        f"This is the state huggingface/transformers#41782 fails in."
    )


def test_many_different_models_never_construct_at_the_same_time(fake_embedder):
    """Widen it past two. A lock that only happens to work for a pair fails here."""
    cache = ModelCache(max_resident=16)
    model_ids = [f"model-{i}" for i in range(8)]
    results, errors = _load_on_threads(cache, model_ids)

    assert not errors, f"loads raised: {errors}"
    assert set(results) == set(model_ids)
    assert fake_embedder.max_in_flight == 1, (
        f"constructions overlapped (max_in_flight={fake_embedder.max_in_flight}, "
        f"pairs={fake_embedder.overlaps})"
    )


def test_same_model_requested_twice_is_constructed_once(fake_embedder):
    """The per model_id lock's original job still has to work."""
    cache = ModelCache(max_resident=4)
    results, errors = _load_on_threads(cache, ["model-alpha"] * 4)

    assert not errors, f"loads raised: {errors}"
    assert fake_embedder.max_in_flight == 1


def test_a_cache_hit_does_not_wait_on_an_in_flight_load(fake_embedder):
    """Serializing construction must not serialize ordinary reads.

    A global lock taken on every get(), rather than only on a miss, would make
    every search queue behind a cold load. That would be a real regression, so
    it gets its own test rather than being left to review.
    """
    cache = ModelCache(max_resident=4)
    cache.get("model-warm")  # resident from here on

    # A slow load of a different model, running in the background.
    fake_embedder.hold_s = 0.4
    slow = threading.Thread(target=cache.get, args=("model-slow",))
    slow.start()
    try:
        time.sleep(0.05)  # let the slow load get inside the lock
        began = time.monotonic()
        cache.get("model-warm")
        elapsed = time.monotonic() - began
    finally:
        slow.join(timeout=30)
        fake_embedder.hold_s = 0.05

    assert elapsed < 0.2, (
        f"a cache hit waited {elapsed:.3f}s for an unrelated load to finish; "
        f"the construction lock is being taken on the hit path too"
    )


def test_construct_lock_is_not_the_global_lock(fake_embedder):
    """Reusing _global_lock for construction deadlocks, so assert they differ.

    _slot_lock() takes _global_lock, and so does _enforce_max_resident(), both
    inside the load block. This states that in a way a future edit trips over,
    since the deadlock it prevents would otherwise hang the suite rather than
    fail it.
    """
    cache = ModelCache(max_resident=4)
    assert cache._construct_lock is not cache._global_lock


def test_eviction_still_runs_under_the_construction_lock(fake_embedder):
    """max_resident must still be enforced once loads are serialized.

    _enforce_max_resident takes _global_lock from inside the load block. If the
    construction lock were ever ordered the wrong way against it this test
    hangs instead of passing, which is the point.
    """
    cache = ModelCache(max_resident=2)
    for i in range(5):
        cache.get(f"model-{i}")
    assert len(cache.loaded_models()) <= 2
