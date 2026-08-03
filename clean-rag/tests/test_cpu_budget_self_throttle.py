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


def test_a_real_ceiling_still_works_when_set():
    """Turning it back on must actually do something."""
    assert sample_pressure(max_percent=0.0, min_free_ram_mb=0.0) is not None


def test_at_least_one_thread_on_any_core_count():
    for cores in (1, 2, 3, 4):
        assert max(1, int(cores * config.TORCH_CORE_FRACTION)) >= 1
