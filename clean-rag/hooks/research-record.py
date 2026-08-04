#!/usr/bin/env python
"""PostToolUse on Task and Agent. Stamps the turn record when research finishes.

This is the half of the gate the model cannot simply skip. research-gate.py
refuses an edit unless this hook has fired, and this hook only fires after Claude
Code has actually run swiper to completion.

To be clear about what that is and isn't: it stops the model forgetting or
drifting, which is the real failure. It is not a security boundary. A model with
Write access can author a stamp file directly if it sets out to. The only actual
security control here is the bash guard on the research agents themselves.

Never blocks. Its only job is to write down what happened.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from research_state import (  # noqa: E402
    RESEARCH_AGENTS,
    clear_session_quick,
    extract_covered_files,
    record_agent,
)

# Proof enforcement: if a report cites a code-source domain (GitHub, StackOverflow,
# etc) without fetching and quoting the actual code, strip the COVERS: line so the
# downstream research gate blocks on the next edit, forcing a respin.
# The gate itself can't reject (PostToolUse fires after the task completes), but
# stripping scope reuses the existing "ran but declared no file coverage" block.

_DOMAIN_PROOF_MAP = {
    re.compile(r"(?:github\.com|gist\.github\.com|raw\.githubusercontent\.com)/[\w.\-/]+", re.IGNORECASE): "GITHUB_FILE_READ:",
    re.compile(r"stackoverflow\.com/questions/", re.IGNORECASE): "STACKOVERFLOW_ANSWER_READ:",
    re.compile(r"gitlab\.com/[\w.\-/]+", re.IGNORECASE): "GITLAB_FILE_READ:",
    re.compile(r"bitbucket\.org/[\w.\-/]+", re.IGNORECASE): "BITBUCKET_FILE_READ:",
    re.compile(r"codepen\.io/[\w.\-/]+/pen/", re.IGNORECASE): "CODEPEN_READ:",
}

_FENCE_RE = re.compile(
    r"(?P<fence>```|~~~)[ \t]*\w*\r?\n(?:(?!(?P=fence)).)+?\r?\n?(?P=fence)",
    re.DOTALL,
)
_COVERS_LINE_RE = re.compile(r"^COVERS:.*$", re.MULTILINE | re.IGNORECASE)

# Bounds the "is this citation actually followed by a code claim" window to the
# citation's own structural unit: a real section break (two or more consecutive
# blank lines), the next per-aspect "**N." marker, or the next markdown heading,
# whichever comes first. A SINGLE blank line is deliberately NOT a boundary:
# "See [file](url):" then a blank line then a fenced code block is completely
# standard markdown (and the exact style swiper/researcher reports use), so
# cutting the window at one blank line would let any normally-formatted unproven
# citation+code evade the check. researcher/swiper reports (see
# clean-rag/portable/agents/swiper.md, researcher.md) are written per-aspect, not
# as one end-of-document bibliography, so a section/heading boundary tracks the
# report's real structure far better than any fixed character count would.
_PARAGRAPH_BOUNDARY_RE = re.compile(r"\n\s*\n\s*\n|\n\*\*\d+\.|\n#{1,6}\s")


def _window_end(report: str, start: int) -> int:
    match = _PARAGRAPH_BOUNDARY_RE.search(report, start)
    return match.start() if match else len(report)


def _missing_proof(report: str) -> list:
    """List of domains cited *with an adjacent code claim* but no fetch proof.

    Returns a list of violation descriptions, e.g. ["GitHub repo cited but no GITHUB_FILE_READ: line"].
    Empty list means no violations.

    Only fires when a domain citation is closely followed (within its own
    paragraph/aspect, see _window_end) by a fenced code block -- that's the
    actual fabrication risk this check exists to catch: claiming quoted code
    came from a source without proving the fetch. A bare bibliography-style
    citation (e.g. "[... - Stack Overflow](url)" cited from a cheap web-search
    survey, with no code attributed to it) needs no proof line -- CLAUDE.md's
    own global instructions explicitly allow surveying with search snippets and
    citing the source without a full fetch. Previously this checked the whole
    report for a proof marker with no proximity relationship at all, so a single
    bare bibliography link anywhere in a long multi-aspect report would strip the
    entire report's COVERS: line, including aspects that had real proof.
    """
    violations = []

    for domain_re, proof_prefix in _DOMAIN_PROOF_MAP.items():
        proof_re = re.compile(re.escape(proof_prefix), re.IGNORECASE)
        # Find all domain citations in this report
        for match in domain_re.finditer(report):
            domain_cite = match.group()
            if "owner/repo" in domain_cite.lower():
                # Placeholder from swiper.md's own documented reporting convention
                # (e.g. "github.com/owner/repo/path" quoted while explaining the
                # format), not a real citation. A genuine citation never has this
                # exact literal path.
                continue

            window = report[match.end():_window_end(report, match.end())]
            if not _FENCE_RE.search(window):
                # No code claimed near this citation -- nothing to prove.
                continue

            # Check if the corresponding proof line exists
            if not proof_re.search(report):
                violations.append(f"{domain_cite} cited with adjacent code but no {proof_prefix} line found")
                continue

            # Proof line exists. Now check if a code block follows it.
            # Find the proof line in the report, then look for a fence after it.
            proof_pos = proof_re.search(report)
            if proof_pos:
                after_proof = report[proof_pos.end():]
                # A valid proof block: a fence that appears somewhere after the proof line
                if not _FENCE_RE.search(after_proof):
                    violations.append(f"{domain_cite} has {proof_prefix} line but no fenced code block after it")

    return violations


def _strip_covers_line(report: str) -> str:
    """Remove COVERS: line(s) from the report, leaving everything else."""
    return _COVERS_LINE_RE.sub("", report)


def _agent_type(payload: dict) -> str:
    tool_input = payload.get("tool_input", {})
    return (
        tool_input.get("subagent_type")
        or tool_input.get("agent_type")
        or tool_input.get("agent")
        or ""
    )


def _report(payload: dict) -> str:
    """The agent's report, flattened to plain text.

    tool_response is not a string. It arrives as a list of content blocks,
    [{"type": "text", "text": "..."}], and str() on that gives a Python repr
    where newlines are escaped as literal backslash-n. Anything downstream doing
    splitlines() then sees one enormous line and matches nothing, which would
    make the COVERS scope undiscoverable and leave the gate blocking every edit
    forever. Found by reading a real stamped record rather than trusting the
    shape the docs implied.

    Passed through whole rather than reduced to a verdict line, because the gate
    needs COVERS, and that's what names the files the research actually looked at.
    """
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

    if payload.get("tool_name") not in ("Task", "Agent"):
        return 0

    agent_type = _agent_type(payload)
    if agent_type not in RESEARCH_AGENTS:
        return 0

    session_id = payload.get("session_id", "")
    report = _report(payload)

    # Check if any code-source domains are cited without proof they were
    # actually fetched and read.
    violations = _missing_proof(report)
    if violations:
        report_to_record = _strip_covers_line(report)
        print(
            "[research-record] REJECTED: this report cites a code source but lacks proof "
            "of actually fetching and reading it. Missing: " + "; ".join(violations) + ". "
            "Each cited domain (GitHub, StackOverflow, etc.) needs a proof line "
            "(GITHUB_FILE_READ: owner/repo/path, STACKOVERFLOW_ANSWER_READ:, etc.) followed by "
            "a verbatim fenced code block showing the code you read. This stamp is recorded "
            "with no file scope, so the research gate will block edits to any file until "
            "swiper runs again with actual proof. Respin with the fetch and quote, or drop "
            "the citation.",
            file=sys.stderr,
        )
    else:
        report_to_record = report

    record_agent(session_id=session_id, agent_type=agent_type, report=report_to_record)
    clear_session_quick(session_id)

    return 0


if __name__ == "__main__":
    sys.exit(main())
