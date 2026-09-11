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
        or ""
    )


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


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except Exception:
        return 0

    # json.loads succeeds for any JSON value, so a payload of `null`, a list or
    # a bare string parses fine and then fails at the first .get(). Claude Code
    # sends an object; anything else is not an agent completion and there is
    # nothing to stamp.
    if not isinstance(payload, dict):
        return 0

    if payload.get("tool_name") not in ("Task", "Agent"):
        return 0

    agent_type = _agent_type(payload)
    if agent_type not in VERIFIER_AGENTS:
        return 0

    report = _report(payload)
    if is_evidence_judge_pass(_spawn_prompt(payload), report):
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
    record_verifier(session_id=session_id, report=report, agent_type=agent_type)
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
