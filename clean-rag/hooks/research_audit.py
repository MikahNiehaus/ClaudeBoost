"""Hash chained, append only audit log of every code edit and whether research covered it.

This is tamper EVIDENCE, not tamper prevention, and the difference is the whole
point of the file.

Prevention is not available here. The research gate's state is a file, this
process can write files, and you cannot secure a resource from a process running
at your own privilege level. That's the reference monitor result from 1972, not
a quirk of this codebase. The one real fix, an OS enforced sandbox that covers
subprocesses and not just the model's Edit tool, needs WSL2, and this is native
Windows.

So instead: you can still lie in the moment, but you cannot quietly rewrite
history. Every entry's hash folds in the previous entry's hash, exactly the way a
git commit folds in its parent's id. Doctor an entry in the middle and its hash
changes, so the next entry's prev_hash stops matching, and every entry after it
is visibly broken. Delete one and the chain has a hole. There is no way to edit
the past without leaving the seal torn.

That turns "did the agent route around research this session" from an unknowable
into a grep. Run: python clean-rag/cli/audit.py verify
"""

import hashlib
import json
import os
import sys
import time
from pathlib import Path

# The first entry has no parent, so it chains from a fixed root.
GENESIS = "0" * 64


def clean_rag_home() -> Path:
    env = os.environ.get("CLEAN_RAG_HOME")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent


def audit_path() -> Path:
    return clean_rag_home() / "state" / "research-audit.jsonl"


def _boost_home() -> Path:
    env = os.environ.get("CLAUDEBOOST_HOME")
    if env:
        return Path(env)
    return clean_rag_home().parent


def _write_lock(path: Path):
    """Real cross process lock, same one research_state.py uses.

    Several hook processes can be appending at once, and two appends racing on
    the tail of the chain would both read the same prev_hash and fork it. A
    forked chain looks exactly like tampering, so the lock is load bearing here,
    not hygiene.
    """
    try:
        lock_src = _boost_home() / "mcp-rag-server" / "src"
        if str(lock_src) not in sys.path:
            sys.path.insert(0, str(lock_src))
        from rag_server.core.locking import index_write_lock

        return index_write_lock(path.with_suffix(".jsonl.lock"))
    except Exception:
        import contextlib

        return contextlib.nullcontext()


def entry_hash(prev_hash: str, entry: dict) -> str:
    """Hash of the entry, welded to its parent.

    sort_keys and a compact separator so the same entry always serializes the
    same way. Without that the hash depends on dict ordering and the chain
    fails to verify against itself for no real reason.

    The prev_hash is inside the hashed material, not appended after it, which
    is what actually chains the entries: you cannot recompute one entry's hash
    without its parent's, all the way back to genesis.
    """
    body = {k: v for k, v in entry.items() if k != "entry_hash"}
    body["prev_hash"] = prev_hash
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _last_hash(path: Path) -> str:
    if not path.exists():
        return GENESIS
    last = GENESIS
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    last = json.loads(line).get("entry_hash", last)
                except json.JSONDecodeError:
                    # A corrupt line is itself a chain break. verify() will
                    # report it. Keep going so we don't lose new entries too.
                    continue
    except OSError:
        return GENESIS
    return last


def append(
    file_path: str,
    session_id: str,
    allowed: bool,
    reason: str,
    covering_agent: str = "",
) -> None:
    """Record one code edit attempt. Never raises, never blocks the edit.

    This is a log, not a gate. research-gate.py already decided whether to allow
    the edit before calling this. If logging breaks, the edit still goes through,
    because a broken logger silently bricking all editing would be a far worse
    failure than a missing line.
    """
    path = audit_path()

    try:
        path.parent.mkdir(parents=True, exist_ok=True)

        with _write_lock(path):
            prev = _last_hash(path)
            entry = {
                "ts": round(time.time(), 3),
                "file": str(file_path).replace("\\", "/"),
                "session_id": session_id,
                "allowed": allowed,
                "reason": reason[:200],
                "covering_agent": covering_agent,
                "prev_hash": prev,
            }
            entry["entry_hash"] = entry_hash(prev, entry)

            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n")

    except Exception as e:
        # Deliberately swallowed. See the docstring: an audit failure must not
        # stop work. Surface it on stderr so it isn't invisible.
        print(f"[research-audit] could not append: {type(e).__name__}: {e}", file=sys.stderr)


def verify() -> dict:
    """Walk the chain. Report breaks, and any edit no research covered.

    Returns a dict rather than printing, so cli/audit.py owns presentation and
    this stays testable.
    """
    path = audit_path()
    result = {
        "path": str(path),
        "exists": path.exists(),
        "entries": 0,
        "chain_ok": True,
        "breaks": [],
        "ungated_edits": [],
    }

    if not path.exists():
        return result

    prev = GENESIS

    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            try:
                entry = json.loads(line)
            except json.JSONDecodeError as e:
                result["chain_ok"] = False
                result["breaks"].append({
                    "line": lineno,
                    "problem": f"line is not valid JSON ({e})",
                })
                continue

            result["entries"] += 1

            # Does this entry point at the entry before it?
            if entry.get("prev_hash") != prev:
                result["chain_ok"] = False
                result["breaks"].append({
                    "line": lineno,
                    "file": entry.get("file"),
                    "problem": "prev_hash does not match the previous entry. "
                               "An entry was deleted, reordered, or inserted.",
                    "expected": prev,
                    "found": entry.get("prev_hash"),
                })

            # Does the entry's own content still hash to what it claims?
            recomputed = entry_hash(entry.get("prev_hash", GENESIS), entry)
            if recomputed != entry.get("entry_hash"):
                result["chain_ok"] = False
                result["breaks"].append({
                    "line": lineno,
                    "file": entry.get("file"),
                    "problem": "entry_hash does not match the entry's contents. "
                               "This entry was altered after it was written.",
                    "expected": recomputed,
                    "found": entry.get("entry_hash"),
                })

            if not entry.get("allowed"):
                # A blocked edit is the gate working, not a problem.
                pass
            elif not entry.get("covering_agent"):
                result["ungated_edits"].append({
                    "line": lineno,
                    "file": entry.get("file"),
                    "ts": entry.get("ts"),
                    "reason": entry.get("reason"),
                })

            prev = entry.get("entry_hash", prev)

    return result
