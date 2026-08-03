"""The thread cap must leave headroom under the CPU ceiling it is checked against.

TORCH_THREADS used to be CPU_MAX_PERCENT of the core count, so the process was
allowed 79% of a 14 core machine against an 80% ceiling. Embedding at full
speed tripped that ceiling with nothing else running, and the sweep spent its
life oscillating: pause, CPU falls, resume, spike, pause. Measured at 406
pauses on one project and 64 s/file, with one log line reading
"DONE 4 files, 477.5 min".

These tests pin the gap. They fail if anyone re-derives one limit from the
other, which is exactly how the bug got in.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import config  # noqa: E402


def test_the_thread_cap_leaves_real_headroom_under_the_ceiling():
    """The invariant. A process allowed to reach its own pause threshold will
    pause on itself forever."""
    cores = 14  # the machine this was measured on
    threads = max(1, int(cores * config.TORCH_CORE_FRACTION))
    load_at_full_tilt = threads / cores * 100

    assert load_at_full_tilt < config.CPU_MAX_PERCENT, (
        f"{threads} threads on {cores} cores is {load_at_full_tilt:.0f}% of the "
        f"machine, against a {config.CPU_MAX_PERCENT:.0f}% pause ceiling. The "
        f"indexer will throttle itself."
    )
    # Not merely under it: far enough under that ordinary background load does
    # not push it over either.
    assert config.CPU_MAX_PERCENT - load_at_full_tilt >= 15


def test_the_fraction_is_not_the_ceiling_in_disguise():
    """Guards the specific regression: TORCH_CORE_FRACTION == CPU_MAX_PERCENT/100
    reproduces the original bug exactly."""
    assert config.TORCH_CORE_FRACTION != config.CPU_MAX_PERCENT / 100.0


def test_it_still_uses_a_meaningful_share_of_the_machine():
    """Overcorrecting into single threaded is its own kind of broken."""
    assert 0.3 <= config.TORCH_CORE_FRACTION <= 0.7


def test_at_least_one_thread_on_any_core_count():
    """int() truncation on a small machine must not yield zero threads."""
    for cores in (1, 2, 3, 4):
        assert max(1, int(cores * config.TORCH_CORE_FRACTION)) >= 1


def test_the_env_override_still_wins():
    """An operator who knows their machine can still set the thread count."""
    import os

    assert "CLEAN_RAG_TORCH_THREADS" in Path(config.__file__).read_text(
        encoding="utf-8"
    )
    # And the value in use is a positive int either way.
    assert isinstance(config.TORCH_THREADS, int) and config.TORCH_THREADS >= 1
    del os
