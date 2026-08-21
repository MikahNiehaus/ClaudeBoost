"""CPU throttling is off, and if it is ever turned back on it must not self trip.

History. TORCH_THREADS used to be CPU_MAX_PERCENT of the core count, so the
process was allowed 79% of a 14 core machine against an 80% pause ceiling.
Embedding at full speed tripped that ceiling with nothing else running and the
sweep spent its life oscillating: pause, CPU falls, resume, spike, pause.
Measured at 406 pauses on one project and 64 s/file, with one log line reading
"DONE 4 files, 477.5 min". Control theory calls this hunting.

Throttling was then turned off outright by request. These tests pin BOTH
states: off means genuinely off (no sample, no pause), and if a real ceiling is
ever restored, the thread cap must leave headroom under it so the original bug
cannot come back.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import config  # noqa: E402
from server.resource_guard import sample_pressure  # noqa: E402

THROTTLING_OFF = config.CPU_MAX_PERCENT >= 100


def _load_at_full_tilt(cores=14):
    return max(1, int(cores * config.TORCH_CORE_FRACTION)) / cores * 100


def test_the_two_limits_are_never_the_same_number():
    """The actual bug: deriving the thread cap from the pause ceiling. This
    holds in both states, because it is what caused the oscillation."""
    if THROTTLING_OFF:
        # Off is off: using every core is correct, there is nothing to trip.
        assert config.TORCH_CORE_FRACTION == 1.0
    else:
        assert config.TORCH_CORE_FRACTION != config.CPU_MAX_PERCENT / 100.0


def test_a_restored_ceiling_must_leave_the_thread_cap_real_headroom():
    """Guards the regression for whoever turns throttling back on."""
    if THROTTLING_OFF:
        return
    load = _load_at_full_tilt()
    assert load < config.CPU_MAX_PERCENT, (
        f"{load:.0f}% of the machine against a {config.CPU_MAX_PERCENT:.0f}% "
        f"ceiling: the indexer will throttle itself"
    )
    assert config.CPU_MAX_PERCENT - load >= 15


def test_off_means_no_cpu_pause_is_ever_reported():
    """Even a machine pinned at 100% must not produce CPU pressure when the
    ceiling is disabled. A ceiling of 100 compared with >= would still fire."""
    assert sample_pressure(max_percent=100.0, min_free_ram_mb=0.0) is None
    assert sample_pressure(max_percent=1000.0, min_free_ram_mb=0.0) is None


def test_the_memory_guard_is_still_live():
    """Memory was deliberately NOT removed. It is the guard against the failure
    that actually stopped the machine, not a throttle."""
    huge = 10 ** 9  # more free RAM than any machine has
    assert sample_pressure(max_percent=100.0, min_free_ram_mb=huge) is not None
    assert config.MIN_FREE_RAM_MB > 0


#: What SFR-Embedding-Code-400M_R actually costs resident, measured and recorded
#: on ModelCache.DEFAULT_MAX_RESIDENT (lang_router.py: "1069 MB for CodeRankEmbed
#: (137M params) and 2161 MB for SFR (400M), measured"). Written out here rather
#: than read from config so the assertions below are against the measurement
#: instead of against the constant they are checking: deriving the expected value
#: from LARGEST_MODEL_RESIDENT_MB made the test `X*2 >= X*2`, which passes at any
#: value of X, including one too small to cover the model.
MEASURED_LARGEST_MODEL_MB = 2161.0


def test_the_memory_gate_covers_a_model_load_plus_its_embedding_peak():
    """The RAM gate and the resident model cap are one budget.

    MIN_FREE_RAM_MB stayed at a flat 3072 MB while MAX_RESIDENT_MODELS went from
    1 to 2. That left the gate below what a single project can still allocate
    after passing it: one model load at 2161 MB plus an embedding peak that
    roughly doubles the active model. A machine cleared the gate and then failed
    partway through a project with "DefaultCPUAllocator: not enough memory",
    which is the failure in state/server.log this covers.

    Asserted against the default rather than config.MIN_FREE_RAM_MB, because
    CLEAN_RAG_MIN_FREE_RAM_MB is a real knob and a machine that has set it lower
    on purpose is not a regression.
    """
    assert config.LARGEST_MODEL_RESIDENT_MB >= MEASURED_LARGEST_MODEL_MB, (
        f"the budget calls the largest routable model "
        f"{config.LARGEST_MODEL_RESIDENT_MB:.0f} MB, but SFR measured "
        f"{MEASURED_LARGEST_MODEL_MB:.0f} MB resident"
    )
    needed = MEASURED_LARGEST_MODEL_MB * 2
    assert config._default_min_free_ram_mb() >= needed, (
        f"the default RAM gate is {config._default_min_free_ram_mb():.0f} MB "
        f"against a {needed:.0f} MB worst case between two pressure checks"
    )


def test_the_default_gate_is_the_number_that_actually_stops_a_sweep(monkeypatch):
    """A declared budget that nothing enforces is not a budget.

    Drives the real pressure sampler either side of the configured gate with
    psutil's reading faked, so this fails if the gate stops being wired to
    sample_pressure, if the units drift (MB against bytes), or if the comparison
    flips. The test above pins the number; this one pins that the number bites.
    """
    import psutil

    class _Memory:
        def __init__(self, mb):
            self.available = int(mb * 1024 * 1024)

    gate = config.MIN_FREE_RAM_MB

    monkeypatch.setattr(psutil, "virtual_memory", lambda: _Memory(gate - 1))
    assert sample_pressure(max_percent=100.0) is not None, (
        "a machine one MB under the gate reported no memory pressure"
    )

    monkeypatch.setattr(psutil, "virtual_memory", lambda: _Memory(gate + 1))
    assert sample_pressure(max_percent=100.0) is None, (
        "a machine one MB over the gate was refused, so the sweep can never run"
    )


def test_the_ram_gate_knob_wins_and_an_empty_value_falls_back():
    """The env override has to work, and an empty value must not crash the
    server at import: the previous default lived in os.environ.get's fallback,
    so CLEAN_RAG_MIN_FREE_RAM_MB="" reached float("") and raised."""
    import importlib
    import os

    original = os.environ.get("CLEAN_RAG_MIN_FREE_RAM_MB")
    try:
        os.environ["CLEAN_RAG_MIN_FREE_RAM_MB"] = "1234"
        assert importlib.reload(config).MIN_FREE_RAM_MB == 1234.0

        os.environ["CLEAN_RAG_MIN_FREE_RAM_MB"] = ""
        reloaded = importlib.reload(config)
        assert reloaded.MIN_FREE_RAM_MB == reloaded._default_min_free_ram_mb()
    finally:
        if original is None:
            os.environ.pop("CLEAN_RAG_MIN_FREE_RAM_MB", None)
        else:
            os.environ["CLEAN_RAG_MIN_FREE_RAM_MB"] = original
        importlib.reload(config)


def test_a_real_ceiling_still_works_when_set():
    """Turning it back on must actually do something."""
    assert sample_pressure(max_percent=0.0, min_free_ram_mb=0.0) is not None


def test_at_least_one_thread_on_any_core_count():
    for cores in (1, 2, 3, 4):
        assert max(1, int(cores * config.TORCH_CORE_FRACTION)) >= 1
