#!/usr/bin/env python3
"""clean-rag proof gate: PreToolUse hook on Edit|Write|MultiEdit.

Blocks file edits unless a verified proof exists in a keyed proof file.
The hook does NO AI work. It checks a state file that Claude writes
after searching RAG and passing mechanical verification checks.

Exit codes:
  0 = pass (proof verified or path exempt)
  2 = block (no proof, tell Claude what to do)
"""

import hashlib
import json
import os
import sys
import time
from pathlib import Path

# Add clean-rag root to sys.path for telemetry imports
_CLEAN_RAG_ROOT = Path(__file__).resolve().parent.parent
if str(_CLEAN_RAG_ROOT) not in sys.path:
    sys.path.insert(0, str(_CLEAN_RAG_ROOT))

try:
    from telemetry.events import gate_block as _tel_block
    from telemetry.events import gate_pass as _tel_pass
    from telemetry.events import gate_exempt as _tel_exempt
    from telemetry.events import gate_auto as _tel_auto
except ImportError:
    def _tel_block(file, reason): pass
    def _tel_pass(file, topics, score): pass
    def _tel_exempt(file, reason): pass
    def _tel_auto(file): pass


def _clean_rag_home() -> Path:
    """Resolve the clean-rag root directory."""
    env = os.environ.get("CLEAN_RAG_HOME")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent


def _read_mode() -> str:
    """Check if ClaudeBoost AUTO mode is active (bypasses all gates)."""
    cb_home = os.environ.get("CLAUDEBOOST_HOME", "")
    if not cb_home:
        return "CONSULT"
    mode_file = Path(cb_home) / "state" / "claudeboost-mode.json"
    if mode_file.exists():
        try:
            data = json.loads(mode_file.read_text(encoding="utf-8"))
            return data.get("mode", "CONSULT")
        except Exception:
            pass
    return "CONSULT"


def _canonicalize(file_path: str) -> str:
    """Resolve and normalize a file path for safe comparison.

    Returns a lowercase forward-slash POSIX path after resolving symlinks
    and relative components.
    """
    try:
        resolved = Path(file_path).resolve()
    except (OSError, ValueError):
        resolved = Path(file_path)
    return resolved.as_posix().lower()


def _path_has_segment(canonical_path: str, segment: str) -> bool:
    """Check if a path contains a segment at a directory boundary.

    Prevents false positives from substring matching. For example,
    '/my-clean-rag-tool/src/main.py' should NOT match the 'clean-rag' segment
    because 'clean-rag' is a substring inside 'my-clean-rag-tool', not a
    standalone directory name.
    """
    seg = segment.strip("/").lower()
    parts = canonical_path.split("/")
    return seg in parts


def _file_content_hash(tool_input: dict) -> str:
    """Compute a SHA-256 hash of the proposed edit content.

    Works for Edit (old_string + new_string), Write (content),
    and MultiEdit (edits array).
    """
    h = hashlib.sha256()

    if "content" in tool_input:
        h.update(tool_input["content"].encode("utf-8", errors="replace"))
    elif "old_string" in tool_input and "new_string" in tool_input:
        h.update(tool_input["old_string"].encode("utf-8", errors="replace"))
        h.update(b"\x00")
        h.update(tool_input["new_string"].encode("utf-8", errors="replace"))
    elif "edits" in tool_input:
        for edit in tool_input["edits"]:
            h.update(edit.get("old_string", "").encode("utf-8", errors="replace"))
            h.update(b"\x00")
            h.update(edit.get("new_string", "").encode("utf-8", errors="replace"))
            h.update(b"\x01")

    return h.hexdigest()


def _proof_file_for(state_dir: Path, canonical_path: str) -> Path:
    """Return the keyed proof file path for a given canonical file path.

    Each file being edited gets its own proof file, keyed by a hash of
    the canonical path. This allows concurrent edits to different files
    without one proof overwriting another.
    """
    path_hash = hashlib.sha256(canonical_path.encode("utf-8")).hexdigest()[:16]
    return state_dir / f"pending-proof-{path_hash}.json"


