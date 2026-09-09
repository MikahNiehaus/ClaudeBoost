"""Concurrent hook processes must not corrupt the research record or the audit chain.

CLAUDE.md allows up to three agents in parallel, and every one of them fires
the same PostToolUse hooks, so several separate OS processes read, modify and
write these same two files at once. Two failures used to follow, and they are
different bugs with different fixes:

  * turn-<hash>.json was written with Path.write_text, which is not atomic. Two
    interleaved writes of different lengths left a stray trailing brace and the
    file stopped being valid JSON at all.
  * research-audit.jsonl is hash chained. Two appends racing on the tail both
    read the same prev_hash and fork the chain, and a forked chain is
    indistinguishable from someone having tampered with it, which defeats the
    single property that file exists to provide.

Real processes, not threads: the GIL would hide the whole class, and these
hooks are separate processes in production.
"""

import json
import multiprocessing as mp
import os
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1] / "hooks"

SESSION = "concurrency-fixture"
WORKERS = 8
STAMPS_EACH = 20
AUDIT_ENTRIES_EACH = 25


def _stamp_worker(home: str) -> None:
    """One hook process stamping the turn record, over and over."""
    import os
    os.environ["CLEAN_RAG_HOME"] = home
    sys.path.insert(0, str(HOOKS))
    import research_state

    for _ in range(STAMPS_EACH):
        research_state.record_agent(SESSION, "swiper", "COVERS: a.py\nVERDICT: ok")


def _audit_worker(args) -> None:
    """One hook process appending to the audit chain, over and over."""
    import os
    home, index = args
    os.environ["CLEAN_RAG_HOME"] = home
    sys.path.insert(0, str(HOOKS))
    import research_audit

    for i in range(AUDIT_ENTRIES_EACH):
        research_audit.append(f"f{index}-{i}.py", SESSION, True, "covered", "swiper")


def _fan_out(target, args_list):
    ctx = mp.get_context("spawn")
    procs = [ctx.Process(target=target, args=(a,)) for a in args_list]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=180)
    assert all(p.exitcode == 0 for p in procs), [p.exitcode for p in procs]


@pytest.fixture
def clean_rag_home(tmp_path, monkeypatch):
    home = tmp_path / "clean-rag"
    (home / "state" / "research").mkdir(parents=True)
    monkeypatch.setenv("CLEAN_RAG_HOME", str(home))
    monkeypatch.syspath_prepend(str(HOOKS))
    return home


def test_concurrent_stamps_leave_the_record_valid_and_complete(clean_rag_home):
    import research_state

    _fan_out(_stamp_worker, [str(clean_rag_home)] * WORKERS)

    path = research_state._record_path(SESSION)
    raw = path.read_text(encoding="utf-8")
    record = json.loads(raw)  # a torn write fails right here

    assert len(record["stamps"]) == WORKERS * STAMPS_EACH, (
        f"{WORKERS * STAMPS_EACH - len(record['stamps'])} stamps were lost. A "
        "dropped stamp reads back as research never having covered the file."
    )


def test_concurrent_appends_leave_the_audit_chain_intact(clean_rag_home):
    import research_audit

    _fan_out(_audit_worker, [(str(clean_rag_home), i) for i in range(WORKERS)])

    result = research_audit.verify()
    assert result["entries"] == WORKERS * AUDIT_ENTRIES_EACH, result
    assert result["chain_ok"], result["breaks"][:3]


def test_a_torn_write_cannot_be_observed_by_a_reader(clean_rag_home):
    """The record is swapped into place, never written in pieces.

    Distinct from the lock: the lock keeps two writers apart, and this keeps a
    reader (the gate, which takes no lock) from ever seeing a partial file.
    """
    import research_state

    path = clean_rag_home / "state" / "research" / "atomic-probe.json"
    research_state.write_json_atomic(path, {"stamps": [{"agent": "swiper"}]})

    big = {"stamps": [{"agent": "swiper", "covers": [f"f{i}.py"]} for i in range(500)]}
    research_state.write_json_atomic(path, big)

    assert json.loads(path.read_text(encoding="utf-8")) == big
    leftovers = [p.name for p in path.parent.iterdir() if p.name.endswith(".tmp")]
    assert not leftovers, f"temp files left behind: {leftovers}"


