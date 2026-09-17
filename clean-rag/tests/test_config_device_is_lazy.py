"""Device detection must stay lazy, and must still pick the right device.

`server/config.py` used to run `DEVICE = _detect_device()` at module scope.
That function imports torch to probe CUDA, so importing the module to read a
port number cost about 4.7 seconds against a 0.06s bare interpreter start. Four
hooks do exactly that, two of them on every prompt and every edit.

Nothing tested device selection before this, so the refactor that fixed the cost
had nothing protecting it. These tests cover both halves: that importing the
module stays cheap, and that the device chosen is still correct on a machine
with a GPU, which is the case a developer on a CPU box cannot notice breaking.
"""
from __future__ import annotations

import logging
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

CLEAN_RAG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLEAN_RAG))

from server import config  # noqa: E402


def _fresh():
    """A config module with the device cache cleared.

    get_device is process cached on purpose, so every test that changes the
    environment has to drop the cache or it reads a previous test's answer.
    """
    config.get_device.cache_clear()
    return config


# ---------------------------------------------------------------------------
# The cost. This is the defect the refactor existed to fix.
# ---------------------------------------------------------------------------

def test_importing_config_does_not_import_torch():
    """The regression guard. Importing config must not pull in torch.

    Run in a subprocess because torch may already be in this process's
    sys.modules from another test, which would make an in-process assertion
    pass for the wrong reason.
    """
    script = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, r"{CLEAN_RAG}")
        import server.config
        assert server.config.STANDALONE_PORT
        print("torch" in sys.modules)
    """)
    out = subprocess.run([sys.executable, "-c", script],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "False", (
        "importing server.config pulled in torch; device detection is eager "
        "again and every hook that reads a constant from this module pays for "
        "it"
    )


def test_reading_a_constant_stays_cheap():
    """Reading the port must not cost a torch import.

    Asserted as a ratio against a bare interpreter start rather than an
    absolute second count, so the test does not go red on a slow or loaded
    machine.
    """
    bare = textwrap.dedent("""
        import time; print(time.perf_counter())
    """)
    withcfg = textwrap.dedent(f"""
        import time, sys
        sys.path.insert(0, r"{CLEAN_RAG}")
        from server.config import STANDALONE_PORT
        print(time.perf_counter())
    """)

    def run(src):
        import time
        best = None
        for _ in range(3):
            t0 = time.perf_counter()
            r = subprocess.run([sys.executable, "-c", src],
                               capture_output=True, text=True, timeout=120)
            assert r.returncode == 0, r.stderr
            dt = time.perf_counter() - t0
            best = dt if best is None else min(best, dt)
        return best

    baseline, loaded = run(bare), run(withcfg)
    # A torch import is ~75x a bare start. Real work here is a few file reads.
    assert loaded < baseline * 8 + 1.0, (
        f"importing server.config took {loaded:.2f}s against a {baseline:.2f}s "
        f"bare start, which is the shape of an eager heavy import"
    )


# ---------------------------------------------------------------------------
# Correctness. A CPU only machine cannot notice these breaking.
# ---------------------------------------------------------------------------

def test_explicit_override_wins_and_skips_the_probe(monkeypatch):
    monkeypatch.setenv("CLEAN_RAG_DEVICE", "cuda:1")
    cfg = _fresh()

    def explode():
        raise AssertionError("probed hardware despite an explicit override")

    monkeypatch.setattr(cfg, "_detect_device",
                        lambda: cfg.os.environ.get("CLEAN_RAG_DEVICE") or explode())
    assert cfg.get_device() == "cuda:1"


def test_picks_cuda_when_available(monkeypatch):
    monkeypatch.delenv("CLEAN_RAG_DEVICE", raising=False)
    cfg = _fresh()
    fake = type("T", (), {
        "cuda": type("C", (), {"is_available": staticmethod(lambda: True)}),
        "backends": type("B", (), {}),
    })
    monkeypatch.setitem(sys.modules, "torch", fake)
    assert cfg.get_device() == "cuda"


def test_falls_back_to_cpu_without_a_gpu(monkeypatch):
    monkeypatch.delenv("CLEAN_RAG_DEVICE", raising=False)
    cfg = _fresh()
    mps = type("M", (), {"is_available": staticmethod(lambda: False)})
    fake = type("T", (), {
        "cuda": type("C", (), {"is_available": staticmethod(lambda: False)}),
        "backends": type("B", (), {"mps": mps}),
    })
    monkeypatch.setitem(sys.modules, "torch", fake)
    assert cfg.get_device() == "cpu"


def test_picks_mps_when_available(monkeypatch):
    """Apple silicon. Nothing on a CI box or a Windows machine covers this."""
    monkeypatch.delenv("CLEAN_RAG_DEVICE", raising=False)
    cfg = _fresh()
    mps = type("M", (), {"is_available": staticmethod(lambda: True)})
    fake = type("T", (), {
        "cuda": type("C", (), {"is_available": staticmethod(lambda: False)}),
        "backends": type("B", (), {"mps": mps}),
    })
    monkeypatch.setitem(sys.modules, "torch", fake)
    assert cfg.get_device() == "mps"


def test_a_torch_that_cannot_probe_resolves_to_cpu_and_says_so(monkeypatch, caplog):
    """A broken CUDA install raises from is_available(), which is not ImportError.

    Letting it propagate resolves nothing, so every later caller repeats the
    ~4.7s probe for the life of the process. CPU is the honest answer, and the
    model load that follows still raises the real error where it can be acted
    on. Logged, because embedding on CPU with a GPU in the machine is the kind
    of slow nobody traces back to here.
    """
    monkeypatch.delenv("CLEAN_RAG_DEVICE", raising=False)
    cfg = _fresh()

    def broken():
        raise OSError("[WinError 126] The specified module could not be found")

    fake = type("T", (), {
        "cuda": type("C", (), {"is_available": staticmethod(broken)}),
        "backends": type("B", (), {}),
    })
    monkeypatch.setitem(sys.modules, "torch", fake)

    with caplog.at_level(logging.WARNING, logger="server.config"):
        assert cfg.get_device() == "cpu"

    assert "Device probe failed" in caplog.text, (
        "a probe that fell back to CPU did so silently"
    )


def test_cpu_when_torch_is_absent(monkeypatch):
    """No torch installed is a supported state, not a crash."""
    monkeypatch.delenv("CLEAN_RAG_DEVICE", raising=False)
    cfg = _fresh()
    real = __builtins__["__import__"] if isinstance(__builtins__, dict) \
        else __builtins__.__import__

    def no_torch(name, *a, **k):
        if name == "torch":
            raise ImportError("no torch")
        return real(name, *a, **k)

    monkeypatch.setattr("builtins.__import__", no_torch)
    assert cfg.get_device() == "cpu"


def test_probe_runs_once(monkeypatch):
    """Cached, so repeated reads do not repeat the probe."""
    monkeypatch.delenv("CLEAN_RAG_DEVICE", raising=False)
    cfg = _fresh()
    calls = []
    monkeypatch.setattr(cfg, "_detect_device",
                        lambda: (calls.append(1), "cpu")[1])
    assert cfg.get_device() == cfg.get_device() == "cpu"
    assert len(calls) == 1, f"probed {len(calls)} times, expected 1"


# ---------------------------------------------------------------------------
# The compatibility shim.
# ---------------------------------------------------------------------------

def test_legacy_DEVICE_attribute_still_resolves(monkeypatch):
    """An import this refactor missed must keep working, lazily."""
    monkeypatch.setenv("CLEAN_RAG_DEVICE", "cpu")
    cfg = _fresh()
    assert cfg.DEVICE == "cpu"


def test_unknown_attribute_still_raises():
    with pytest.raises(AttributeError):
        config.NOT_A_REAL_SETTING