# Exempt path segments (checked at directory boundaries, not substrings)
EXEMPT_SEGMENTS = [
    "workspace",
    "knowledge",
    "plans",
    "docs",
    "state",
    ".claudeboost",
    ".claude",
]

# File extensions that don't need proof (documentation and config only)
# NOTE: .json, .yaml, .yml, .toml deliberately EXCLUDED to prevent
# proof file fabrication through config file writes
EXEMPT_EXTENSIONS = [
    ".md", ".mdx", ".rst", ".txt",
    ".gitignore", ".env.example",
    ".csv", ".svg",
]

# How long a verified proof stays valid (seconds)
PROOF_WINDOW_S = 120

# Minimum RAG score required for proof to be accepted
MIN_PROOF_SCORE = 0.5


BLOCK_MESSAGE = """
===================================================================
CLEAN-RAG: Edit blocked. No verified proof for this file.

  File: {file}

Before editing, you must:

1. SEARCH clean-rag for relevant research:
   POST http://127.0.0.1:{port}/search
   {{"query": "<what you need to know>", "sources": ["all_topics", "project:<path>"]}}

   You need at least one result with score >= {min_score}.
   If search returns NO results or all scores are below {min_score}:
   go to step 1b to auto-research the topic first.

1b. AUTO-RESEARCH (only when step 1 found nothing usable):
   POST http://127.0.0.1:{port}/acquire-topic
   {{"topic": "<technology-slug>"}}

   This runs the 4-layer waterfall automatically: GitHub sparse checkout,
   llms.txt check, BFS doc crawl, then indexes the results into a new
   topic database. After it completes, re-run step 1.

   If acquire-topic returns needs_websearch:true, use WebSearch to find
   authoritative docs, save them to clean-rag/knowledge/<category>/<topic>/,
   then index:
   POST http://127.0.0.1:{port}/index-topic {{"topic": "<name>", "category": "<category>"}}

2. WRITE proof to a keyed proof file using write_pending_proof():
   from clean_rag.verifier.log import write_pending_proof

   write_pending_proof(
       state_dir="clean-rag/state",
       file_path="<path to file being edited>",
       verdict="VERIFIED",
       verifier_response="<summary of RAG results that justify the edit>",
       rag_results_count=<number of RAG results used>,
       topics_cited=["<topic1>", "<topic2>"],
       project_cited=<True if project codebase was searched>,
       content_hash="<SHA-256 of the edit content>",
       min_score=<best RAG result score, must be >= {min_score}>,
   )

   content_hash: compute SHA-256 of the edit content (old_string + new_string
   for Edit, content for Write, edits array for MultiEdit).
   min_score: the highest score from your RAG search results.

3. RETRY the edit. The gate will pass if:
   - verdict == VERIFIED
   - content_hash matches the proposed edit (prevents proof reuse)
   - min_score >= {min_score}
   - timestamp is within {window}s and timezone-aware

The research you acquire is permanently saved. Next time you edit code
using the same technology, the search in step 1 will find it instantly.
No re-research, no re-downloading. Proof comes from local search.
===================================================================
"""


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError) as e:
        print(f"proof-gate: failed to parse hook payload: {e}", file=sys.stderr)
        return 2

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})

    if tool_name not in ("Edit", "Write", "MultiEdit"):
        return 0

    file_path = tool_input.get("file_path", "")
    if not file_path:
        # No file path = suspicious. Block, don't pass.
        print("proof-gate: edit with empty file_path blocked", file=sys.stderr)
        _tel_block("(empty)", "empty_file_path")
        return 2

    canonical = _canonicalize(file_path)

    # 1. Exempt path segments (directory boundary check)
    for seg in EXEMPT_SEGMENTS:
        if _path_has_segment(canonical, seg):
            _tel_exempt(file_path, f"segment:{seg}")
            return 0

    # 2. Exempt extensions (docs only, no structured data formats)
    for ext in EXEMPT_EXTENSIONS:
        if canonical.endswith(ext):
            _tel_exempt(file_path, f"extension:{ext}")
            return 0

    # 3. AUTO mode bypass (logged for audit trail)
    if _read_mode() == "AUTO":
        home = _clean_rag_home()
        _log_auto_bypass(home / "state", file_path)
        _tel_auto(file_path)
        return 0

    # 4. Check for verified proof
    home = _clean_rag_home()
    state_dir = home / "state"
    proof_path = _proof_file_for(state_dir, canonical)
    port = os.environ.get("CLEAN_RAG_PORT", "8613")

    # Compute content hash of the proposed edit
    edit_hash = _file_content_hash(tool_input)

    # Atomic proof consumption: rename to .consumed, then read.
    # If rename fails, another process already consumed it.
    consumed_path = proof_path.with_suffix(".consumed")
    try:
        os.replace(str(proof_path), str(consumed_path))
    except (OSError, FileNotFoundError):
        # No proof file exists or rename failed (already consumed)
        consumed_path = None

    if consumed_path and consumed_path.exists():
        try:
            raw = consumed_path.read_text(encoding="utf-8")
            proof = json.loads(raw)
            proof_canonical = _canonicalize(proof.get("file", ""))

            valid = True
            reasons = []

            # Check file match
            if proof_canonical != canonical:
                valid = False
                reasons.append(f"file mismatch: proof={proof_canonical}, edit={canonical}")

            # Check verdict
            if proof.get("verdict") != "VERIFIED":
                valid = False
                reasons.append(f"verdict={proof.get('verdict', 'missing')}")

            # Check freshness (timezone required)
            if not _is_fresh_strict(proof):
                valid = False
                reasons.append("timestamp expired or missing timezone")

            # Check content hash (if present in proof)
            proof_hash = proof.get("content_hash", "")
            if proof_hash and proof_hash != edit_hash:
                valid = False
                reasons.append("content_hash mismatch (edit changed after verification)")

            # Check minimum score threshold
            proof_score = proof.get("min_score", 0)
            if proof_score < MIN_PROOF_SCORE:
                valid = False
                reasons.append(f"min_score {proof_score} < {MIN_PROOF_SCORE}")

            if valid:
                _log_proof(state_dir, file_path, proof, edit_hash)
                _tel_pass(file_path, proof.get("topics_cited", []), proof.get("min_score", 0))
                # Clean up consumed file
                try:
                    consumed_path.unlink()
                except OSError:
                    pass
                return 0
            else:
                # Proof was invalid. Log why and block.
                reason_str = "; ".join(reasons)
                print(
                    f"proof-gate: proof rejected: {reason_str}",
                    file=sys.stderr,
                )
                _tel_block(file_path, f"proof_rejected: {reason_str}")
                _maybe_write_debug_fix(state_dir, file_path, f"proof_rejected: {reason_str}")
                # Clean up consumed file
                try:
                    consumed_path.unlink()
                except OSError:
                    pass

        except (json.JSONDecodeError, KeyError, OSError) as e:
            print(f"proof-gate: corrupt proof file: {e}", file=sys.stderr)
            _tel_block(file_path, f"corrupt_proof: {e}")
            # Clean up corrupt consumed file
            try:
                consumed_path.unlink()
            except OSError:
                pass

    # 5. No valid proof. Block.
    _tel_block(file_path, "no_valid_proof")
    _maybe_write_debug_fix(state_dir, file_path, "no_valid_proof")
    print(
        BLOCK_MESSAGE.format(
            file=file_path,
            port=port,
            state_dir=str(state_dir).replace("\\", "/"),
            min_score=MIN_PROOF_SCORE,
            window=PROOF_WINDOW_S,
        ),
        file=sys.stderr,
    )
    return 2


