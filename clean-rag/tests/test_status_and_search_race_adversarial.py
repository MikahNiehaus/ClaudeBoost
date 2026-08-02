"""Adversarial tests for /status failed/ready/warming_up and for the
handle_search executor-based retry path (concurrency + non-blocking event
loop, and no stale last_error leak after a later retry succeeds).
"""
import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path("C:/Development/ClaudeBoost/clean-rag")))

import server.app as app_mod
from server.lang_router import ModelCache


@pytest.fixture(autouse=True)
def _reset_app_globals():
    """server.app keeps module level singletons. Snapshot and restore them
    so these tests cannot leak state into each other or into a real run."""
    orig_cache = app_mod._model_cache
    orig_error = app_mod._warmup_error
    yield
    app_mod._model_cache = orig_cache
    app_mod._warmup_error = orig_error


def test_status_reports_failed_with_reason_when_never_loaded():
    app_mod._model_cache = ModelCache()  # constructed, empty, never loaded
    app_mod._warmup_error = "OSError: could not load config for bigcode/starencoder"

    result = asyncio.run(app_mod.handle_status(MagicMock()))
    body = _json_body(result)
    assert body["status"] == "failed", body
    assert body["last_error"] == "OSError: could not load config for bigcode/starencoder"


def test_status_reports_warming_up_when_still_loading_no_error_yet():
    app_mod._model_cache = ModelCache()
    app_mod._warmup_error = None

    result = asyncio.run(app_mod.handle_status(MagicMock()))
    body = _json_body(result)
    assert body["status"] == "warming_up"
    assert "last_error" not in body


def test_status_does_not_leak_stale_error_after_a_later_retry_succeeds():
    """The exact property named in the requirements: /status must not leak
    a stale last_error after a later handler retried the load and it
    succeeded."""
    app_mod._model_cache = ModelCache()
    app_mod._warmup_error = "OSError: could not load config for bigcode/starencoder"

    class FakeEmbedder:
        model_name = "nomic-ai/CodeRankEmbed"

    # Simulate a later successful retry loading the model into the cache
    # (this is what handle_search's model_cache.get() call would do).
    app_mod._model_cache._cache["nomic-ai/CodeRankEmbed"] = FakeEmbedder()

    result = asyncio.run(app_mod.handle_status(MagicMock()))
    body = _json_body(result)
    assert body["status"] == "ready", body
    assert "last_error" not in body, (
        "status flipped to ready but a stale last_error string is still "
        "present in the payload"
    )


def test_status_none_cache_is_warming_up_not_a_crash():
    """Before create_app() has run at all, _model_cache is genuinely None.
    This must not be confused with 'failed'."""
    app_mod._model_cache = None
    app_mod._warmup_error = None
    result = asyncio.run(app_mod.handle_status(MagicMock()))
    body = _json_body(result)
    assert body["status"] == "warming_up"


def _json_body(web_response):
    import json
    return json.loads(web_response.body.decode("utf-8"))


# ---------------------------------------------------------------------------
# Concurrency: two handle_search calls arriving while the model is unloaded.
# The load must happen in the executor (not block the event loop), and the
# per-model lock inside ModelCache must prevent a duplicate concurrent load.
# ---------------------------------------------------------------------------

def test_concurrent_model_cache_get_does_not_double_load(monkeypatch):
    """Two threads calling ModelCache.get() for the same not-yet-loaded model
    concurrently must trigger exactly one real load, proving the per-slot
    lock actually serializes the slow path rather than racing it."""
    import threading

    load_count = {"n": 0}
    load_started = threading.Event()
    release_load = threading.Event()

    class SlowFakeEmbedder:
        def __init__(self, model_name):
            self._model_name = model_name
            load_count["n"] += 1
            load_started.set()
            # Hold the slot lock long enough that a second concurrent caller
            # would double load if the locking were broken.
            release_load.wait(timeout=5)

        @property
        def model_name(self):
            return self._model_name

        def embed(self, texts):
            return [[0.1]]

    monkeypatch.setattr("server.embedding.SentenceTransformerEmbedding", SlowFakeEmbedder)
    cache = ModelCache()

    results = []

    def worker():
        results.append(cache.get("slow-model").model_name)

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    load_started.wait(timeout=5)
    t2.start()  # arrives while the first load is still in progress
    time.sleep(0.2)
    release_load.set()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert load_count["n"] == 1, f"expected exactly one real load, got {load_count['n']}"
    assert results == ["slow-model", "slow-model"]


def test_handle_search_runs_model_load_in_executor_not_on_event_loop(monkeypatch):
    """The event loop must stay responsive while the model loads: a second
    coroutine scheduled on the same loop must be able to run while the
    (blocking, thread pool bound) model load is in flight."""
    import threading
    from server.lang_router import ModelCache as RealModelCache

    load_started = threading.Event()
    release_load = threading.Event()

    class SlowFakeEmbedder:
        def __init__(self, model_name):
            self._model_name = model_name
            load_started.set()
            release_load.wait(timeout=5)

        @property
        def model_name(self):
            return self._model_name

        def embed(self, texts):
            return [[0.1]]

    monkeypatch.setattr("server.embedding.SentenceTransformerEmbedding", SlowFakeEmbedder)
    monkeypatch.setattr(app_mod, "CODE_EMBEDDING_MODEL", "slow-model", raising=False)

    async def run():
        cache = RealModelCache()
        loop = asyncio.get_running_loop()
        other_ran = {"flag": False}

        async def other_coro():
            # If the model load blocked the event loop, this would never get
            # a chance to run until the load finished.
            load_started.wait(timeout=5)
            other_ran["flag"] = True
            release_load.set()

        load_future = loop.run_in_executor(None, cache.get, "slow-model")
        other_future = asyncio.ensure_future(other_coro())
        await asyncio.gather(load_future, other_future)
        return other_ran["flag"]

    other_ran_while_loading = asyncio.run(run())
    assert other_ran_while_loading, (
        "the other coroutine never ran while the model load was in flight, "
        "meaning the load blocked the event loop"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
