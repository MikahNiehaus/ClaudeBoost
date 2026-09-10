"""Shared state for the verifier gate.

verifier-gate.py used to count how many times it printed a nudge, not whether
good-cop had actually run. After 2 nudges it gave up for the rest of the
session regardless of whether anything was ever reviewed. This is the real
check that replaces the counter: a stamp, written only when good-cop
actually completes, the same shape research-gate.py already uses for research.

The scope is different from research's, on purpose. swiper's stamp is
per TURN, reset by rag-enforce.py's open_turn() on every UserPromptSubmit,
because the research gate blocks a single edit and a fresh turn should require
fresh research. verifier-gate.py reviews the accumulated uncommitted git diff,
which spans however many turns happened since the last commit, so a stamp here
is scoped to the SESSION, not the turn, and is invalidated per file instead: if
a file's mtime advances past its stamp's timestamp, it was edited again after
being reviewed, and the stamp no longer covers what is on disk now.

Reuses research_state's file_in_scope and extract_covered_files rather than
forking them; the only real difference is the marker line ("VERIFIED:" instead
of "COVERS:") and the mtime based invalidation.
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from research_state import (  # noqa: E402
    append_stamp,
    extract_covered_files,
    file_in_scope,
)

VERIFIER_MARKER = "VERIFIED:"
HANDOFF_MARKER = "HANDOFF:"
# bad-cop's third closing line. Everything it found was Nit severity, so
# good-cop is not spawned: the orchestrator applies the fixes and re-runs
# bad-cop for the stamp. Distinct from HANDOFF: because both leave `covers`
# empty, and without this the gate cannot tell them apart and nudges for an
# Opus fix pass over polish.
NITS_MARKER = "NITS:"

# bad-cop runs in two modes. Mode A reviews a code diff and stamps VERIFIED: or
# HANDOFF:, which is what this gate is built on. Mode B judges a finished /qa
# session's evidence and stamps FULLY VERIFIED: or TEST AGAIN:, neither of which
# names a file and neither of which says anything about a diff.
JUDGE_MODE_MARKER = "MODE: evidence-judge"
JUDGE_STAMPS = ("FULLY VERIFIED:", "TEST AGAIN:")


def _normalize(line: str) -> str:
    """Normalized the way extract_covered_files does, so a stamp still reads as
    one when an agent bolds it or makes it a heading."""
    return line.strip().lstrip("*# ").strip().upper()


def _stamp_lines(text: str):
    """Every normalized line, for the "does this text mention a stamp anywhere"
    question. closing_stamp needs a stricter one and does not use this."""
    for line in (text or "").splitlines():
        yield _normalize(line)


_MARKERS = (VERIFIER_MARKER, HANDOFF_MARKER, NITS_MARKER)


def _marker_of(line: str) -> str:
    for marker in _MARKERS:
        if line.startswith(marker):
            return marker
    return ""


def _blocks(text: str) -> list[list[str]]:
    """Runs of consecutive non-blank normalized lines.

    A block is git's unit for the same problem: git-interpret-trailers finds a
    commit's trailers in "a group of one or more lines ... preceded by one or
    more empty (or whitespace only) lines", not by scanning the whole message.

    Fenced code needs no special case. A stamp inside a fence sits between the
    two delimiter lines, so it is never its block's first or last line and
    closing_stamp already ignores it.
    """
    blocks, current = [], []
    for raw in (text or "").splitlines():
        line = _normalize(raw)
        if line:
            current.append(line)
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def is_evidence_judge_pass(spawn_prompt: str, report: str) -> bool:
    """Was this completion bad-cop in Mode B (QA evidence judge) rather than
    Mode A (diff review)?

    A Mode B pass never reviewed a diff, so recording it as a verifier stamp
    tells verifier-gate.py that bad-cop ran and found real bugs, which sends the
    session off to spawn good-cop over a diff nobody looked at. Mode B is
    therefore not recorded at all, and Mode A behaves exactly as it did before
    Mode B existed.

    Two independent signals, because one of them is enough on its own and
    neither is available in every payload:

      - the spawn prompt carries the routing marker bad-cop itself dispatches on
      - the report carries a Mode B stamp, which no Mode A pass emits

    A report carrying a real Mode A stamp wins over both. That keeps a Mode A
    report that merely quotes Mode B's vocabulary (a report about this loop, for
    instance) from having its own stamp thrown away.
    """
    lines = list(_stamp_lines(report))
    if any(line.startswith((VERIFIER_MARKER, HANDOFF_MARKER, NITS_MARKER)) for line in lines):
        return False
    if JUDGE_MODE_MARKER.upper() in (spawn_prompt or "").upper():
        return True
    return any(line.startswith(JUDGE_STAMPS) for line in lines)


def _clean_rag_home() -> Path:
    env = os.environ.get("CLEAN_RAG_HOME")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent


def _state_dir() -> Path:
    d = _clean_rag_home() / "state" / "verifier"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _record_path(session_id: str) -> Path:
    import hashlib

    key = hashlib.sha256((session_id or "no-session").encode("utf-8")).hexdigest()[:16]
    return _state_dir() / f"session-{key}.json"




def _first_verdict_line(text: str) -> str:
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("VERDICT:"):
            return stripped[:200]
    return (text or "")[:200]


def closing_stamp(report: str) -> str:
    """Which of the three closing markers the report actually closes on, or "".

    Neither "first match wins" nor "last match wins" identifies a close. A
    report legitimately quotes the convention while explaining it, so an early
    match may be prose; and a report legitimately adds a footnote or a recap
    after closing, so a late match may be prose too. Position alone cannot tell
    them apart, and picking one direction just chooses which report shape
    breaks.

    So this looks for a stamp the way git-interpret-trailers looks for a
    commit's trailers: in a block, and only when the block actually looks like a
    trailer block rather than like prose. Scanning blocks last to first, a block
    closes the report when both hold:

      - It names exactly one marker. bad-cop emits exactly one closing line, so
        a block naming two or three of them is reciting the convention.
      - That marker opens or closes the block. A marker line buried between
        prose lines is a wrapped sentence, not a stamp.

    Fails toward "" and toward HANDOFF, never toward NITS or VERIFIED, which is
    the safe direction: "" and HANDOFF both leave covers empty and route the
    loop to good-cop, so an unreadable close costs an extra fix pass. Guessing
    NITS tells the orchestrator to hand-polish a Critical finding, and guessing
    VERIFIED marks files reviewed that nobody reviewed. Both end the loop early
    on a real bug.
    """
    for block in reversed(_blocks(report)):
        markers = {_marker_of(line) for line in block} - {""}
        if len(markers) != 1:
            continue
        marker = markers.pop()
        if marker in (_marker_of(block[0]), _marker_of(block[-1])):
            return marker
    return ""


def is_nits_only_pass(report: str) -> bool:
    """Did bad-cop close with NITS:, meaning every finding was Nit severity?

    Keyed on the closing line, so a report that merely discusses the NITS
    convention is not read as one, and a real NITS close still routes to the
    orchestrator rather than spending an Opus fix pass on polish when the body
    happens to quote one of the other two markers.
    """
    return closing_stamp(report) == NITS_MARKER


def record_verifier(session_id: str, report: str, agent_type: str = "good-cop") -> None:
    """Called on PostToolUse after good-cop finishes, or after bad-cop finishes
    having found nothing (it stamps VERIFIED itself in that case, no separate
    good-cop run needed to re-confirm a clean adversarial pass). Appends a stamp.

    A bad-cop stamp also records nits_only, set when the report closed with
    NITS: instead of HANDOFF:. Both leave `covers` empty, so the flag is the
    only thing that lets verifier-gate route a nit only run to the
    orchestrator rather than to good-cop.

    Session scoped: unlike research's per-turn record, this file is never reset
    by a new prompt, since the diff it covers spans turns too.
    """
    path = _record_path(session_id)

    # research_state.append_stamp, not a second copy of the same read, modify
    # and write: it already carries the lock, the atomic write, and the verify
    # then retry that keeps a stamp from being clobbered when the lock fails
    # open. A lost stamp here reads back as unverified, so the gate nudges for
    # a review that already happened.
    recorded = append_stamp(
        path,
        {
            "agent": agent_type,
            "at": time.time(),
            # Only a report that closes on VERIFIED: names files. Reading a
            # VERIFIED: line out of a HANDOFF or NITS report's prose gives the
            # stamp a file list, and loop_stage keys the whole handoff on that
            # list being empty.
            "covers": (
                extract_covered_files(report, prefix=VERIFIER_MARKER)
                if closing_stamp(report) == VERIFIER_MARKER
                else []
            ),
            "verdict": _first_verdict_line(report),
            "nits_only": is_nits_only_pass(report),
        },
        {"session_id": session_id, "stamps": []},
    )
    if not recorded:
        print(
            f"[verifier-state] the {agent_type} stamp was not recorded; the "
            "verifier gate will treat the reviewed files as unverified.",
            file=sys.stderr,
        )


def check_file_verified(session_id: str, file_path: str) -> tuple[bool, str]:
    """Was this file verified (by good-cop's fix, or by bad-cop finding
    nothing to fix), and not edited again since?

    Returns (ok, reason). Picks the newest stamp that covers the file, then
    checks whether the file's mtime is still older than that stamp's
    timestamp; if the file changed again after the stamp, the review no
    longer describes what's on disk, so it doesn't count.
    """
    path = _record_path(session_id)
    if not path.exists():
        return False, "no verifier run has covered this file"

    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, "the verifier record is unreadable"

    stamps = record.get("stamps", []) if isinstance(record, dict) else []
    matching = [s for s in stamps if file_in_scope(file_path, s.get("covers", []))]
    if not matching:
        return False, "no verifier run has covered this file"

    newest = max(matching, key=lambda s: s.get("at", 0))
    verifying_agent = newest.get("agent", "verifier")

    try:
        mtime = Path(file_path).stat().st_mtime
    except OSError:
        # File is gone; nothing to re-verify against, and nothing to block either.
        return True, f"verified by {verifying_agent} (file no longer present)"

    if mtime > newest.get("at", 0):
        return False, "verified earlier, but edited again since"

    return True, f"verified by {verifying_agent}"