def _is_fresh_strict(proof: dict) -> bool:
    """Check if the proof timestamp is within the allowed window.

    Strict mode: rejects naive timestamps (no timezone info). A proof
    without timezone data could be from any time zone and is not trustworthy.
    """
    ts_str = proof.get("ts", "")
    if not ts_str:
        return False
    try:
        from datetime import datetime, timezone

        if ts_str.endswith("Z"):
            ts_str = ts_str[:-1] + "+00:00"

        proof_time = datetime.fromisoformat(ts_str)

        # Reject naive timestamps (no timezone)
        if proof_time.tzinfo is None:
            return False

        now = datetime.now(timezone.utc)
        age = (now - proof_time).total_seconds()

        # Reject future timestamps (clock skew attack)
        if age < -5:
            return False

        return age < PROOF_WINDOW_S
    except Exception:
        return False


def _log_proof(state_dir: Path, file_path: str, proof: dict, edit_hash: str) -> None:
    """Append the verified proof to the audit log."""
    log_path = state_dir / "proof-log.jsonl"
    entry = {
        "ts": proof.get("ts", ""),
        "file": file_path,
        "verdict": proof.get("verdict", ""),
        "verifier_response": proof.get("verifier_response", ""),
        "rag_results_count": proof.get("rag_results_count", 0),
        "topics_cited": proof.get("topics_cited", []),
        "project_cited": proof.get("project_cited", False),
        "content_hash": edit_hash,
        "min_score": proof.get("min_score", 0),
        "consumed_at": _utc_now_iso(),
    }
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def _log_auto_bypass(state_dir: Path, file_path: str) -> None:
    """Log when AUTO mode bypasses the proof gate."""
    log_path = state_dir / "proof-log.jsonl"
    entry = {
        "ts": _utc_now_iso(),
        "file": file_path,
        "verdict": "AUTO_BYPASS",
        "verifier_response": "ClaudeBoost AUTO mode active",
        "rag_results_count": 0,
        "topics_cited": [],
        "project_cited": False,
    }
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def _maybe_write_debug_fix(state_dir: Path, file_path: str, reason: str) -> None:
    """If debug mode is active, write a fix-required file.

    When debug-mode.json exists, every proof-gate block also creates
    debug-fix-required.json. The debug-gate hook reads this file and
    blocks all non-clean-rag edits until the enforcement gap is fixed.
    """
    debug_mode = state_dir / "debug-mode.json"
    if not debug_mode.exists():
        return
    fix_file = state_dir / "debug-fix-required.json"
    fix_data = {
        "ts": _utc_now_iso(),
        "file_blocked": file_path,
        "mistake_type": _classify_mistake(reason),
        "reason": reason,
        "fix_instruction": _fix_instruction_for(reason),
    }
    try:
        fix_file.write_text(json.dumps(fix_data, indent=2), encoding="utf-8")
    except OSError:
        pass


