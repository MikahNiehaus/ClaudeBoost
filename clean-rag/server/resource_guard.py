"""One definition of "the machine is too busy to keep indexing".

Two callers need the same rule and cannot share the same code path:

  * ``auto_reindex.wait_for_system_headroom()`` runs on the event loop and can
    await a back-off sleep between samples.
  * ``indexing.index_project()`` runs inside a ``run_in_executor`` worker
    thread, where there is no event loop to await on and spinning one up inside
    the worker would be worse than not checking at all.

So the sampling itself lives here as a plain synchronous function and each
caller wraps it in whatever waiting it can actually do.
"""

import logging
import threading
import time

from .config import CPU_MAX_PERCENT, INDEX_PRESSURE_CHECK_S, MIN_FREE_RAM_MB

logger = logging.getLogger(__name__)


# ``psutil.cpu_percent(interval=None)`` keeps ONE "previous sample" per process
# and reports the delta since it. Two threads reaching it at once consume each
# other's baseline and both read nonsense (giampaolo/psutil#1703).
#
# That bookkeeping is process global, so the lock guarding it has to be module
# level, not per instance. A per-instance lock leaves two PressureCheckpoints
# free to overlap (a manual /index-project racing the sweep is exactly two
# instances) and does nothing at all for auto_reindex.wait_for_system_headroom(),
# which calls sample_pressure() directly. Putting the lock inside the sampling
# functions themselves is what makes it cover every call site, including ones
# added later.
#
# Held across the psutil reads only. Milliseconds, not microseconds. Measured
# twice with real threads and real psutil, 500 samples each: a median hold of
# 0.2 to 0.5ms, a p95 of 0.4 to 0.9ms, and a worst case in the 12 to 16ms range
# both times. Contended (the sweep and a manual index sampling at once) the wait
# to acquire is near zero at the median and lands in the same tens of
# milliseconds at the tail. Expect the tail to move with machine load; the scale
# is the durable part, not the decimals.
#
# Short enough to be worth a correct reading, long enough to say plainly:
# wait_for_system_headroom() takes this synchronous lock from the event loop
# without awaiting, so a tail sample does stall the loop for those
# milliseconds. It is a stall of a frame, not of a request, and the alternative
# is two threads reading each other's baseline. Nothing slower than these
# counter lookups may be held under it though. Indexing work or file IO here
# would take that stall from tens of milliseconds to seconds.
_SAMPLE_LOCK = threading.Lock()


def prime_cpu_sampling() -> None:
    """Take one CPU sample and throw it away.

    ``psutil.cpu_percent(interval=None)`` has no previous sample to diff
    against on its first call, and psutil documents that it "will return a
    meaningless 0.0 value which you are supposed to ignore". Reading that as an
    idle machine is how a pressure check silently never fires.
    """
    try:
        import psutil
    except ImportError:
        return
    # Same global baseline sample_pressure() reads, so the same lock. The
    # import stays outside it: acquiring a lock around an import invites a
    # deadlock against Python's own import machinery.
    with _SAMPLE_LOCK:
        psutil.cpu_percent(interval=None)


def sample_pressure(
    max_percent: float = CPU_MAX_PERCENT,
    min_free_ram_mb: float = MIN_FREE_RAM_MB,
) -> str | None:
    """Why the machine is under pressure right now, or None if it is not.

    Non-blocking: ``cpu_percent(interval=None)`` reports load since the last
    sample and returns immediately, so this is safe to call from the event loop
    as well as from a worker thread.

    RAM is checked alongside CPU because they fail differently. Running hot on
    CPU makes the machine slow; running out of memory makes it stop.

    Every caller reaches psutil through here, so this is where the sampling is
    serialised: see ``_SAMPLE_LOCK`` above for why the lock has to be process
    wide rather than owned by any one caller.

    Degrades to "no pressure" when psutil is missing, because a missing
    optional dependency must never silently disable reindexing.
    """
    try:
        import psutil
    except ImportError:
        return None

    # A ceiling of 100 or more cannot be exceeded in any useful sense, so treat
    # it as "CPU throttling off" and skip the sample rather than comparing
    # against a number nothing can reach. Skipping also drops psutil's cost on
    # the hot path, which is the whole point of turning it off.
    cpu_check_on = max_percent < 100

    with _SAMPLE_LOCK:
        cpu = psutil.cpu_percent(interval=None) if cpu_check_on else 0.0
        free_mb = psutil.virtual_memory().available / (1024 * 1024)

    pressure = []
    if cpu_check_on and cpu >= max_percent:
        pressure.append(f"CPU {cpu:.0f}% (limit {max_percent:.0f}%)")
    if free_mb < min_free_ram_mb:
        pressure.append(f"free RAM {free_mb:.0f} MB (need {min_free_ram_mb:.0f} MB)")
    return ", ".join(pressure) or None


class PressureCheckpoint:
    """An interval-throttled pressure probe for a long-running loop.

    Call :meth:`pressure` as often as is convenient; it only really samples once
    per ``interval_s`` and returns None the rest of the time.

    Sampled on a wall clock interval rather than every N files on purpose. Per
    file cost is nowhere near uniform (4.65s measured on one project's average
    file, milliseconds for a small one), so "every N files" gives an
    unpredictable reaction time, while an interval bounds it directly. It also
    fixes the probe's own cost at one psutil sample per interval and keeps
    successive samples far above the 0.1s minimum psutil documents for an
    accurate reading.

    The lock this class holds guards ``_next_sample_at`` and nothing else,
    which is all it can usefully guard: that field is this checkpoint's own
    state. Serialising the psutil call is not this class's job, because
    psutil's bookkeeping is shared by every checkpoint and by
    ``wait_for_system_headroom`` too; that happens in :func:`sample_pressure`,
    which all of them go through.
    """

    def __init__(
        self,
        interval_s: float = INDEX_PRESSURE_CHECK_S,
        max_percent: float = CPU_MAX_PERCENT,
        min_free_ram_mb: float = MIN_FREE_RAM_MB,
    ) -> None:
        self._interval_s = interval_s
        self._max_percent = max_percent
        self._min_free_ram_mb = min_free_ram_mb
        self._lock = threading.Lock()
        # First real sample is one interval away: the work that just started
        # has to run long enough to be worth interrupting, and the sample needs
        # a baseline to diff against.
        self._next_sample_at = time.monotonic() + interval_s
        prime_cpu_sampling()

    def pressure(self) -> str | None:
        now = time.monotonic()
        with self._lock:
            if now < self._next_sample_at:
                return None
            self._next_sample_at = now + self._interval_s
        # Released before sampling on purpose. Holding this one across the
        # psutil call would serialise nothing extra (a second checkpoint has a
        # different lock) while pinning this instance's interval bookkeeping
        # for the duration. The sampling takes the process wide _SAMPLE_LOCK
        # inside sample_pressure() instead.
        return sample_pressure(self._max_percent, self._min_free_ram_mb)
