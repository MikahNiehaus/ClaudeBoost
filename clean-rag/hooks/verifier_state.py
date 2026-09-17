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
forking them. It differs in the marker line ("VERIFIED:" instead of "COVERS:"),
the mtime based invalidation, and in reading the file list out of the closing
block only (see covered_files_in_block), since a verifier report legitimately
quotes the marker while explaining the loop it is part of.
"""

import hashlib
import json
import os
import re
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
    normalized = _normalize(line)
    for marker in _MARKERS:
        if normalized.startswith(marker):
            return marker
    return ""


# CommonMark 4.5: a fenced code block is opened by three or more backticks or
# tildes, indented at most three spaces, and runs until a closing fence of the
# same character and at least the same length, or to the end of the document if
# there is none. A blank line inside it is content, not a boundary.
#
# The closer is deliberately the stricter pattern (fence characters and nothing
# else, per the spec, where only the opener may carry an info string). An
# unrecognized closer leaves the fence open longer, which swallows more text; a
# too-generous one ends the fence early and exposes what is inside it.
_FENCE_OPEN_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")
_FENCE_CLOSE_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})[ \t]*$")


def _collapse_fences(lines: list[str]) -> list[str]:
    """Every fenced region reduced to its opening line alone.

    Blank lines do not split a fence, so a fence cannot be read as several
    blocks. pytest prints a blank line before its summary, which put the rest of
    a pasted run into a fresh block: a quoted "VERIFIED: other.py" on the line
    after it then opened that block and was recorded as the report's own stamp,
    naming a file nobody had reviewed.

    Collapsing rather than deleting keeps the fence occupying one non-blank
    line, so it still joins the block around it exactly as it did before and a
    stamp on the line after a fence still reads as one.

    The fail direction is toward "" (no stamp found). An unbalanced fence
    swallows the text after it, including a real closing stamp, and an
    unstamped report leaves its files reading as unverified, which keeps
    nudging. A stamp parsed out of pasted output is the silent direction.
    """
    out: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        opener = _FENCE_OPEN_RE.match(lines[i])
        if not opener:
            out.append(lines[i])
            i += 1
            continue
        fence = opener.group(1)
        out.append(lines[i])
        i += 1
        while i < n:
            closer = _FENCE_CLOSE_RE.match(lines[i])
            i += 1
            if (
                closer
                and closer.group(1)[0] == fence[0]
                and len(closer.group(1)) >= len(fence)
            ):
                break
    return out


def _blocks(text: str) -> list[list[str]]:
    """Runs of consecutive non-blank lines, kept verbatim.

    Verbatim, not normalized, because the block is also what the file list is
    parsed out of: extract_covered_files matches its "agentId:" suffix cut
    case-sensitively and the recorded paths should read as the agent wrote them.
    Blankness is still judged on the normalized line, so a whitespace-only line
    separates two blocks.

    A block is git's unit for the same problem: git-interpret-trailers finds a
    commit's trailers in "a group of one or more lines ... preceded by one or
    more empty (or whitespace only) lines", not by scanning the whole message.

    Fenced code is collapsed first, so pasted runner output cannot contribute a
    line to any block. See _collapse_fences.
    """
    blocks, current = [], []
    for raw in _collapse_fences((text or "").splitlines()):
        if _normalize(raw):
            current.append(raw)
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


# A token that is unambiguously a file reference: a path separator, a glob, or a
# short extension suffix. Prose split on commas fails all three, which is what
# keeps a sentence out of the covers list.
_EXTENSION_RE = re.compile(r"\.[A-Za-z0-9_+-]{1,10}$")

# Files carrying no extension and no separator, which no shape rule can tell
# apart from an ordinary word. GitHub Linguist has the same problem and solves
# it the same way, with an explicit `filenames:` list in languages.yml next to
# its extension map, documented there as the list of associated filenames.
# Matched exactly and case sensitively, so a lowercase "license" in a sentence
# is not read as the file.
_KNOWN_BARE_FILENAMES = frozenset({
    "AUTHORS", "Brewfile", "CHANGELOG", "CODEOWNERS", "COPYING",
    "Containerfile", "Dockerfile", "GNUmakefile", "Gemfile", "Jenkinsfile",
    "LICENCE", "LICENSE", "Makefile", "NOTICE", "Podfile", "Procfile",
    "README", "Rakefile", "Vagrantfile", "makefile",
})

# Stripped from the front of a continuation line before parsing, so a bulleted
# file list reads the same as a comma separated one. "*" and "#" match what
# _normalize already strips from a marker line.
_LIST_PREFIX = "-*# \t"


def _is_bare_file_token(token: str) -> bool:
    """One whitespace-free segment that reads as a file reference."""
    if not token:
        return False
    if "*" in token or "/" in token or "\\" in token:
        return True
    if token in _KNOWN_BARE_FILENAMES:
        return True
    return bool(_EXTENSION_RE.search(token))


def _is_file_token(token: str) -> bool:
    """Does this comma-separated token read as a file reference?

    A space in a path is legal, not exotic: POSIX permits every byte but "/" and
    NUL in a filename, and Windows allows spaces outright, so
    "C:\\Development\\F and B PWA\\src\\app.py" is a path this list has to carry.
    Rejecting a token for containing whitespace therefore drops real files.
    Accepting whitespace outright sweeps prose in instead, since a sentence
    below the marker is also one comma-free token.

    The line between them is where the whitespace sits. In a path, the space is
    interior: the segments on either end are still path shaped. A sentence
    usually opens on an ordinary word, so requiring the first and last segments
    to each read as a file on their own lets a spaced path through while
    rejecting most prose.

    Most, not all, and the gap is not closeable here. A sentence with a file at
    both ends is accepted:

        "app.py breaks config.py"   -> ['app.py', 'breaks', 'config.py']
        "C:/dev/F and B PWA/a.py"   -> ['C:/dev/F', 'and', 'B', 'PWA/a.py']

    Two file references separated by a word and one path containing a word are
    close to the same shape, and every rule that separates them buys it with a
    new false negative. Requiring the first segment to be a truncated directory
    fragment rather than a complete reference does reject all four examples
    above, and it also rejects "notes.v2 and more/app.py", a real path whose
    first directory carries a version style dot. Tightening moves the gap, it
    does not close it, so this keeps the looser rule and bounds the damage
    instead.

    What bounds the damage is downstream, in file_in_scope: it compares each
    covers entry as one indivisible string, so a recorded sentence only ever
    matches its own literal self. It can never mark app.py or config.py
    verified. The cost of this gap is therefore a noisy audit record, never a
    false verification. test_verifier_prose_both_ends_covers_gap.py holds both
    halves of that: the accept, and the proof it stays inert.
    """
    segments = token.split()
    if not segments:
        return False
    return _is_bare_file_token(segments[0]) and _is_bare_file_token(segments[-1])


def _continuation_files(line: str) -> list[str]:
    """The file list on a line below the marker, or [] if the line is anything
    else.

    All or nothing per line: one token that does not read as a file rejects the
    whole line. That is the deliberate fail direction, and it is not free. An
    over broad covers list marks files verified that nobody reviewed and the
    gate then goes silent about them, which is unrecoverable from the record. A
    missed entry is recoverable but costs more than it looks: on a VERIFIED
    close it empties the covers list, and loop_stage reads a bad-cop stamp with
    empty covers as STAGE_BUGS_FOUND, so a clean pass routes to good-cop for a
    fix pass over nothing, and the files keep reading as unverified. That
    emptiness is load bearing for HANDOFF and NITS, which legitimately carry no
    files, so the cost is paid here by making the token check generous rather
    than by changing what empty covers means.
    """
    text = line.strip().lstrip(_LIST_PREFIX).strip().split("agentId:", 1)[0]
    tokens = [t.strip().strip("`") for t in text.split(",") if t.strip()]
    if not tokens or not all(_is_file_token(t) for t in tokens):
        return []
    return tokens


def covered_files_in_block(block: list[str]) -> list[str]:
    """The VERIFIED file list carried by a closing block, including a list that
    wrapped onto the lines below the marker.

    extract_covered_files reads the marker line and returns, so a close that
    puts the marker alone on its own line records nothing. Reading forward is
    only safe because a block is already bounded by blank lines and already
    chosen as the close; the same reading applied to a whole report would sweep
    up whatever prose follows the first marker-shaped line anywhere in it.

    Continuation stops at the first line that is not a file list. git does the
    same for a folded trailer value ("split over multiple lines with each
    subsequent line starting with whitespace, like the folding in RFC 822",
    git-interpret-trailers), but identifies the fold by that leading whitespace.
    Agent reports wrap without indenting, so the signal here is token shape.
    """
    for i, line in enumerate(block):
        if _marker_of(line) != VERIFIER_MARKER:
            continue
        covers = extract_covered_files(line, prefix=VERIFIER_MARKER)
        for continuation in block[i + 1:]:
            more = _continuation_files(continuation)
            if not more:
                break
            covers.extend(more)
        return covers
    return []


def is_evidence_judge_pass(spawn_prompt: str, report: str) -> bool:
    """Was this completion bad-cop in Mode B (QA evidence judge) rather than
    Mode A (diff review)?

    A Mode B pass never reviewed a diff, so recording it as a verifier stamp
    tells verifier-gate.py that bad-cop ran and found real bugs, which sends the
    session off to spawn good-cop over a diff nobody looked at. Mode B is
    therefore not recorded at all, and Mode A behaves exactly as it did before
    Mode B existed.

    The spawn prompt decides it, and nothing in the report overrides that. The
    marker is on its own line there because that is how bad-cop.md:28 tells the
    agent to dispatch on it, so the prompt is the routing fact rather than a
    reading of one. The report is the agent's own prose and quotes whatever it
    is discussing: a Mode B judgement that explains the Mode A convention writes
    a VERIFIED: line while explaining it, and scanning the whole body for one
    turned that sentence into a code-review stamp naming files nobody opened.

    When the prompt is silent the report decides, and there a real Mode A close
    wins over Mode B vocabulary quoted in passing. Closing stamp, not any line
    anywhere, for the reason in the module docstring: a verifier report
    legitimately quotes the marker while explaining the loop it is part of.

    Fails toward Mode B, which records nothing and leaves the files reading as
    unverified. That keeps nudging. Mode A is the silent direction.
    """
    if any(line.startswith(JUDGE_MODE_MARKER.upper()) for line in _stamp_lines(spawn_prompt)):
        return True
    if closing_stamp(report):
        return False
    return any(line.startswith(JUDGE_STAMPS) for line in _stamp_lines(report))


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
    key = hashlib.sha256((session_id or "no-session").encode("utf-8")).hexdigest()[:16]
    return _state_dir() / f"session-{key}.json"


# A reviewed source file is far below this. The cap is here so a Stop hook
# cannot stall on a capture or a binary that happened to land in a covers list;
# an oversized file records no hash and keeps the mtime rule below.
_HASH_SIZE_CAP = 16 * 1024 * 1024


def _content_hash(path: Path) -> str:
    """sha256 of the file, or "" when it cannot be read or is over the cap."""
    try:
        if path.stat().st_size > _HASH_SIZE_CAP:
            return ""
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return ""


def _hash_key(file_path) -> str:
    """The key a content hash is looked up under: absolute and case folded.

    abspath, never Path.resolve(). resolve() opens the file to canonicalize it,
    which measured 27ms per call on Windows against 0.02ms for abspath, and
    check_file_verified runs this once per changed file on every Stop. abspath
    is pure string work.
    """
    return os.path.normcase(os.path.abspath(str(file_path)))


def _hash_keys(file_path) -> list:
    """Every key one file may be looked up under, for the write side.

    Two, when they differ: the path as written, and its canonical form. The
    stamp is written from the agent's own relative covers entry while
    verifier-gate.py looks it up by a path it has already resolved, so a symlink
    or a junction between them would otherwise miss. The one resolve() this
    costs is paid here, once per stamp, rather than on every check.
    """
    keys = [_hash_key(file_path)]
    try:
        canonical = os.path.normcase(str(Path(file_path).resolve()))
    except OSError:
        return keys
    if canonical not in keys:
        keys.append(canonical)
    return keys


def _covered_hashes(covers: list, cwd: str) -> dict:
    """Content hash per covered file, at the moment the stamp is written.

    Glob entries and paths that do not exist are absent on purpose; those keep
    the mtime rule, which is what they had before.

    The hashing itself is not the cost: 62 source files totalling 859KB
    measured 10.5ms. Path.resolve() on the same 62 measured 1700ms, which is
    why it appears once here and never in check_file_verified.
    """
    hashes = {}
    base = Path(cwd) if cwd else Path.cwd()
    for entry in covers:
        if "*" in entry or "?" in entry:
            continue
        target = Path(os.path.abspath(str(base / entry)))
        digest = _content_hash(target)
        if not digest:
            continue
        for key in _hash_keys(target):
            hashes[key] = digest
    return hashes


def _first_verdict_line(text: str) -> str:
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("VERDICT:"):
            return stripped[:200]
    return (text or "")[:200]


def _closing_block(report: str) -> tuple[str, list[str]]:
    """The marker the report closes on and the block that carries it, or ("", []).

    Returning the block is what keeps the marker and its file list reading the
    same lines. git does the same in trailer.c: parse_trailers() finds
    trailer_block_start once, then splits only from that offset
    (`strbuf_split_buf(str + trailer_block_start, ...)`) and reads every
    token and value out of those lines. It never re-scans the whole message for
    a token once it has chosen the block.

    See closing_stamp for how a block is judged to be the close.
    """
    for block in reversed(_blocks(report)):
        markers = {_marker_of(line) for line in block} - {""}
        if len(markers) != 1:
            continue
        marker = markers.pop()
        if marker in (_marker_of(block[0]), _marker_of(block[-1])):
            return marker, block
    return "", []


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

    Pasted runner output is out of the running before either test, because
    _blocks collapses fenced code to a single line first.

    Fails toward "" and toward HANDOFF, never toward NITS or VERIFIED, which is
    the safe direction: "" and HANDOFF both leave covers empty and route the
    loop to good-cop, so an unreadable close costs an extra fix pass. Guessing
    NITS tells the orchestrator to hand-polish a Critical finding, and guessing
    VERIFIED marks files reviewed that nobody reviewed. Both end the loop early
    on a real bug.
    """
    return _closing_block(report)[0]