def _classify_mistake(reason: str) -> str:
    """Categorize a proof-gate rejection into a mistake type."""
    if "content_hash" in reason:
        return "content_hash_mismatch"
    if "min_score" in reason:
        return "insufficient_research"
    if "verdict" in reason:
        return "protocol_violation"
    if "timestamp" in reason or "expired" in reason:
        return "stale_proof"
    if "corrupt" in reason:
        return "corrupt_proof"
    return "missing_proof"


def _fix_instruction_for(reason: str) -> str:
    """Generate a specific fix instruction based on the mistake type."""
    if "content_hash" in reason:
        return (
            "The content hash in the proof didn't match the actual edit. "
            "This means the proof was written for different content than "
            "what the tool is sending. Research how the tool serializes "
            "content and update the hash computation to match."
        )
    if "min_score" in reason:
        return (
            "The RAG search didn't return strong enough results (score < 0.5). "
            "The topic may not be indexed, or the query was too vague. "
            "Run acquire-topic to index docs for this technology, then "
            "re-search with a more specific query."
        )
    if "verdict" in reason:
        return (
            "The proof was written without VERIFIED verdict. "
            "Search RAG, confirm results have score >= 0.5, then "
            "write proof with verdict='VERIFIED'."
        )
    if "timestamp" in reason or "expired" in reason:
        return (
            "The proof expired (older than 120s) or had no timezone. "
            "Write the proof immediately before retrying the edit. "
            "Use timezone-aware timestamps (UTC with Z suffix)."
        )
    if "corrupt" in reason:
        return (
            "The proof file was corrupt (invalid JSON or missing fields). "
            "Use write_pending_proof() from verifier/log.py which handles "
            "formatting correctly."
        )
    return (
        "No proof file was found for this edit. Search RAG first, "
        "get results with score >= 0.5, write proof with "
        "write_pending_proof(), then retry the edit."
    )


def _utc_now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    sys.exit(main())
