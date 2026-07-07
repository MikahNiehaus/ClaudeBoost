"""Local-only proof verification for when the clean-rag server is unreachable.

POST /log-direct-research (server/app.py) can't help here -- it's an HTTP
endpoint on the very server that's down. This script does the same kind of
independent verification (file existence, a real regex match count) but
entirely locally, so it works even with the server dead. Mirrors
server/app.py's handle_log_direct_research: verifies claims itself instead
of trusting a self-reported description, then only writes a proof if the
checks genuinely pass.

Security-sensitive files (auth/session/token/password/crypto/secret/api-key
paths) are refused here unconditionally -- per the OWASP-grounded decision
in the plan (RAG pipeline failures should fail closed for access-control-
relevant checks), those edits must wait for the server to come back, not go
through the offline path. proof-gate.py also checks this before ever
offering the offline path, but this script refuses independently too, so
it can't be misused by calling it directly.

Usage: reads a JSON payload from stdin:
{
  "file_path": "<path to the file being edited>",
  "checks": [
    {"files_examined": ["a.py"], "method": "grep", "pattern": "foo"},
    {"files_examined": ["b.py"], "method": "read"}
  ],
  "quality_aspects": [
    {"aspect": "architecture", "assertion": "..."},
    {"aspect": "patterns", "assertion": "..."}
  ]
}

Prints a JSON result to stdout and exits 0 on success, or prints an error
to stderr and exits 1 without writing anything on failure.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verifier.log import write_pending_proof  # noqa: E402

_STATE_DIR = Path(__file__).resolve().parent.parent / "state"
_RAG_DOWN_LOG = _STATE_DIR / "rag-down-events.jsonl"
_MIN_CHECKS = 2
_VERIFIED_SCORE = 1.0  # same reasoning as app.py's _DIRECT_RESEARCH_SCORE

# Kept in sync manually with app.py's security-sensitive pattern list
# (Stage 6) -- both need to agree on what counts as security-sensitive.
_SECURITY_PATH_RE = re.compile(
    r"(auth|session|token|password|passwd|crypto|secret|api[_-]?key)",
    re.IGNORECASE,
)


def _is_security_sensitive(file_path: str) -> bool:
    return bool(_SECURITY_PATH_RE.search(file_path))


def _grep_files(pattern: str, files: list[str]) -> int:
    """Same verification logic as server/app.py's _grep_files -- real regex
    matches against real file content, not a claim."""
    try:
        compiled = re.compile(pattern)
    except re.error:
        return -1
    total = 0
    for f in files:
        try:
            text = Path(f).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        total += len(compiled.findall(text))
    return total


def _log_rag_down_event(file_path: str, checks: list[dict]) -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "file": file_path,
        "reason": "clean-rag server unreachable, offline verification used",
        "checks": checks,
    }
    try:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(_RAG_DOWN_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError) as e:
        print(json.dumps({"error": f"invalid JSON on stdin: {e}"}), file=sys.stderr)
        return 1

    file_path = payload.get("file_path", "").strip()
    if not file_path:
        print(json.dumps({"error": "missing 'file_path'"}), file=sys.stderr)
        return 1

    if _is_security_sensitive(file_path):
        print(json.dumps({
            "error": (
                f"'{file_path}' matches a security-sensitive path pattern "
                "(auth/session/token/password/crypto/secret/api-key). Offline "
                "verification is refused for security-relevant files -- this "
                "edit must wait for the clean-rag server to come back up, per "
                "the fail-closed policy for access-control-relevant changes."
            ),
        }), file=sys.stderr)
        return 1

    checks = payload.get("checks", [])
    if not isinstance(checks, list) or len(checks) < _MIN_CHECKS:
        print(json.dumps({
            "error": f"checks must be a list of >= {_MIN_CHECKS} entries",
        }), file=sys.stderr)
        return 1

    quality_aspects = payload.get("quality_aspects", [])
    if not isinstance(quality_aspects, list) or len(quality_aspects) < 2:
        print(json.dumps({
            "error": "quality_aspects must be a list of >= 2 {aspect, assertion} entries",
        }), file=sys.stderr)
        return 1
    macro = {"architecture", "patterns"}
    if not any(isinstance(q, dict) and q.get("aspect") in macro for q in quality_aspects):
        print(json.dumps({
            "error": "quality_aspects must include at least one aspect='architecture' or 'patterns'",
        }), file=sys.stderr)
        return 1

    verified_checks = []
    for i, check in enumerate(checks):
        files_examined = check.get("files_examined", [])
        method = check.get("method", "")
        pattern = check.get("pattern", "")

        if not isinstance(files_examined, list) or not files_examined:
            print(json.dumps({"error": f"check {i}: files_examined must be non-empty"}), file=sys.stderr)
            return 1
        if method not in ("grep", "read"):
            print(json.dumps({"error": f"check {i}: method must be 'grep' or 'read'"}), file=sys.stderr)
            return 1

        missing = [f for f in files_examined if not Path(f).is_file()]
        if missing:
            print(json.dumps({
                "error": f"check {i}: files do not exist, cannot verify: {missing}",
            }), file=sys.stderr)
            return 1

        match_count = None
        if method == "grep":
            if not pattern:
                print(json.dumps({"error": f"check {i}: pattern required for method='grep'"}), file=sys.stderr)
                return 1
            match_count = _grep_files(pattern, files_examined)
            if match_count < 0:
                print(json.dumps({"error": f"check {i}: '{pattern}' is not a valid regex"}), file=sys.stderr)
                return 1
            if match_count == 0:
                print(json.dumps({
                    "error": f"check {i}: pattern {pattern!r} matched zero times, cannot verify",
                }), file=sys.stderr)
                return 1

        verified_checks.append({
            "files_examined": files_examined,
            "method": method,
            "pattern": pattern,
            "match_count": match_count,
        })

    research_angles = [
        {
            "angle": "codebase",
            "query": c["pattern"] if c["method"] == "grep" else f"read {c['files_examined'][0]}",
            "score": _VERIFIED_SCORE,
        }
        for c in verified_checks
    ]

    proof_path = write_pending_proof(
        state_dir=str(_STATE_DIR),
        file_path=file_path,
        verdict="VERIFIED",
        verifier_response=(
            f"Offline-verified (clean-rag server unreachable): {len(verified_checks)} real local "
            "check(s), each independently verified (file existence + regex match count) by this "
            "script, not self-reported. " + json.dumps(verified_checks)
        ),
        rag_results_count=len(verified_checks),
        topics_cited=[],
        project_cited=True,
        content_hash="",
        min_score=_VERIFIED_SCORE,
        research_angles=research_angles,
        quality_aspects=quality_aspects,
    )

    _log_rag_down_event(file_path, verified_checks)

    print(json.dumps({
        "verdict": "VERIFIED",
        "proof_path": str(proof_path),
        "offline": True,
        "checks_verified": len(verified_checks),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
