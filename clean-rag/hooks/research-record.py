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

_FENCE_RE = re.compile(r"```[ \t]*\w*\r?\n(?:(?!```).)+?\r?\n?```", re.DOTALL)
_COVERS_LINE_RE = re.compile(r"^COVERS:.*$", re.MULTILINE | re.IGNORECASE)


def _missing_proof(report: str) -> list:
    """List of domains cited without fetch proof (line + code block).

    Returns a list of violation descriptions, e.g. ["GitHub repo cited but no GITHUB_FILE_READ: line"].
    Empty list means no violations.
    """
    violations = []

    for domain_re, proof_prefix in _DOMAIN_PROOF_MAP.items():
        # Find all domain citations in this report
        for match in domain_re.finditer(report):
            domain_cite = match.group()
            # Check if the corresponding proof line exists
            proof_re = re.compile(re.escape(proof_prefix), re.IGNORECASE)
            if not proof_re.search(report):
                violations.append(f"{domain_cite} cited but no {proof_prefix} line found")
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


_MATCH_STRATEGY_RE = re.compile(r"^MATCH_STRATEGY:\s*clone-and-patch\s*$", re.MULTILINE | re.IGNORECASE)
_WRITTEN_TO_RE = re.compile(r"written to", re.IGNORECASE)
_GIT_CLONE_RE = re.compile(r"git clone https?://\S+", re.IGNORECASE)


def _missing_write_proof(report: str, covers: list) -> list:
    """List of violations when clone-and-patch is declared but nothing was actually placed.

    Only fires when MATCH_STRATEGY: clone-and-patch is declared AND the COVERS
    scope names at least one concrete file (no "*"), since a glob-only scope
    means a brand new project with no known target file yet (swiper.md's
    documented escape hatch). A "written to <file>" marker (direct placement)
    or a recommended `git clone` command (swiper.md's documented fallback for
    "take the whole repo") both count as proof something was actually done,
    not just reported. Empty list means no violations.
    """
    if not _MATCH_STRATEGY_RE.search(report):
        return []

    concrete_files = [f for f in covers if "*" not in f]
    if not concrete_files:
        return []

    if not _WRITTEN_TO_RE.search(report) and not _GIT_CLONE_RE.search(report):
        return [
            "MATCH_STRATEGY: clone-and-patch declared against known file(s) but no "
            "'written to <file>' proof or 'git clone' command found — code must be "
            "placed with Write/Edit, or a real clone command recommended, not just quoted"
        ]

    return []


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

    # Check if any code-source domains are cited without proof
    violations = _missing_proof(report)
    if violations:
        report_to_record = _strip_covers_line(report)
        print(
            "[research-record] REJECTED: this report cites a code source but lacks proof "
            "of actually downloading and reading it. Missing: " + "; ".join(violations) + ". "
            "Each cited domain (GitHub, StackOverflow, etc.) needs a proof line "
            "(GITHUB_FILE_READ: owner/repo/path, STACKOVERFLOW_ANSWER_READ:, etc.) followed by "
            "a verbatim fenced code block showing the code you read. This stamp is recorded with "
            "no file scope, so the research gate will block edits to any file until swiper "
            "runs again with actual proof. Respin with the fetch and quote, or drop the citation.",
            file=sys.stderr,
        )
    else:
        report_to_record = report

    record_agent(session_id=session_id, agent_type=agent_type, report=report_to_record)

    return 0


if __name__ == "__main__":
    sys.exit(main())