def is_nits_only_pass(report: str) -> bool:
    """Did bad-cop close with NITS:, meaning every finding was Nit severity?

    Keyed on the closing line, so a report that merely discusses the NITS
    convention is not read as one, and a real NITS close still routes to the
    orchestrator rather than spending an Opus fix pass on polish when the body
    happens to quote one of the other two markers.
    """
    return closing_stamp(report) == NITS_MARKER


def record_verifier(
    session_id: str,
    report: str,
    agent_type: str = "good-cop",
    cwd: str = "",
) -> None:
    """Called on PostToolUse after good-cop finishes, or after bad-cop finishes
    having found nothing (it stamps VERIFIED itself in that case, no separate
    good-cop run needed to re-confirm a clean adversarial pass). Appends a stamp.

    A bad-cop stamp also records nits_only, set when the report closed with
    NITS: instead of HANDOFF:. Both leave `covers` empty, so the flag is the
    only thing that lets verifier-gate route a nit only run to the
    orchestrator rather than to good-cop.

    Session scoped: unlike research's per-turn record, this file is never reset
    by a new prompt, since the diff it covers spans turns too.

    cwd is the hook payload's working directory, used only to resolve a relative
    covers entry when hashing it. An entry that does not resolve simply records
    no hash.
    """
    path = _record_path(session_id)

    # Only a report that closes on VERIFIED: names files, and only the block it
    # closed on names them. Scanning the whole report instead hands the covers
    # slot to the first VERIFIED:-shaped line anywhere above, which a report
    # explaining this very convention writes as an ordinary quoted example. That
    # misrecords two ways at once: the file actually reviewed stays unverified,
    # and whatever the quoted line happened to name is marked reviewed instead.
    marker, block = _closing_block(report)
    covers = covered_files_in_block(block) if marker == VERIFIER_MARKER else []

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
            # A HANDOFF or NITS report leaves this empty, and loop_stage keys
            # the whole handoff on that emptiness.
            "covers": covers,
            # What the reviewed files actually contained, so check_file_verified
            # can ask whether they still do rather than trusting a timestamp.
            "hashes": _covered_hashes(covers, cwd),
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


