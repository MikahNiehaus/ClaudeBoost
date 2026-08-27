"""Self healing must give up when restarting demonstrably is not fixing it.

On 2026-08-26 the server was restarted six times in about three hours. Every
restart found the same startup error (a NotImplementedError out of the model
load), and every restart re-ran the same startup and hit it again. The 15
minute cooldown in _self_heal_suppressed worked exactly as written, and that is
the point: a cooldown throttles a restart storm, it never ends one.

So _repeated_failure_suppressed counts consecutive restarts that saw the SAME
error reported by /status and stops after _MAX_IDENTICAL_SELF_HEALS.

The distinctions that matter, and which each get a test below:
  - unreachable server  -> restart, always. That is the case a restart fixes.
  - healthy server      -> nothing to count.
  - failed, new error   -> restart. Something changed.
  - failed, same error  -> stop after N. A fresh process runs the same startup.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _load_rag_enforce():
    import importlib.util
    path = str(Path(__file__).resolve().parents[1] / "hooks" / "rag-enforce.py")
    spec = importlib.util.spec_from_file_location("rag_enforce_repeat_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mod():
    return _load_rag_enforce()


@pytest.fixture
def home(tmp_path):
    (tmp_path / "state").mkdir()
    return tmp_path


def _stub_status(mod, monkeypatch, payload):
    """Make _status_failure_signature see *payload*, or raise if it is None."""
    class _Resp:
        def read(self):
            return json.dumps(payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _urlopen(*a, **k):
        if payload is None:
            raise OSError("connection refused")
        return _Resp()

    monkeypatch.setattr(mod.urllib.request, "urlopen", _urlopen)


def _stub_durable_write(mod, monkeypatch):
    """Real file writes, without importing server.durable_write."""
    def _write(path, text):
        Path(path).write_text(text, encoding="utf-8")

    monkeypatch.setattr(mod, "_load_write_durably", lambda: _write)


def test_unreachable_server_is_never_suppressed(mod, monkeypatch, home):
    """A server that does not answer is exactly what a restart fixes.

    Suppressing this case would turn a recoverable outage into a permanent one,
    which is strictly worse than the restart storm this guard exists to stop.
    """
    _stub_status(mod, monkeypatch, None)
    _stub_durable_write(mod, monkeypatch)
    for _ in range(10):
        assert mod._repeated_failure_suppressed(home, "8613") is None


def test_healthy_server_is_never_suppressed(mod, monkeypatch, home):
    _stub_status(mod, monkeypatch, {"status": "ready"})
    _stub_durable_write(mod, monkeypatch)
    for _ in range(10):
        assert mod._repeated_failure_suppressed(home, "8613") is None


def test_same_error_stops_at_the_limit(mod, monkeypatch, home):
    """The production case, using the production error string."""
    err = (
        "NotImplementedError: Cannot copy out of meta tensor; no data! Please "
        "use torch.nn.Module.to_empty() instead of torch.nn.Module.to()"
    )
    _stub_status(mod, monkeypatch, {"status": "failed", "last_error": err})
    _stub_durable_write(mod, monkeypatch)

    limit = mod._MAX_IDENTICAL_SELF_HEALS
    for attempt in range(1, limit):
        assert mod._repeated_failure_suppressed(home, "8613") is None, (
            f"attempt {attempt} was suppressed before reaching the limit of {limit}"
        )

    reason = mod._repeated_failure_suppressed(home, "8613")
    assert reason is not None, f"still restarting after {limit} identical failures"
    assert "meta tensor" in reason, "the reason must name the actual error"
    assert str(limit) in reason


def test_a_different_error_resets_the_count(mod, monkeypatch, home):
    """A changed error means a changed situation, so the count starts over."""
    _stub_durable_write(mod, monkeypatch)

    _stub_status(mod, monkeypatch, {"status": "failed", "last_error": "error one"})
    for _ in range(mod._MAX_IDENTICAL_SELF_HEALS - 1):
        assert mod._repeated_failure_suppressed(home, "8613") is None

    _stub_status(mod, monkeypatch, {"status": "failed", "last_error": "error two"})
    assert mod._repeated_failure_suppressed(home, "8613") is None, (
        "a new error inherited the old error's count"
    )


def test_recovery_clears_the_count(mod, monkeypatch, home):
    """Once the server comes back, a later failure must get a full set of tries."""
    _stub_durable_write(mod, monkeypatch)
    err = "the same error"

    _stub_status(mod, monkeypatch, {"status": "failed", "last_error": err})
    for _ in range(mod._MAX_IDENTICAL_SELF_HEALS - 1):
        mod._repeated_failure_suppressed(home, "8613")

    _stub_status(mod, monkeypatch, {"status": "ready"})
    mod._repeated_failure_suppressed(home, "8613")

    _stub_status(mod, monkeypatch, {"status": "failed", "last_error": err})
    assert mod._repeated_failure_suppressed(home, "8613") is None, (
        "the count survived a recovery"
    )


def test_an_expired_record_does_not_suppress(mod, monkeypatch, home):
    """A stale count must not disable self healing forever."""
    _stub_durable_write(mod, monkeypatch)
    import time

    record = home / "state" / mod._SELF_HEAL_FAILURE_NAME
    record.write_text(
        json.dumps({
            "signature": "old error",
            "count": 99,
            "at": time.time() - mod._FAILURE_SIGNATURE_TTL_S - 60,
        }),
        encoding="utf-8",
    )
    _stub_status(mod, monkeypatch, {"status": "failed", "last_error": "old error"})
    assert mod._repeated_failure_suppressed(home, "8613") is None


@pytest.mark.parametrize("body", [
    "not json at all",
    json.dumps(["a", "list"]),
    json.dumps({"signature": 5, "count": "many", "at": "now"}),
    json.dumps({"signature": "x"}),
    "",
])
def test_a_corrupt_record_does_not_suppress(mod, monkeypatch, home, body):
    """Unreadable means unknown, and unknown must never refuse a restart.

    Same rule _read_self_heal_stamp already follows for the cooldown: a record
    we cannot trust must fail toward restarting, because a permanent outage is
    worse than one extra restart.
    """
    _stub_durable_write(mod, monkeypatch)
    (home / "state" / mod._SELF_HEAL_FAILURE_NAME).write_text(body, encoding="utf-8")
    _stub_status(mod, monkeypatch, {"status": "failed", "last_error": "some error"})
    assert mod._repeated_failure_suppressed(home, "8613") is None


def test_a_future_dated_record_does_not_suppress(mod, monkeypatch, home):
    """Clock skew or a restored file must not read as a live count."""
    _stub_durable_write(mod, monkeypatch)
    import time

    (home / "state" / mod._SELF_HEAL_FAILURE_NAME).write_text(
        json.dumps({"signature": "e", "count": 99, "at": time.time() + 9999}),
        encoding="utf-8",
    )
    _stub_status(mod, monkeypatch, {"status": "failed", "last_error": "e"})
    assert mod._repeated_failure_suppressed(home, "8613") is None


def test_failed_status_with_no_error_text_is_not_counted(mod, monkeypatch, home):
    """No signature means nothing to compare, so it must not suppress.

    Counting an empty string would let every unrelated failure share one bucket
    and disable self healing for reasons that have nothing to do with each
    other.
    """
    _stub_durable_write(mod, monkeypatch)
    _stub_status(mod, monkeypatch, {"status": "failed", "last_error": ""})
    for _ in range(10):
        assert mod._repeated_failure_suppressed(home, "8613") is None


def test_trigger_self_heal_does_not_restart_once_suppressed(mod, monkeypatch, home):
    """End to end through the real entry point, not just the helper."""
    _stub_durable_write(mod, monkeypatch)
    monkeypatch.setattr(mod, "_clean_rag_home", lambda: home)
    monkeypatch.setattr(mod, "_self_heal_suppressed", lambda h: None)
    monkeypatch.setattr(mod, "_record_self_heal_attempt", lambda h: True)

    launched = []
    monkeypatch.setattr(
        mod.subprocess, "Popen", lambda *a, **k: launched.append(a) or None
    )

    err = "NotImplementedError: Cannot copy out of meta tensor; no data!"
    _stub_status(mod, monkeypatch, {"status": "failed", "last_error": err})

    for _ in range(6):
        mod._trigger_self_heal("8613")

    assert len(launched) == mod._MAX_IDENTICAL_SELF_HEALS - 1, (
        f"expected {mod._MAX_IDENTICAL_SELF_HEALS - 1} restarts before giving "
        f"up, got {len(launched)}"
    )
