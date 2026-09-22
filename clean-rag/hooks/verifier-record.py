#!/usr/bin/env python
"""PostToolUse on Task and Agent. Stamps the verifier record when good-cop
finishes, or when bad-cop finishes having found nothing (a genuinely clean
adversarial pass needs no separate good-cop run to confirm it).

Mirrors research-record.py exactly, including its tool_response flattening (the
same list-of-content-blocks shape applies to any Task/Agent completion), pointed
at verifier_state instead of research_state. Never blocks; its only job is to
write down what happened.

One completion it deliberately does not write down: bad-cop in Mode B, the /qa
evidence judge. That pass reads a finished QA session's artifacts and never looks
at a diff, so a stamp for it would tell verifier-gate.py that bad-cop reviewed
the code and found real bugs. See is_evidence_judge_pass in verifier_state.
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verifier_state import (  # noqa: E402
    VERIFIER_MARKER,
    closing_stamp,
    is_evidence_judge_pass,
    record_verifier,
)

VERIFIER_AGENTS = {"good-cop", "bad-cop"}

# --------------------------------------------------------------------------
# Execution proof on a VERIFIED stamp
#
# bad-cop.md:879 and good-cop.md:493 both say the same thing: VERIFIED is an
# execution claim, not a review claim, and the response body must contain the
# command and its actual output before that line appears. bad-cop.md even lists
# the phrasings it rejects by name, "I verified by inspection" among them.
#
# None of that was enforced. A report reading only "VERIFIED: foo.py", with no
# findings, no command and no output, was recorded identically to a fully
# evidenced one: main() called record_verifier unconditionally, record_verifier
# built the stamp from one regex on the marker line, and check_file_verified
# then returned True for foo.py. The whole contract was instruction text that
# nothing read.
#
# This is the same shape research-record.py already uses to require fetch proof
# on a citation, with one deliberate difference: the stamp is withheld entirely
# rather than recorded with its file list stripped. See the comment in main().
# --------------------------------------------------------------------------

_FENCE_RE = re.compile(
    r"(?P<fence>```|~~~)[ \t]*\w*\r?\n(?:(?!(?P=fence)).)+?\r?\n?(?P=fence)",
    re.DOTALL,
)

# Pasted output is line shaped; prose about output is sentence shaped. That is
# the only thing reliably separating the two, so these match a line rather than
# a substring anywhere in the body. CPython writes unittest's verdict as its own
# line, "OK" or "OK (skipped=1)" (Lib/unittest/runner.py:298-309), which is what
# makes it distinguishable from an "OK, so ..." sentence opener.
#
# Deliberately generous within that constraint. A false negative silently
# discards a real review, which is worse than letting a thin one through.
_RUNNER_OUTPUT = (
    re.compile(r"^\s*[$>]\s+\S", re.MULTILINE),                   # a shown command line
    re.compile(r"\b\d+\s+(passed|failed|skipped|error|errors)\b", re.I),  # pytest/jest
    re.compile(r"^\s*Ran \d+ tests?\b", re.MULTILINE),            # unittest
    re.compile(r"Traceback \(most recent call last\)"),
    re.compile(r"^[ \t]*OK([ \t]*\([^)]*\))?[ \t]*$", re.MULTILINE),  # unittest verdict
    re.compile(r"^\s*FAILED\b", re.MULTILINE),                    # unittest/pytest verdict
    re.compile(r"^\s*(PASS|FAIL)\b", re.MULTILINE),               # jest
    re.compile(r"^\s*={3,}.*\b(test|pass|fail)", re.MULTILINE | re.I),  # pytest banner
    re.compile(r"^\s*(Passed|Failed|Skipped)!", re.MULTILINE),    # vstest verdict
    # vstest and jest count summaries: "Failed:     0, Passed:     7, Total: 7"
    re.compile(r"\b(Failed|Passed|Skipped|Total|Tests|Test Suites):\s+\d+"),
    re.compile(r"\b(AssertionError|AssertFailedException|AssertionFailedError)\b"),
    re.compile(r"^\s*E\s{2,}\S", re.MULTILINE),                   # pytest's error line
    # An exit code shown as output starts its own line; one explained in prose
    # sits mid-sentence.
    re.compile(r"^\s*(process finished with\s+)?exit(\s+(code|status))?[ :=]+\d+",
               re.MULTILINE | re.I),
)

# Evidence from a run that prints no runner summary at all. CLAUDE.md names both
# as legitimate proof: an mcp-debugger step through, and a before/after
# screenshot pair from the eyes skill. Neither can be produced without executing
# something, which is the only question this check asks.
_EXECUTION_ARTIFACTS = (
    re.compile(
        r"\b(breakpoints?|get_(local_)?variables|evaluate_expression"
        r"|step(ped)?\s+(over|into|out|through)"
        r"|attach(ed)?\s+to\s+(the\s+)?process)\b",
        re.I,
    ),
    re.compile(r"\b[\w./\\-]+\.(png|jpe?g|webp|gif)\b", re.I),
)


def _has_execution_proof(report: str) -> bool:
    """True when the report shows a real command, real runner output, or an
    artifact only a real run produces.

    A fenced block is the usual shape, since that is how output gets pasted.
    The signal regexes cover output pasted without fences.
    """
    if _FENCE_RE.search(report):
        return True
    return any(rx.search(report) for rx in _RUNNER_OUTPUT + _EXECUTION_ARTIFACTS)


def _proof_check_enabled() -> bool:
    """Escape hatch, matching the CLAUDEBOOST_BASH_GUARD=off precedent."""
    return os.environ.get("CLEAN_RAG_VERIFIER_PROOF_CHECK", "").strip().lower() != "off"


def _agent_type(payload: dict) -> str:
    tool_input = payload.get("tool_input", {})
    return (
        tool_input.get("subagent_type")
        or tool_input.get("agent_type")
        or tool_input.get("agent")
        # SubagentStop carries it at the top level instead of under tool_input.
        or payload.get("agent_type")
        or payload.get("subagent_type")
        or ""
    )


def _is_subagent_stop(payload: dict) -> bool:
    """A SubagentStop payload, which names an agent but no tool."""
    return not payload.get("tool_name") and bool(
        payload.get("agent_type") or payload.get("agent_id")
    )


#: How much of the tail of a transcript to read before falling back to the
#: whole file. The handback sits a handful of entries from the end, but a
#: single entry can be large, so this is sized for "comfortably more than the
#: last few entries" rather than tuned.
_TAIL_BYTES = 512 * 1024


def _describe(e: BaseException) -> str:
    """One short line naming the failure, the shape research_state.py prints."""
    return f"{type(e).__name__}: {e}"


def _read_failure(e: OSError) -> str:
    """The failure worth reporting, empty for a missing file.

    No transcript is a real empty result rather than a read that gave up, and
    it is the ordinary shape for an agent that never handed back. Every read
    site shares this rule so the two cannot drift apart.
    """
    return "" if isinstance(e, FileNotFoundError) else _describe(e)


def _transcript_lines(path: Path) -> tuple[list[str], bool, str]:
    """The transcript's lines, reading only the tail when the file is large,
    whether the first of them may be a fragment left by the seek, and the read
    failure that stopped us, empty when nothing went wrong.

    A JSONL transcript grows without bound and this hook runs on every agent
    completion, so reading the whole file to find an entry near the end is
    waste.

    The failure is returned rather than swallowed because a read that gave up
    early is otherwise indistinguishable from a file that held nothing, which
    is the same defect os.walk's default has: without an `onerror` handler a
    partial walk reports as a complete one.

    The seek lands mid line, so the first line is normally cut from the left
    and json.loads rejects it. That fragment is expected on every large
    transcript, which is why the scan is told where it is instead of being
    left to infer it: only the reader that seeked knows, and a diagnostic
    that fires on every healthy run is one nobody reads. Position is what
    identifies it, the same way rag-enforce.py:1077 discards exactly the line
    after its own seek and LogTail._partial holds exactly the text after the
    last newline.

    It is still parsed and used if it happens to be valid, because a cut that
    lands on a line boundary leaves a complete entry there.
    """
    try:
        size = path.stat().st_size
    except OSError as e:
        return [], False, _read_failure(e)

    if size <= _TAIL_BYTES:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return [], False, _read_failure(e)
        return text.splitlines(), False, ""

    try:
        with path.open("rb") as fh:
            fh.seek(size - _TAIL_BYTES)
            chunk = fh.read()
    except OSError as e:
        return [], False, _read_failure(e)

    return chunk.decode("utf-8", errors="replace").splitlines(), True, ""


def _handback_report(agent_transcript_path: str) -> str:
    """The agent's real report, read from its own transcript, or empty.

    The report never arrives as assistant text. This project's agents deliver
    it through a `SubagentHandback` tool call, and only that call reaches the
    caller; plain text written at the end of a turn is not delivered. So the
    report is the `input.message` of the last `tool_use` block named
    `SubagentHandback`, and `last_assistant_message` is whatever the agent said
    in chat afterwards, which is sometimes a reply to a delayed background task
    notification minutes later. Confirmed 2026-09-18 by reading a real bad-cop
    transcript that closed `HANDOFF:`: the marker was in the handback at line
    194, and the final assistant text at line 201 was "No action needed".

    There is deliberately no fallback to the last assistant text. Falling back
    would let an agent that never handed back stamp the gate by writing
    `VERIFIED:` into ordinary chat, which is the one thing this record exists
    to make unfakeable. No handback means no report.
    """
    if not agent_transcript_path:
        return ""
    p = Path(agent_transcript_path)

    lines, first_line_may_be_cut, read_error = _transcript_lines(p)
    report, unreadable = _scan_for_handback(
        lines, first_line_may_be_cut=first_line_may_be_cut
    )

    # The tail read may have cut above the handback, or may not have happened
    # at all. Retry on the whole file before concluding there is none.
    #
    # A failed tail read earns the same retry as a short one, which is what
    # makes this the recovery for a transient failure rather than only its
    # diagnostic: the causes are momentary (research_state.py:155 measures the
    # same Windows handles clearing in milliseconds) and a second read costs
    # nothing on a healthy run, because a handback found in the tail never
    # reaches here.
    #
    # No seek happens here, so no line is expected to be a fragment and every
    # parse failure counts. That also re-reads the one line the tail scan was
    # told to stay quiet about, so a genuinely corrupt first line of the
    # window is still reported, just by this pass instead of that one.
    if not report:
        try:
            if read_error or p.stat().st_size > _TAIL_BYTES:
                full = p.read_text(encoding="utf-8", errors="replace").splitlines()
                report, unreadable = _scan_for_handback(full)
                # Every byte was read, so whatever the tail missed is answered.
                read_error = ""
        except OSError as e:
            read_error = read_error or _read_failure(e)

    if not report:
        _explain_empty_report(p, read_error, unreadable)
    return report


def _explain_empty_report(p: Path, read_error: str, unreadable: list[str]) -> None:
    """Say which of the three empty states this was, on stderr.

    "No handback was present", "the entry holding it was unreadable" and "the
    transcript could not be read at all" all return the same empty string, and
    returning it with no explanation is what made the original crash
    invisible. The first needs nothing said: an agent that did not hand back
    is the ordinary case and a diagnostic nobody needs is one nobody reads.
    """
    if read_error:
        # A report above the tail window is lost whenever the retry cannot
        # read, which on Windows is what a file another process still holds
        # open looks like. Silence reads as "this agent never handed back",
        # blaming the agent for a failure that was ours.
        # The closing advice names both causes because the error does not say
        # which one this is. A held file clears on its own and running the cop
        # again fixes it, but a path naming a directory fails the same way
        # forever, so asserting the lock cause sends someone to retry a thing
        # that cannot work.
        print(
            f"[verifier-record] could not read {p.name}: {read_error}. Nothing "
            f"was recorded and the files stay unverified. The handback may "
            f"still be in {p}: this is a read failure, not a missing report. "
            f"If that path is a real transcript, another process holding it is "
            f"the usual cause on Windows and clears in milliseconds, so run the "
            f"cop again. If it is not, the payload named the wrong path and "
            f"running the cop again will fail the same way.",
            file=sys.stderr,
        )

    if unreadable:
        print(
            f"[verifier-record] found no SubagentHandback in {p.name} after "
            f"skipping {len(unreadable)} unreadable transcript "
            f"{'entry' if len(unreadable) == 1 else 'entries'}. First: "
            f"{unreadable[0]}",
            file=sys.stderr,
        )


def _handback_in_entry(entry: object) -> str:
    """The last SubagentHandback message in one transcript entry, or empty.

    Every field is read as untrusted, so a value present with the wrong type
    reads as absent and takes the path that already handles a missing one.
    `.get(key, default)` does not do that by itself: the default fires when the
    key is absent, never when it holds the wrong type, which is how
    `(block.get("input") or {}).get(...)` raised AttributeError whenever
    `input` was not a dict. Same reasoning as _str_field in rag-enforce.py:970.

    A block that fails a guard is skipped rather than ending the entry, so a
    malformed block cannot hide a good one beside it.
    """
    if not isinstance(entry, dict):
        return ""
    msg = entry.get("message")
    if not isinstance(msg, dict):
        return ""
    content = msg.get("content")
    if not isinstance(content, list):
        return ""
    for block in reversed(content):
        if not isinstance(block, dict):
            continue
        if block.get("type") != "tool_use":
            continue
        if block.get("name") != "SubagentHandback":
            continue
        tool_input = block.get("input")
        if not isinstance(tool_input, dict):
            continue
        message = tool_input.get("message")
        if isinstance(message, str) and message.strip():
            return message
    return ""


def _scan_for_handback(
    lines: list[str], *, first_line_may_be_cut: bool = False
) -> tuple[str, list[str]]:
    """The last SubagentHandback message in these lines, plus one note per
    entry that could not be read at all.

    The walk runs backwards, so an exception raised by a late entry does not
    cost that entry, it costs every earlier one. The real report is exactly
    what a corrupt tail would hide that way, so an unreadable entry is skipped
    instead. jsonlines exposes the same rule as Reader.iter(skip_invalid=True),
    and raises one InvalidLineError for unparseable JSON and for a line of the
    wrong data type alike. It skips silently; these are collected, because a
    silently skipped entry looks identical to a review that never happened,
    which is the one thing this record exists to rule out.

    Both ways a line goes unread count: JSON that will not parse (a torn
    write, a BOM, a process killed mid line) and JSON that parses into a shape
    _handback_in_entry cannot walk. Neither is distinguishable from "no
    handback" once it is dropped without a note.

    `first_line_may_be_cut` is the one exemption, and it is positional rather
    than a guess at the content: with it set, a parse failure on line 0 is
    read as the fragment the caller's seek left behind. A left cut line and a
    right truncated one both fail to parse and both can start with `{`, so
    nothing about the text itself separates them.

    The limit that follows, accepted rather than fixed: genuine corruption
    landing exactly on the seek boundary goes unreported when the scan finds a
    report later in the same window, because the retry that would re-derive
    the note from the whole file only runs when nothing was found. Reporting
    it instead would fire on every transcript over the window, which is the
    noise property 9 forbids, and the miss costs only a note. It can never
    hide a report: a handback on that line is unparseable either way, and then
    no report is found and the retry does run.
    """
    unreadable: list[str] = []
    for i in range(len(lines) - 1, -1, -1):
        line = lines[i].strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except Exception as e:
            if not (i == 0 and first_line_may_be_cut):
                unreadable.append(_describe(e))
            continue
        try:
            message = _handback_in_entry(entry)
        except Exception as e:
            unreadable.append(_describe(e))
            continue
        if message:
            return message, unreadable
    return "", unreadable


def _spawn_prompt(payload: dict) -> str:
    """The prompt the agent was spawned with, which is where the mode marker is."""
    return payload.get("tool_input", {}).get("prompt") or ""


def _report(payload: dict) -> str:
    """The agent's report, flattened to plain text. See research-record.py's
    _report() for why this can't just be str(tool_response)."""
    response = payload.get("tool_response", "")

    if isinstance(response, str):
        return response

    if isinstance(response, list):
        parts = []
        for block in response:
            if isinstance(block, dict):
                parts.append(block.get("text") or block.get("content") or "")
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(p for p in parts if p)

    if isinstance(response, dict):
        inner = response.get("content") or response.get("output") or response.get("text")
        if inner is None:
            return ""
        if isinstance(inner, (str, list, dict)):
            return _report({"tool_response": inner})
        return str(inner)

    return str(response)


