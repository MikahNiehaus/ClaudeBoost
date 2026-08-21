"""The self-heal cooldown stamp must prove it landed, and must never become a
permanent refusal to self heal.

Originally written by bad-cop to prove the defect: ``_record_self_heal_attempt``
wrote the stamp and then called ``stamp.stat()``, discarding the result. That
checks existence, not durability. Against a stale pre-existing stamp and a write
that silently no-ops (a lazy network write, a synced folder, an antivirus
intercept: returns without raising, commits nothing), it returned True while the
cooldown window was never re-armed, defeating the fail-closed behaviour in
exactly the fault class it exists for.

Inverted here to assert the corrected contract, keeping the same attack. Plus
the other half of the same surface: a corrupt stamp must not raise out of the
hook (that breaks the user's prompt) and must not turn a 15 minute cooldown into
a permanent one.
"""
import importlib.util
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

CLEAN_RAG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLEAN_RAG))
sys.path.insert(0, str(CLEAN_RAG / "hooks"))
sys.path.insert(0, str(CLEAN_RAG / "cli"))


@pytest.fixture()
def rag_enforce():
    path = str(CLEAN_RAG / "hooks" / "rag-enforce.py")
    spec = importlib.util.spec_from_file_location("rag_enforce_durability", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def state(tmp_path):
    d = tmp_path / "state"
    d.mkdir()
    return d


def test_record_reports_failure_when_the_write_never_lands(tmp_path, state, rag_enforce, monkeypatch):
    """bad-cop's original attack: a stale stamp plus a write that returns
    success without touching the file."""
    stamp = state / rag_enforce._SELF_HEAL_STAMP_NAME
    stale_mtime = time.time() - 20 * 60
    stamp.write_text("stale", encoding="utf-8")
    os.utime(stamp, (stale_mtime, stale_mtime))

    real_write_text = Path.write_text

    def noop_write_text(self, *a, **kw):
        if self.name == rag_enforce._SELF_HEAL_STAMP_NAME:
            return len(a[0]) if a else 0
        return real_write_text(self, *a, **kw)

    monkeypatch.setattr(Path, "write_text", noop_write_text)
    persisted = rag_enforce._record_self_heal_attempt(tmp_path)
    monkeypatch.undo()

    assert abs(stamp.stat().st_mtime - stale_mtime) < 1.0, (
        "sanity: the no-op write must really not have touched the file"
    )
    assert persisted is False, (
        "the write left the stale stamp in place, so the cooldown was never "
        "re-armed; reporting success here is what lets an unthrottleable "
        "restart storm through"
    )


def test_a_failed_write_stops_the_restart(tmp_path, state, rag_enforce, monkeypatch):
    """The consequence that actually matters. Returning False is only useful if
    _trigger_self_heal acts on it, so drive the real entry point and assert no
    subprocess is launched."""
    stamp = state / rag_enforce._SELF_HEAL_STAMP_NAME
    stamp.write_text("stale", encoding="utf-8")
    os.utime(stamp, (time.time() - 20 * 60,) * 2)

    real_write_text = Path.write_text

    def noop_write_text(self, *a, **kw):
        if self.name == rag_enforce._SELF_HEAL_STAMP_NAME:
            return len(a[0]) if a else 0
        return real_write_text(self, *a, **kw)

    monkeypatch.setattr(rag_enforce, "_clean_rag_home", lambda: tmp_path)
    monkeypatch.setattr(Path, "write_text", noop_write_text)

    with patch.object(rag_enforce.subprocess, "Popen") as popen:
        rag_enforce._trigger_self_heal("8613")

    popen.assert_not_called()


def test_a_write_that_lands_really_arms_the_cooldown(tmp_path, state, rag_enforce):
    """The other side of the same contract: True must mean the next call is
    genuinely throttled, otherwise the fix is just a stricter way to say no."""
    assert rag_enforce._record_self_heal_attempt(tmp_path) is True

    reason = rag_enforce._self_heal_suppressed(tmp_path)
    assert reason is not None and "cooling down" in reason, reason


@pytest.mark.parametrize(
    "body",
    ["", "   ", "stale", "not-a-timestamp", "\x00\x00", "1.2.3"],
    ids=["empty", "whitespace", "word", "text", "nulls", "malformed_float"],
)
def test_a_corrupt_stamp_is_no_cooldown_not_a_permanent_one(tmp_path, state, rag_enforce, body):
    """A damaged stamp says nothing about when the last restart happened.
    Reading it as an active cooldown would refuse self healing forever, which is
    a worse outage than the 15 minutes it is meant to enforce. It must also not
    raise: this runs inside a UserPromptSubmit hook, and an exception there
    breaks the user's prompt."""
    (state / rag_enforce._SELF_HEAL_STAMP_NAME).write_text(body, encoding="utf-8")

    assert rag_enforce._self_heal_suppressed(tmp_path) is None

    # And it self repairs: the next attempt overwrites it with a real value.
    assert rag_enforce._record_self_heal_attempt(tmp_path) is True
    assert "cooling down" in rag_enforce._self_heal_suppressed(tmp_path)


def test_a_stamp_dated_in_the_future_is_not_an_infinite_cooldown(tmp_path, state, rag_enforce):
    """Clock skew or a restored backup leaves a stamp ahead of now. Naive
    subtraction gives a negative age, which is below every cooldown threshold
    forever."""
    future = time.time() + 365 * 24 * 3600
    (state / rag_enforce._SELF_HEAL_STAMP_NAME).write_text(str(future), encoding="utf-8")

    assert rag_enforce._self_heal_suppressed(tmp_path) is None


def test_an_expired_cooldown_lets_the_next_attempt_through(tmp_path, state, rag_enforce):
    """The throttle has to expire, or the first failure disables self healing
    for the life of the checkout."""
    expired = time.time() - rag_enforce._SELF_HEAL_COOLDOWN_S - 60
    (state / rag_enforce._SELF_HEAL_STAMP_NAME).write_text(str(expired), encoding="utf-8")

    assert rag_enforce._self_heal_suppressed(tmp_path) is None


def test_both_markers_use_the_same_durability_check(rag_enforce):
    """The two copies of "write and prove it landed" already drifted once, which
    is how the stat()-only version survived. Pin them to one implementation."""
    import server.durable_write as durable
    import server_ctl

    assert rag_enforce._load_write_durably() is durable.write_durably
    assert server_ctl._load_write_durably() is durable.write_durably
    assert durable.write_durably.__module__ == "server.durable_write"
    assert server_ctl.STOP_MARKER_NAME == rag_enforce._STOP_MARKER_NAME


def test_write_durably_rejects_a_write_that_reads_back_wrong(tmp_path):
    from server.durable_write import write_durably

    target = tmp_path / "marker"
    target.write_text("old", encoding="utf-8")

    real_write_text = Path.write_text

    def noop_write_text(self, *a, **kw):
        if self.name == "marker":
            return len(a[0]) if a else 0
        return real_write_text(self, *a, **kw)

    with patch.object(Path, "write_text", noop_write_text):
        with pytest.raises(OSError):
            write_durably(target, "new")

    assert target.read_text(encoding="utf-8") == "old"


def test_mark_stopped_by_user_fails_on_a_write_that_never_lands(tmp_path):
    """server_ctl's half of the shared check, driven through its real entry
    point: a stop that was not recorded must report failure, or the next prompt
    resurrects a server the user deliberately killed."""
    import server_ctl

    state = tmp_path / "state"
    state.mkdir()
    (state / server_ctl.STOP_MARKER_NAME).write_text("old", encoding="utf-8")

    real_write_text = Path.write_text

    def noop_write_text(self, *a, **kw):
        if self.name == server_ctl.STOP_MARKER_NAME:
            return len(a[0]) if a else 0
        return real_write_text(self, *a, **kw)

    with patch.object(Path, "write_text", noop_write_text):
        assert server_ctl._mark_stopped_by_user(state) is False

    assert server_ctl._mark_stopped_by_user(state) is True


def test_stop_on_a_partial_install_says_so_and_exits_nonzero(tmp_path):
    """A half installed clean-rag must not turn stop into a traceback.

    Both siblings load server.durable_write through CLEAN_RAG_HOME, and both
    have to survive it not being there: rag-enforce.py returns None and logs,
    so server_ctl has to degrade the same way rather than raising out of the
    middle of the command. It matters most in exactly this case, because a
    stop that reports nothing wrong is a stop the next prompt undoes.

    Run in a subprocess against a copied tree, since the real clean-rag root is
    already on this process's sys.path and would satisfy the import anyway.
    """
    import shutil
    import subprocess

    home = tmp_path / "clean-rag"
    (home / "cli").mkdir(parents=True)
    (home / "server").mkdir()
    (home / "state").mkdir()
    shutil.copy2(CLEAN_RAG / "cli" / "server_ctl.py", home / "cli" / "server_ctl.py")
    # A partial install: server.config arrived, server.durable_write did not.
    (home / "server" / "config.py").write_text(
        "from pathlib import Path\n"
        f"STATE_DIR = Path(r'{home / 'state'}')\n"
        "STANDALONE_PORT = 8613\n",
        encoding="utf-8",
    )

    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    proc = subprocess.run(
        [sys.executable, str(home / "cli" / "server_ctl.py"), "stop"],
        capture_output=True, text=True, env=env, timeout=60,
    )

    assert proc.returncode == 1, (
        f"stop must report the unrecorded stop. rc={proc.returncode}\n"
        f"stdout={proc.stdout}\nstderr={proc.stderr}"
    )
    assert "Traceback" not in proc.stderr, proc.stderr
    assert "server.durable_write" in proc.stderr
    assert "could not record the stop" in proc.stderr
    assert "by hand" in proc.stderr, "the message has to say how to keep the server down"
    assert not (home / "state" / "server-stopped-by-user").exists()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
