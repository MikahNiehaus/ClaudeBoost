"""Shared state for the research gate.

The gate answers one question: was the file I'm about to edit actually covered by
research this turn?

Note the shape of that question. It is not "did some agent run", which is what
this used to ask, and the difference matters. Under the old rule one triage run
at the top of a turn unlocked every edit that followed: in practice a single
agent stamped the record and then ten unrelated code edits sailed through
unresearched. The gate had stopped complaining, so nobody noticed.

That failure is task drift, not omission. The model did research. It then edited
something else. A boolean cannot catch that, because its memory is "an agent ran"
rather than "an agent looked at this file".

So a stamp carries a scope: the files its research covered. The gate checks
membership. One research run covers a coherent multi file change, and an edit to
a file nobody researched still blocks. That's the guarantee of per edit gating at
roughly the cost of per turn gating.

Per edit gating (one agent spawn per file) was considered and rejected. There is
no evidence that re-researching ten times for one coherent refactor beats
researching once, and this codebase already learned what blind forced retrieval
costs when it deleted the topic knowledge base.

The scope-then-check pattern is not new here. scripts/consult-gate.py already
does it for the approval gate, and file_in_spec below is deliberately the same
matching logic.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import random
import re
import sys
import tempfile
import time
from pathlib import Path

# Agents whose completion counts as research having happened. Both run the full
# pass every time: researcher maps the codebase and grounds the change in real
# engineering standards; swiper checks existence and finds what to clone. Either
# stamps the file scope it covered. The gate checks per-file membership in any
# stamp's scope, not whether a specific agent ran. /ps is the human's exit for
# a turn they already know is trivial — skips both research and the verifier gate.
RESEARCH_AGENTS = {"swiper", "researcher"}

# A record older than this is treated as gone, covering an abandoned turn whose
# edits arrive much later without a fresh prompt.
TURN_MAX_AGE_S = 3600


def clean_rag_home() -> Path:
    env = os.environ.get("CLEAN_RAG_HOME")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent


# How long to wait for another hook to finish its critical section before
# giving up and proceeding unlocked.
#
# Sized from measurement, not taste. In production three hooks contend at most,
# each takes the lock once and exits, and the wait is under a millisecond. The
# number that matters is the pathological case: 8 processes taking it back to
# back, 160 times, on a record that grows with every stamp. There the longest
# single hold measured 0.56s and the longest wait 2.9s, so 5s was close enough
# to the tail that a loaded machine pushed waiters over it and they wrote
# unlocked. 15s is five times the measured tail and still well inside
# LOCK_STALE_S, so a waiter that gives up has genuinely been behind a live
# holder rather than a dead one.
LOCK_TIMEOUT_S = 15.0

# A lock file older than this belonged to a holder that is gone: the longest
# hold measured under the load above was 0.56s, so 60s is two orders of
# magnitude past anything a working holder does, and it stays above
# LOCK_TIMEOUT_S so a waiter never breaks a lock it merely got tired of.
# Staleness is decided on age, never on a PID liveness probe, because the POSIX
# `os.kill(pid, 0)` idiom does not ask whether a process is alive on Windows,
# it terminates it (python/cpython#70538). server/indexing.py hit this too and
# documents it.
LOCK_STALE_S = 60.0

_LOCK_POLL_S = 0.005

# How long a release keeps retrying its unlink before giving up and letting the
# stale window handle it.
_RELEASE_TIMEOUT_S = 0.5

# After releasing, this process waits this long before claiming the same path
# again, so a waiter gets the gap. Without it a caller that releases and
# immediately re-claims barges past everyone polling, and the tail measured on
# 8 processes taking the lock back to back was 6.7s against a median of 0.4ms.
# A hook acquires once and exits, so nothing in production pays this.
_HANDOFF_S = 0.02

_last_release: dict[str, float] = {}

# How many times append_stamp re-reads and re-appends after an unlocked write
# found its own stamp missing. Bounded so a pathological writer cannot spin.
_APPEND_ATTEMPTS = 5


def _break_stale_lock(lock_path: Path) -> bool:
    """Clear *lock_path* if it is too old to have a live holder.

    Only removes, never grants: the caller re-runs the same atomic create
    afterwards, so two callers that spot the same dead holder still race for a
    single winner. Taken from server/indexing.py:_break_stale_lock, minus its
    PID liveness probe.

    Everything here goes through ``stat``, and nothing opens the lock file for
    reading, which is load bearing on Windows. ``open()`` there asks for
    FILE_SHARE_READ | FILE_SHARE_WRITE but not FILE_SHARE_DELETE, so a reader
    holding the file open makes the real holder's release ``unlink`` fail. The
    first version of this function read the payload back, and the effect was
    measurable: under 8 way contention the lock file stopped being deleted at
    all, every caller waited out the timeout, and 96 of 160 stamps were lost.
    ``os.stat`` opens with FILE_SHARE_DELETE and gets in nobody's way.
    """
    try:
        mtime = lock_path.stat().st_mtime
    except FileNotFoundError:
        return True  # Released underneath us. Free to retry.
    except OSError:
        return False

    if time.time() - mtime < LOCK_STALE_S:
        return False

    try:
        # Re-stat before unlinking. Between the check above and here the
        # abandoned lock can have been cleared and a live caller can have
        # claimed it for real; deleting that would hand the lock to two callers
        # at once. An unchanged mtime means it is still the same dead claim.
        if lock_path.stat().st_mtime != mtime:
            return False
        lock_path.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        return False
    return True


def _release(lock_path: Path) -> None:
    """Delete the lock file, retrying briefly if something else has it open.

    A release that quietly fails parks every later caller behind the whole
    stale window for no reason, so one failed unlink is not the end of it. The
    usual culprit on Windows is a scanner that opened the file when it was
    closed a moment ago; those handles clear in milliseconds.
    """
    deadline = time.monotonic() + _RELEASE_TIMEOUT_S
    while True:
        try:
            lock_path.unlink(missing_ok=True)
            return
        except OSError as e:
            if time.monotonic() >= deadline:
                print(
                    f"[research-state] could not release {lock_path.name}: "
                    f"{type(e).__name__}: {e}. Later callers will wait "
                    f"{LOCK_STALE_S:.0f}s before clearing it.",
                    file=sys.stderr,
                )
                return
            time.sleep(_LOCK_POLL_S)


def _claim(lock_path: Path, timeout: float) -> bool:
    """Take the lock, or give up and report why.

    Split out of write_lock so the acquire loop, which is where all the
    platform behaviour lives, reads on its own.
    """
    # Hand the lock over before taking it back. See _HANDOFF_S.
    since_release = time.monotonic() - _last_release.get(str(lock_path), 0.0)
    if since_release < _HANDOFF_S:
        time.sleep(_HANDOFF_S - since_release)

    deadline = time.monotonic() + timeout
    first_failure = True
    extended_once = False

    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Nothing to report yet. If the directory really is unusable the claim
        # below fails on the next line and the timeout branch names the reason;
        # logging it twice would just be noise on the ordinary "already there".
        pass

    payload = f"{os.getpid()} {time.time():.3f}".encode("utf-8")

    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except OSError as e:
            # Every failure here is retryable, including PermissionError. On
            # Windows a delete is asynchronous: between the holder's unlink and
            # the name leaving the directory the file is "delete pending", and
            # a CREATE_NEW against it comes back as access denied rather than
            # already-exists. Measured at 1 in ~150 claims under 8 way
            # contention, so treating it as fatal would drop the lock exactly
            # when contention is highest, which is the only time it matters.
            expired = time.monotonic() >= deadline
            if first_failure or expired:
                # Ask whether the holder is dead on the first failed claim, and
                # again once the wait runs out, but not on every poll: the
                # answer is almost always no and the check costs two more
                # syscalls. Asking on the first failure is what keeps an
                # abandoned sidecar cheap, and there are real ones on disk.
                # state/research still holds lock files left by the previous
                # implementation, zero bytes and weeks old, and without the
                # early check the next hook to touch one of those sessions
                # would stall for the whole timeout before clearing it.
                cleared = _break_stale_lock(lock_path)
                if expired and not cleared:
                    print(
                        f"[research-state] proceeding without the lock on "
                        f"{lock_path.name}: still held after {timeout:.0f}s "
                        f"({type(e).__name__})",
                        file=sys.stderr,
                    )
                    return False
                if expired and not extended_once:
                    # The wait was spent behind a dead holder, so it bought
                    # nothing. Give the claim one more full window rather than
                    # writing unlocked over a lock that no longer exists.
                    extended_once = True
                    deadline = time.monotonic() + timeout
            first_failure = False
            # A flat poll with jitter, deliberately not exponential backoff.
            # The critical section here is milliseconds, so growing the wait
            # only makes a waiter sleep through the gaps: measured on 8
            # processes, a backoff capped at 8x had a worst wait of 6.7s where
            # the flat poll had 2.3s. The jitter is there to stop several
            # waiters waking in lockstep. random, not secrets: this picks a
            # sleep length, it guards nothing.
            time.sleep(_LOCK_POLL_S * (0.5 + random.random()))
            continue

        try:
            # os.write, not fdopen: no newline translation, so the bytes on
            # disk are the same on Windows and POSIX. The payload is
            # diagnostic only, so a failed write still leaves a valid claim:
            # exclusion comes from the file existing, not from its contents.
            with contextlib.suppress(OSError):
                os.write(fd, payload)
        finally:
            with contextlib.suppress(OSError):
                os.close(fd)
        return True


@contextlib.contextmanager
def write_lock(path: Path, timeout: float = LOCK_TIMEOUT_S):
    """Cross process lock around a read-modify-write of *path*.

    These hooks are separate short lived processes, and CLAUDE.md explicitly
    allows up to 3 agents in parallel, so two of them can finish milliseconds
    apart and both read-modify-write the same file. Without a lock the later
    write drops the earlier stamp, and on the append only audit log both
    appends read the same prev_hash and fork the chain.

    The claim is a single ``os.open(O_CREAT | O_EXCL | O_WRONLY)`` on a sidecar
    file, which is one kernel operation with no check-then-write gap and
    behaves the same on POSIX and on Windows (CPython maps it to ``CreateFile``
    with ``CREATE_NEW``). That is the same technique, and the same reasoning
    about stdlib over filelock/portalocker, as server/indexing.py's
    acquire_index_lock; the differences are that this one is per path and waits
    for the holder instead of reporting busy, because a hook's critical section
    is milliseconds rather than a multi minute reindex.

    This used to import ``rag_server.core.locking`` from a sibling
    ``mcp-rag-server/`` checkout that no longer exists anywhere, so every call
    fell into the except branch and returned ``contextlib.nullcontext()``. The
    lock was dead code and never engaged once.

    Fails open, deliberately and unchanged in direction: if the lock cannot be
    claimed within *timeout*, the body still runs, so a wedged lock can never
    stop a hook from recording. Callers pair this with an atomic write, which
    keeps the worst case at a lost update rather than a torn file.
    """
    lock_path = path.with_name(path.name + ".lock")
    if not _claim(lock_path, timeout):
        yield False
        return

    try:
        yield True
    finally:
        _release(lock_path)
        _last_release[str(lock_path)] = time.monotonic()


def write_json_atomic(path: Path, record: dict) -> None:
    """Serialize *record* to *path* so no reader can ever see a half written file.

    Write to a temp file in the same directory, then ``os.replace``, which is
    atomic on POSIX and, since Python 3.3, on Windows too (it maps to
    ``MoveFileEx`` with ``MOVEFILE_REPLACE_EXISTING``). This is the separate
    half of the concurrency fix: the lock stops a lost update between two
    writers, and this stops a torn file, which is what actually left the record
    as invalid JSON with a stray trailing brace when two ``write_text`` calls of
    different lengths interleaved.

    Raises OSError on failure, the same as ``Path.write_text`` did, so callers
    keep the error handling they already have.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(record, indent=2)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(body)
        os.replace(tmp_name, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


def _state_dir() -> Path:
    d = clean_rag_home() / "state" / "research"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _session_key(session_id: object) -> str:
    """Hash a session id into a filename fragment, whatever arrives.

    Two shapes reach here from a hook payload and neither is a string. A field
    present with the wrong type (`{"session_id": 12}`) raises AttributeError on
    .encode(), and a lone surrogate raises UnicodeEncodeError. Both read as
    absent instead, which is how rag-enforce._str_field already treats a
    mistyped field, so two hooks on the same payload cannot disagree about
    which flag file they are using.
    """
    if not isinstance(session_id, str):
        session_id = ""
    raw = (session_id or "no-session").encode("utf-8", "replace")
    return hashlib.sha256(raw).hexdigest()[:16]


def _record_path(session_id: str) -> Path:
    # Session ids come from Claude Code and could contain anything, so hash
    # rather than trusting one as a filename.
    return _state_dir() / f"turn-{_session_key(session_id)}.json"


def _load_record(path: Path) -> dict | None:
    """Read the record back, or None if there isn't a usable one.

    None covers a missing file, an unreadable one, and a file whose JSON parses
    to something other than an object, which the callers used to let through
    and then crash on at the first ``.setdefault``.
    """
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return record if isinstance(record, dict) else None


def _normalize(path: str) -> str:
    return path.replace("\\", "/").lower()


def file_in_scope(file_path: str, covered: list[str]) -> bool:
    """Is this file within what the research actually covered?

    Same matching as consult-gate.py's file_in_spec (scripts/consult-gate.py:51),
    plus glob support so research can declare a module rather than listing every
    file in it.

    Entries may be:
      - an absolute or relative path: clean-rag/server/app.py
      - a glob: clean-rag/hooks/*.py, or src/auth/**
    """
    norm = _normalize(file_path)

    for entry in covered:
        entry = _normalize(entry.strip().strip("/\\"))
        if not entry:
            continue

        if "*" in entry:
            # ** crosses directory separators, * does not.
            pattern = re.escape(entry).replace(r"\*\*", "\x00").replace(r"\*", "[^/]*")
            pattern = pattern.replace("\x00", ".*")
            if re.search(pattern + "$", norm):
                return True
            continue

        if norm == entry or norm.endswith("/" + entry):
            return True

    return False


def extract_covered_files(text: str, prefix: str = "COVERS:") -> list[str]:
    """Pull the file scope out of an agent's report.

    An agent declares scope with a line like:
        COVERS: clean-rag/server/app.py, clean-rag/hooks/*.py

    `prefix` lets a sibling gate reuse this same parser for its own marker line
    (verifier-gate's stamps use "VERIFIED:") instead of forking the logic.

    If it declares nothing, it covers nothing, and the gate will block. That's
    deliberate. An agent that can't say what it looked at hasn't given the gate
    anything to check, and silently treating that as "covers everything" is
    exactly the blanket clearance this design exists to remove.

    Claude Code's Agent tool appends an "agentId: ... (use SendMessage with
    to: ..., summary: ...)" wrapper suffix to a spawned agent's final report
    text, and it can land glued onto this exact line with no newline in
    between. Left alone, that suffix gets swept into the file list and
    corrupts the last entry, so it's cut off before the comma split.
    """
    if not text:
        return []

    marker = prefix.upper()
    for line in text.splitlines():
        stripped = line.strip().lstrip("*# ").strip()
        if stripped.upper().startswith(marker):
            raw = stripped.split(":", 1)[1]
            raw = raw.split("agentId:", 1)[0]
            return [p.strip().strip("`") for p in raw.split(",") if p.strip()]

    return []


def open_turn(session_id: str, prompt: str, quick: bool = False) -> None:
    """Called on UserPromptSubmit. Updates turn metadata; preserves existing stamps.

    Research coverage earned this session persists across messages until it expires
    (TURN_MAX_AGE_S) or new research lands. This is the prerequisite for the research
    gate being a hard block: under the old reset-on-every-message design, coverage
    from swiper was wiped by the next follow-up message before anything was edited,
    causing constant false blocks. Preserving stamps fixes that. Coverage now expires
    only via the TTL or when new research runs (which adds its own stamps on top).

    `quick` marks a /ps turn: the human's explicit "skip the ceremony". Set
    deterministically from the raw prompt text, never by the model.
    """
    path = _record_path(session_id)
    try:
        with write_lock(path):
            record = _load_record(path)
            if record is None:
                record = {"session_id": session_id, "started_at": time.time(), "stamps": []}

            # Update metadata but preserve existing stamps. Coverage persists across
            # follow-up messages; it expires only via TTL or when new research runs.
            record["session_id"] = session_id
            record["started_at"] = time.time()
            record["prompt_preview"] = (prompt or "")[:200]
            record["quick"] = bool(quick)
            record.setdefault("stamps", [])

            write_json_atomic(path, record)
    except OSError:
        # A gate that can't write its record blocks every edit. Staying quiet is
        # the lesser evil; the pre edit hook explains a missing record itself.
        pass


def is_quick_turn(session_id: str) -> bool:
    """Did this turn start with /ps? Then the gates and the verifier stand down.

    Fail closed: a missing, malformed, or stale record returns False, so a broken
    record means "still require research and verification", never a silent skip. The
    age guard (same TURN_MAX_AGE_S the research check uses) also stops a quick flag
    leaking into a later turn if a following open_turn write failed and left the old
    record in place.
    """
    path = _record_path(session_id)
    if not path.exists():
        return False
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(record, dict) or not record.get("quick", False):
            return False
        return (time.time() - record.get("started_at", 0)) <= TURN_MAX_AGE_S
    except Exception:  # noqa: BLE001 -- any failure means "not quick", enforce the gate
        return False


def append_stamp(path: Path, stamp: dict, defaults: dict) -> bool:
    """Add *stamp* to the record at *path*, and confirm it is actually there.

    The lock is the fast path, not the guarantee. write_lock fails open on
    purpose, so under enough contention a caller writes without exclusion and
    its stamp can be clobbered by whoever wrote last. That is a lost update,
    and a lost update reads back as research or review never having happened,
    which is the one thing these records exist to tell apart.

    So an unlocked write is verified and retried, the ordinary optimistic
    concurrency loop: read, modify, write, confirm your own change survived,
    start over if it did not. A locked write is trusted and returns straight
    away, which is every write in practice. Measured on 8 processes appending
    160 stamps to one record, the verify path ran a handful of times and the
    count came out exact, where before it lost 96.

    Returns True when the stamp is on disk.
    """
    for _ in range(_APPEND_ATTEMPTS):
        with write_lock(path) as locked:
            record = _load_record(path)
            if record is None:
                record = dict(defaults)

            stamps = record.get("stamps")
            if not isinstance(stamps, list):
                stamps = []
            stamps.append(stamp)
            record["stamps"] = stamps

            try:
                write_json_atomic(path, record)
            except OSError as e:
                print(
                    f"[research-state] could not write {path.name}: "
                    f"{type(e).__name__}: {e}",
                    file=sys.stderr,
                )
                return False

            if locked:
                return True

        # Unlocked, so another process may have written over us between our
        # read and our write. Read it back outside the lock and look for our
        # own stamp; anything else and we go round again.
        written = _load_record(path)
        if written and any(s == stamp for s in written.get("stamps", [])):
            return True

    print(
        f"[research-state] gave up recording a stamp in {path.name} after "
        f"{_APPEND_ATTEMPTS} attempts; a concurrent writer kept overwriting it",
        file=sys.stderr,
    )
    return False


def record_agent(session_id: str, agent_type: str, report: str = "") -> None:
    """Called on PostToolUse after researcher or swiper finishes."""
    if agent_type not in RESEARCH_AGENTS:
        return

    append_stamp(
        _record_path(session_id),
        {
            "agent": agent_type,
            "at": time.time(),
            "covers": extract_covered_files(report),
            "verdict": _first_verdict_line(report),
        },
        {"session_id": session_id, "started_at": time.time(), "stamps": []},
    )


def _first_verdict_line(text: str) -> str:
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("VERDICT:"):
            return stripped[:200]
    return (text or "")[:200]


def has_any_research_this_turn(session_id: str) -> tuple[bool, str]:
    """Did swiper run at all this turn? For actions with no single file to
    scope against, a destructive package manager command, not an edit to a file.
    Same freshness rule as check_file_researched, just without the per file scope
    check, since "which file does this cover" does not apply to a shell command.
    """
    path = _record_path(session_id)
    if not path.exists():
        return False, "no research agent has run this turn"

    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, "the research record is unreadable"

    stamps = record.get("stamps", [])
    last_activity = max([record.get("started_at", 0)] + [s.get("at", 0) for s in stamps])
    age = time.time() - last_activity
    if age > TURN_MAX_AGE_S:
        return False, f"the research record is stale ({age / 60:.0f} minutes old)"

    if not stamps:
        return False, "no research agent has run this turn"

    return True, f"research ran this turn ({stamps[-1].get('agent')})"


# ---------------------------------------------------------------------------
# Session-scoped /ps persistence.
#
# /ps marks one message's turn record as quick. The next user message opens
# a fresh turn record with quick=False, so the gate blocks again on the very
# next edit. User sends /ps, then the actual task as a separate message. The
# task message gets blocked.
#
# Fix: a session-keyed file with a 10-minute TTL. set_session_quick() is
# called when /ps is detected. rag-enforce.py checks is_session_quick() on
# new turns and carries the flag forward. clear_session_quick() is called by
# research-record.py once real research lands, ending the sticky /ps.
# ---------------------------------------------------------------------------

SESSION_QUICK_MAX_AGE_S = 600  # 10 minutes


def _session_quick_path(session_id: str) -> Path:
    return _state_dir() / f"session-quick-{_session_key(session_id)}.json"


def set_session_quick(session_id: str) -> None:
    path = _session_quick_path(session_id)
    path.write_text(json.dumps({"set_at": time.time()}), encoding="utf-8")


def clear_session_quick(session_id: str) -> None:
    path = _session_quick_path(session_id)
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def is_session_quick(session_id: str) -> bool:
    """True if /ps was issued recently for this session and no research has landed since."""
    path = _session_quick_path(session_id)
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return (time.time() - data.get("set_at", 0)) <= SESSION_QUICK_MAX_AGE_S
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Emit once per session, or again when the content actually changes.
#
# Cloned from the session-quick pair above: same session id hashing, same
# _state_dir, so there is one place that decides how a session keyed file is
# named. The differences are that this one holds many keys in one file and
# stores a fingerprint per key instead of a timestamp.
#
# Why it exists: a hook that printed the same fixed block on every message left
# one permanent copy per firing in the transcript, 325 of them in a measured
# session, 164,012 tokens. Repetition also does not buy what it was meant to
# buy. Liu et al. measured a U shaped recall curve over long contexts, so every
# copy but the newest sits in the worst position, and no study isolates repeat
# count as the lever that improves compliance.
#
# No TTL on purpose. A stale flag is not the failure mode here; losing the rule
# after the context is wiped is. compaction-restore.py calls clear_session_once
# on source=="compact" and source=="clear", so the full text comes back exactly
# when the context that held it went away, whether or not Claude Code issues a
# new session id for a compaction.
# ---------------------------------------------------------------------------


def _session_once_path(session_id: str) -> Path:
    return _state_dir() / f"session-once-{_session_key(session_id)}.json"


def claim_session_once(session_id: str, key: str, fingerprint: str = "") -> bool:
    """True the first time *key* is claimed, and again if *fingerprint* changed.

    Pass an empty fingerprint for content that never varies. Pass a hash of the
    rendered block for content that can vary, such as the search contract that
    names the active workspace: switching workspace changes the fingerprint and
    the block is emitted again, so nothing goes stale silently.

    Fails open. Any unreadable or unwritable state returns True, because a hook
    that cannot record its flag must still say the thing it was going to say.
    """
    try:
        path = _session_once_path(session_id)
    except OSError:
        # mkdir(exist_ok=True) still raises when state/research exists as a
        # file, so there is no flag to read and no lock worth waiting on.
        return True
    with write_lock(path):
        seen = _load_record(path) or {}
        if seen.get(key) == fingerprint:
            return False
        seen[key] = fingerprint
        try:
            write_json_atomic(path, seen)
        except OSError:
            return True
    return True


def clear_session_once(session_id: str) -> None:
    """Forget every once flag, so the next firing emits in full again."""
    path = _session_once_path(session_id)
    with contextlib.suppress(OSError):
        path.unlink(missing_ok=True)


def fingerprint(text: str) -> str:
    """Short stable digest of a rendered block, for the fingerprint argument."""
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16]