#: Temporary. Every invocation of this hook appends one line here, before any
#: early return, so "the hook ran and rejected the payload" can be told apart
#: from "the hook never ran at all". Those two look identical from the record,
#: which is why four real cop completions produced no stamp and no explanation.
#: Delete this and _trace() once SubagentStop's behaviour is established.
_TRACE_PATH = Path(__file__).resolve().parent.parent / "state" / "verifier-hook-trace.log"


def _trace(note: str) -> None:
    """Append one line. Never raises: a broken trace must not break the hook."""
    try:
        _TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _TRACE_PATH.open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now().isoformat(timespec='seconds')} {note}\n")
    except Exception:
        pass


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except Exception:
        _trace(f"INVOKED unparseable_stdin bytes={len(raw)}")
        return 0

    # json.loads succeeds for any JSON value, so a payload of `null`, a list or
    # a bare string parses fine and then fails at the first .get(). Claude Code
    # sends an object; anything else is not an agent completion and there is
    # nothing to stamp.
    if not isinstance(payload, dict):
        _trace(f"INVOKED non_dict_payload type={type(payload).__name__}")
        return 0

    _trace(
        "INVOKED "
        f"event={payload.get('hook_event_name')!r} "
        f"tool={payload.get('tool_name')!r} "
        f"agent_type={payload.get('agent_type')!r} "
        f"subagent_type={payload.get('tool_input', {}).get('subagent_type')!r} "
        f"keys={sorted(payload)} "
        f"last_msg_len={len(payload.get('last_assistant_message') or '')}"
    )

    subagent_stop = _is_subagent_stop(payload)
    if not subagent_stop and payload.get("tool_name") not in ("Task", "Agent"):
        return 0

    agent_type = _agent_type(payload)
    if agent_type not in VERIFIER_AGENTS:
        return 0

    if subagent_stop:
        # SubagentStop fires when the agent actually finishes, so this is the
        # only path that sees a report at all once Task spawns run async.
        #
        # Read the agent's own transcript, not `last_assistant_message` and not
        # `transcript_path`. The first carries the agent's closing chat text,
        # which never holds the marker; the second is THIS session's transcript
        # rather than the subagent's, so it was never the right file. Both were
        # wrong from 2026-08-28 until 2026-09-18, which is why no stamp in that
        # window ever carried a covers list.
        report = _handback_report(payload.get("agent_transcript_path", ""))
    else:
        report = _report(payload)

    _trace(
        f"REPORT agent={agent_type!r} len={len(report)} "
        f"closing={closing_stamp(report)!r} "
        f"proof={_has_execution_proof(report)} "
        f"agent_transcript={payload.get('agent_transcript_path')!r} "
        f"tail={report[-300:]!r}"
    )

    if is_evidence_judge_pass(_spawn_prompt(payload), report):
        _trace("SKIPPED evidence_judge_pass")
        return 0

    # A report with none of the three closing markers is not a report.
    #
    # Recording it anyway writes a stamp with an empty covers list, and
    # loop_stage() reads `agent == "bad-cop" and not covers` as
    # STAGE_BUGS_FOUND. So a completion that carried no report at all becomes
    # indistinguishable from a real HANDOFF, and the loop routes to good-cop on
    # evidence that does not exist. Skipping it leaves STAGE_NO_VERIFIER, which
    # is the truthful state and the same reasoning the proof check below uses.
    #
    # Measured 2026-09-17: every session from 2026-08-28 onward recorded 0 of N
    # stamps with a covers list, 21 sessions running. Feeding this hook a real
    # report records covers, hashes and verdict correctly, so the hook was never
    # the defect; it was being handed completions with no report text. A
    # backgrounded spawn is the known cause, since the PostToolUse fires when
    # the Task tool returns rather than when the agent finishes
    # (anthropics/claude-code#21352).
    if not closing_stamp(report):
        print(
            f"[verifier-record] {agent_type} completion carried no VERIFIED, "
            f"HANDOFF or NITS line, so nothing was recorded and the files stay "
            f"unverified. A report is required to end with one of the three. "
            f"The usual cause is a backgrounded spawn: the record is written "
            f"when the Task tool returns, not when the agent finishes, so the "
            f"launch acknowledgement arrives here instead of the report. Spawn "
            f"{agent_type} in the foreground and re-run.",
            file=sys.stderr,
        )
        return 0

    # A VERIFIED with no execution behind it is not recorded at all.
    #
    # research-record.py strips the COVERS: line and records the stamp anyway.
    # Copying that here would be wrong, and quietly so. verifier-gate.py's
    # loop_stage reads `agent == "bad-cop" and not covers` as STAGE_BUGS_FOUND,
    # so a bad-cop stamp with its file list removed does not read as "nothing
    # verified", it reads as "bad-cop found real bugs" and routes to good-cop.
    # Skipping the record leaves STAGE_NO_VERIFIER, which is the truthful state:
    # no verifier pass has covered these files.
    #
    # Only the VERIFIED path is gated, and only when VERIFIED is the report's own
    # closing line. HANDOFF and NITS legitimately carry no file list, and that
    # empty list is exactly what drives the loop routing, so withholding those
    # stamps would break the handoff to good-cop. Matching a VERIFIED: line
    # anywhere in the body swallows them, because a report about this loop quotes
    # one while explaining itself.
    if (
        _proof_check_enabled()
        and closing_stamp(report) == VERIFIER_MARKER
        and not _has_execution_proof(report)
    ):
        print(
            f"[verifier-record] VERIFIED stamp not recorded. {agent_type} returned a "
            f"VERIFIED line with no command and no output anywhere in the report. "
            f"bad-cop.md:879 and good-cop.md:493 both require the command run, shown "
            f"verbatim, and its actual output before that line: VERIFIED is an "
            f"execution claim, not a review claim, and \"I verified by inspection\" is "
            f"named there as not qualifying. The files it named stay unverified. "
            f"Re-run {agent_type} and require the run. To turn this check off, set "
            f"CLEAN_RAG_VERIFIER_PROOF_CHECK=off.",
            file=sys.stderr,
        )
        return 0

    session_id = payload.get("session_id", "")
    record_verifier(
        session_id=session_id,
        report=report,
        agent_type=agent_type,
        # Resolves a relative covers entry to the file whose contents get hashed.
        cwd=payload.get("cwd") or "",
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        # Exit 0 like its siblings, but say what went wrong. This hook writes
        # the stamp verifier-gate.py reads, so a swallowed failure looks
        # identical to the review never having happened.
        print(
            f"[verifier-record] could not stamp this agent completion: "
            f"{type(e).__name__}: {e}. The verifier gate will treat the "
            f"reviewed files as unverified.",
            file=sys.stderr,
        )
        sys.exit(0)