def test_the_lock_is_released_even_when_the_body_raises(clean_rag_home):
    """A hook that dies holding the lock must not wedge the next one.

    write_lock fails open after its timeout, so a leaked lock would degrade to
    no lock rather than hang. That makes a leak silent, which is why it is
    pinned here rather than left to show up as a slow hook.
    """
    import research_state

    path = clean_rag_home / "state" / "research" / "lock-probe.json"
    with pytest.raises(ValueError):
        with research_state.write_lock(path):
            raise ValueError("boom")

    assert not path.with_name(path.name + ".lock").exists()
    with research_state.write_lock(path) as acquired:
        assert acquired is True


def test_a_stamp_clobbered_by_an_unlocked_write_is_written_again(clean_rag_home, monkeypatch):
    """The lock is the fast path; this is what makes the result correct anyway.

    write_lock fails open by design, so a caller can write without exclusion and
    have its stamp overwritten by whoever wrote last. append_stamp reads back
    after an unlocked write and starts over when its own stamp is missing. The
    clobber is simulated by having the first write land a record that does not
    contain the stamp, which is exactly what a competing writer leaves behind.
    """
    import research_state

    path = clean_rag_home / "state" / "research" / "clobber-probe.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    # A live lock nobody will release, so every attempt takes the fail open path.
    path.with_name(path.name + ".lock").write_bytes(b"1 0.0")
    monkeypatch.setattr(research_state, "LOCK_TIMEOUT_S", 0.0)

    real_write = research_state.write_json_atomic
    calls = []

    def clobber_the_first_write(target, record):
        calls.append(record)
        real_write(target, {"stamps": []} if len(calls) == 1 else record)

    monkeypatch.setattr(research_state, "write_json_atomic", clobber_the_first_write)

    stamp = {"agent": "swiper", "at": 1.0, "covers": ["a.py"]}
    assert research_state.append_stamp(path, stamp, {"stamps": []}) is True
    assert len(calls) == 2, "the clobbered write was never retried"
    assert json.loads(path.read_text(encoding="utf-8"))["stamps"] == [stamp]


def test_a_lock_left_behind_by_a_dead_holder_is_cleared(clean_rag_home, monkeypatch):
    """A hook killed mid write must not park every later hook behind its lock.

    Staleness is decided on the lock file's age, never on os.kill(pid, 0): that
    POSIX liveness idiom terminates the target on Windows rather than probing
    it (python/cpython#70538), which server/indexing.py records having hit.
    """
    import research_state

    path = clean_rag_home / "state" / "research" / "stale-probe.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    lock_path.write_bytes(b"999999 0.0")

    monkeypatch.setattr(research_state, "LOCK_STALE_S", 0.0)
    with research_state.write_lock(path, timeout=0.05) as acquired:
        assert acquired is True, "a dead holder's lock was never cleared"
    assert not lock_path.exists()


def test_an_abandoned_lock_is_cleared_without_waiting_out_the_timeout(clean_rag_home):
    """A leftover sidecar must cost syscalls, not the whole timeout.

    state/research still contains zero byte .lock files left by the previous
    implementation, some of them weeks old. If staleness were only checked once
    the wait expired, the next hook to touch one of those sessions would stall
    for the full timeout before clearing it, on a lock nothing has held since
    July.
    """
    import time as _time

    import research_state

    path = clean_rag_home / "state" / "research" / "abandoned-probe.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    lock_path.write_bytes(b"")
    old = _time.time() - 60 * 60 * 24 * 30
    os.utime(lock_path, (old, old))

    started = _time.monotonic()
    with research_state.write_lock(path, timeout=10.0) as acquired:
        assert acquired is True
    elapsed = _time.monotonic() - started
    assert elapsed < 1.0, f"took {elapsed:.2f}s to clear a month old lock"


def test_a_lock_held_by_a_live_holder_fails_open_rather_than_hanging(clean_rag_home):
    """The direction this guard fails in, pinned.

    Recording is not worth blocking an edit for, so a lock that cannot be
    claimed lets the body run anyway. Pair that with the atomic write above and
    the worst case is a lost stamp, which reads back as "not covered" and makes
    the gate nudge. Turning this into a wait forever, or into a refusal, would
    be a different product.
    """
    import research_state

    path = clean_rag_home / "state" / "research" / "busy-probe.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    lock_path.write_bytes(b"1 0.0")  # young, so never treated as stale

    with research_state.write_lock(path, timeout=0.05) as acquired:
        assert acquired is False
    assert lock_path.exists(), "the live holder's lock was stolen"