def check_file_researched(session_id: str, file_path: str) -> tuple[bool, str]:
    """Was this specific file covered by research this turn?

    Returns (ok, reason). The reason explains a refusal, so the gate can say
    something useful instead of just saying no.
    """
    path = _record_path(session_id)
    if not path.exists():
        return False, "no research agent has run this turn"

    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, "the research record is unreadable"

    stamps = record.get("stamps", [])

    # Freshness keys off the most recent research activity, not the turn open time.
    # A long turn that keeps researching is not stale; only a genuinely abandoned
    # record is (its newest stamp, or its start if nothing stamped, has aged out).
    # Keying staleness to started_at alone bricked every edit in a session that ran
    # past TURN_MAX_AGE_S, even right after a valid research stamp landed for this file.
    last_activity = max([record.get("started_at", 0)] + [s.get("at", 0) for s in stamps])
    age = time.time() - last_activity
    if age > TURN_MAX_AGE_S:
        return False, f"the research record is stale ({age / 60:.0f} minutes old)"

    if not stamps:
        return False, "no research agent has run this turn"

    for stamp in stamps:
        if file_in_scope(file_path, stamp.get("covers", [])):
            return True, f"covered by {stamp.get('agent')}"

    # Research ran, but not on this file. This is the case the old boolean gate
    # waved through, and it's the one that actually bit.
    covered = sorted({c for s in stamps for c in s.get("covers", [])})
    if covered:
        shown = ", ".join(covered[:4]) + (" ..." if len(covered) > 4 else "")
        return False, f"research this turn covered {shown}, not this file"

    agents = ", ".join(s.get("agent", "?") for s in stamps)
    return False, f"{agents} ran but declared no file scope (no COVERS: line)"