def _contents_changed(stamp: dict, file_path: str) -> bool:
    """Does this file no longer hold what the stamp recorded?

    False when the stamp has no hash for it, which is the honest answer: a glob
    covers entry, a file that was absent when the stamp was written, or a record
    from before hashes existed says nothing about the contents either way, and
    the caller's timestamp rule still applies.
    """
    recorded = (stamp.get("hashes") or {}).get(_hash_key(file_path))
    return bool(recorded) and _content_hash(Path(file_path)) != recorded


def check_file_verified(session_id: str, file_path: str) -> tuple[bool, str]:
    """Was this file verified (by good-cop's fix, or by bad-cop finding
    nothing to fix), and not edited again since?

    Returns (ok, reason). Picks the newest stamp that covers the file, then
    asks two things of it: does it still hold the contents that were reviewed,
    and is its mtime still older than the stamp.

    Content first, because mtime only answers the question under an assumption
    that does not hold. "Newer than the stamp" reads a clock, and a clock moves
    both ways: a synced or restored file, skew between two machines, or an
    editor that preserves mtime on save all leave a rewritten file reading as
    still verified. git hit the same wall with its index and answered it the
    same way, in racy-git.adoc: when the cached stat data alone cannot settle
    it, git "also compares the contents with the object". Both checks run, so
    this only ever invalidates more than the timestamp alone did.

    A stamp with no recorded hash for this file (a glob covers entry, a path
    that did not resolve when the stamp was written, a record from before
    hashes existed) keeps the timestamp rule by itself.
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

    if _contents_changed(newest, file_path):
        return False, "verified earlier, but its contents changed since"

    if mtime > newest.get("at", 0):
        return False, "verified earlier, but edited again since"

    return True, f"verified by {verifying_agent}"
