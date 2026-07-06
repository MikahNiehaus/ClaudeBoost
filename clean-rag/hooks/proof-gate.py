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
import socket
import sys
import tempfile
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


def _is_temp_path(canonical_path: str) -> bool:
    """Check if a file is in a system temp directory.

    Covers Windows %TEMP%, %TMP%, Unix /tmp, /var/tmp, and Python's
    tempfile.gettempdir(). Files in temp dirs are transient scratch
    space and should never require research proof.
    """
    temp_dirs = set()

    # Python's canonical temp dir (covers most cases)
    try:
        temp_dirs.add(Path(tempfile.gettempdir()).resolve().as_posix().lower())
    except Exception:
        pass

    # Environment variables (Windows: TEMP, TMP; Unix: TMPDIR)
    for var in ("TEMP", "TMP", "TMPDIR"):
        val = os.environ.get(var)
        if val:
            try:
                temp_dirs.add(Path(val).resolve().as_posix().lower())
            except Exception:
                pass

    # Common Unix temp paths
    for d in ("/tmp", "/var/tmp"):
        try:
            p = Path(d)
            if p.exists():
                temp_dirs.add(p.resolve().as_posix().lower())
        except Exception:
            pass

    for td in temp_dirs:
        if canonical_path.startswith(td + "/") or canonical_path == td:
            return True
    return False


def _is_outside_any_repo(file_path: str) -> bool:
    """Check if a file is outside any git repository.

    Files not under version control are scratch/output files. They
    don't benefit from research enforcement and blocking them just
    creates friction.
    """
    try:
        current = Path(file_path).resolve().parent
    except (OSError, ValueError):
        return False

    for _ in range(15):
        if (current / ".git").exists():
            return False
        parent = current.parent
        if parent == current:
            break
        current = parent

    return True


def _server_reachable(port: str) -> bool:
    """Quick TCP check to see if the clean-rag server is listening."""
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=0.5):
            return True
    except (OSError, ValueError):
        return False


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


def _detect_project_root(file_path: str) -> str | None:
    """Walk up from a file path to find the project root.

    First pass: look for .git (strongest signal, always at repo root).
    Second pass (only if no .git found): look for package.json, pyproject.toml,
    etc. Returns the absolute path string or None.
    """
    try:
        start = Path(file_path).resolve().parent
    except (OSError, ValueError):
        return None

    # Pass 1: .git is the definitive project root marker
    current = start
    for _ in range(10):
        if (current / ".git").exists():
            return str(current)
        parent = current.parent
        if parent == current:
            break
        current = parent

    # Pass 2: fallback markers (for non-git projects)
    fallback_markers = [
        "package.json", "pyproject.toml", "Cargo.toml",
        "go.mod", "pom.xml", "build.gradle",
    ]
    glob_exts = [".sln", ".csproj"]

    current = start
    for _ in range(10):
        for marker in fallback_markers:
            if (current / marker).exists():
                return str(current)
        for ext in glob_exts:
            if any(current.glob(f"*{ext}")):
                return str(current)
        parent = current.parent
        if parent == current:
            break
        current = parent

    return None


def _check_project_indexed(project_root: str) -> dict | None:
    """Check if a project is in the clean-rag project registry.

    Returns the project entry dict if indexed, None otherwise.
    """
    home = _clean_rag_home()
    reg_path = home / "state" / "projects.json"
    if not reg_path.exists():
        return None
    try:
        registry = json.loads(reg_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    # Check each registered project to see if it matches
    proj_resolved = Path(project_root).resolve()
    for pid, info in registry.items():
        reg_path_str = info.get("project_path", "")
        if not reg_path_str:
            continue
        try:
            reg_resolved = Path(reg_path_str).resolve()
            if reg_resolved == proj_resolved:
                return info
        except (OSError, ValueError):
            continue

    return None


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

# How long a verified proof stays valid (seconds)
PROOF_WINDOW_S = 120

# Minimum RAG score required for proof to be accepted
MIN_PROOF_SCORE = 0.5

# Minimum number of research angles required in proof
MIN_RESEARCH_ANGLES = 2

# Minimum number of quality aspects required in proof
MIN_QUALITY_ASPECTS = 2

# Quality aspects that count as "macro" (project fit, not just code correctness)
MACRO_QUALITY_ASPECTS = {"architecture", "patterns"}


BLOCK_MESSAGE = """
===================================================================
CLEAN-RAG: Edit blocked. No verified proof for this file.

  File: {file}
  Expected proof: {state_dir}/{proof_file}

Before editing, you must:

1. SEARCH clean-rag for relevant research:
   POST http://127.0.0.1:{port}/search
   {{"query": "<what you need to know>", "sources": ["all_topics", "project:<path>"]}}

   You need at least one result with score >= {min_score}.

2. IF SEARCH RETURNED NOTHING (or scores below {min_score}):
   Do DIRECT research NOW. This is the fast path (seconds, not minutes):

   a) Grep the codebase for existing patterns (counts as "codebase" angle)
   b) Read a specific doc file or use WebSearch for the technology question
   c) Save what you found to clean-rag/knowledge/<category>/<topic>/
      (even one file is enough)
   d) Quick-index: POST http://127.0.0.1:{port}/index-topic
      {{"topic": "<name>", "category": "<category>"}}
      (indexes a few files in under 2 seconds)
   e) Re-search the newly indexed topic (will get high score now)

   ALSO: spawn a background Agent to run acquire-topic for full coverage.
   Do NOT wait for it. The background agent fills the database for future
   queries while you continue working now.

3. WRITE proof using write_pending_proof():
   from clean_rag.verifier.log import write_pending_proof

   write_pending_proof(
       state_dir="clean-rag/state",
       file_path="<path to file being edited>",
       verdict="VERIFIED",
       verifier_response="<summary of research that justifies the edit>",
       rag_results_count=<number of results>,
       topics_cited=["<topic1>"],
       project_cited=<True if codebase was searched>,
       content_hash="<SHA-256 of the edit content>",
       min_score=<best score, must be >= {min_score}>,
       research_angles=[
           {{"angle": "technology", "query": "<what you searched>", "score": <score>}},
           {{"angle": "codebase", "query": "<how you searched project>", "score": <score>}},
       ],
       quality_aspects=[
           {{"aspect": "architecture", "assertion": "<how the change fits the project structure>"}},
           {{"aspect": "patterns", "assertion": "<which existing patterns this follows>"}},
       ],
   )

4. RETRY the edit. The gate passes if:
   - verdict == VERIFIED
   - min_score >= {min_score}
   - research_angles has >= 2 entries, including at least one with angle="codebase"
     (you MUST search callers, imports, and dependents of the target file)
   - quality_aspects has >= 2 entries, at least one with aspect="architecture" or "patterns"
     (you MUST consider whether the code fits the project, not just whether it works)
   - timestamp is within {window}s and timezone-aware
   (content_hash is tracked for audit but not required, allowing legitimate edit revisions)

{index_guidance}
===================================================================
"""

BLOCK_MESSAGE_SERVER_DOWN = """
===================================================================
CLEAN-RAG: Edit blocked. No verified proof for this file.

  File: {file}
  Server: NOT RUNNING (port {port} unreachable)

The clean-rag server must be running to search for proof. Start it:
  python clean-rag/cli/server_ctl.py start

Or start it from the project root:
  python -m clean_rag.server

After the server starts, search for research, write proof, then retry.
===================================================================
"""

# Appended to BLOCK_MESSAGE when the project is NOT indexed
INDEX_GUIDANCE_NOT_INDEXED = """PROJECT INDEX STATUS: NOT INDEXED
  Project root detected: {project_root}
  This project's code is not in the clean-rag index. You have two options:

  Option A (recommended): Index the project first, then use it as a codebase angle:
    POST http://127.0.0.1:{port}/index-project
    {{"project_path": "{project_root}"}}
    Then search with: "sources": ["all_topics", "project:{project_root}"]

  Option B (immediate fallback): Use Grep as the codebase research angle.
    Search the project with Grep for existing patterns, then cite the
    grep results as your "codebase" angle in the proof. This works now
    but won't build a reusable index for future edits."""

# Appended when the project IS indexed
INDEX_GUIDANCE_INDEXED = """PROJECT INDEX STATUS: INDEXED
  Project root: {project_root}
  Include "project:{project_root}" in your search sources for the codebase angle.
  Example: "sources": ["topic:fastapi", "project:{project_root}"]"""

# Appended when we can't detect the project root
INDEX_GUIDANCE_UNKNOWN = """PROJECT INDEX STATUS: UNKNOWN
  Could not detect the project root for this file.
  For the codebase research angle, use Grep to search the project
  directory for existing patterns, then cite grep results in the proof."""


def _build_remediation_for_reasons(reasons: list) -> str:
    """Build actionable remediation steps for each validation failure."""
    lines = ["Proof validation failed:"]
    for reason in reasons:
        if "verdict" in reason:
            lines.append(f"  Verdict: {reason}")
            lines.append(f"    Fix: Set verdict to 'VERIFIED' in your proof file")
        elif "min_score" in reason:
            lines.append(f"  Score: {reason}")
            lines.append(f"    Fix: Search RAG again for results with score >= 0.5")
        elif "missing 'codebase' angle" in reason:
            lines.append(f"  Codebase context: {reason}")
            lines.append(f"    Fix: Search the surrounding codebase (callers, imports, files that depend on")
            lines.append(f"    the target) and include an angle with angle='codebase' in your proof")
        elif "research_angles" in reason:
            lines.append(f"  Angles: {reason}")
            lines.append(f"    Fix: Add research angles including at least one 'codebase' angle (callers, imports, dependents)")
        elif "missing macro quality" in reason:
            lines.append(f"  Quality: {reason}")
            lines.append(f"    Fix: Include at least one quality aspect with aspect='architecture' or")
            lines.append(f"    aspect='patterns' to prove the code fits the project structure")
        elif "quality_aspects" in reason:
            lines.append(f"  Quality: {reason}")
            lines.append(f"    Fix: Add quality_aspects to your proof with at least 2 entries.")
            lines.append(f"    Each entry: {{\"aspect\": \"<name>\", \"assertion\": \"<what you verified>\"}}")
            lines.append(f"    Aspects: architecture, patterns, maintainability, security, performance, testing")
            lines.append(f"    At least one must be 'architecture' or 'patterns' (macro quality)")
        elif "timestamp" in reason:
            lines.append(f"  Timestamp: {reason}")
            lines.append(f"    Fix: Create a fresh proof file (must be within 120 seconds)")
        else:
            lines.append(f"  {reason}")
    return "\n".join(lines)


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

    # 2. Exempt temp directories (scratch files, handoff docs, etc.)
    if _is_temp_path(canonical):
        _tel_exempt(file_path, "temp_directory")
        return 0

    # 2c. Exempt files outside any git repository (not project code)
    if _is_outside_any_repo(file_path):
        _tel_exempt(file_path, "outside_git_repo")
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

            # Note: content_hash is informational only (tracked for audit trail).
            # We do NOT block on content_hash mismatch because:
            # Freshness window (120s) prevents stale proof reuse (replay protection)
            # Users may legitimately revise their edit after writing proof
            # See clean-rag/CLAUDE.md line 20 for design rationale update

            # Check minimum score threshold
            proof_score = proof.get("min_score", 0)
            if proof_score < MIN_PROOF_SCORE:
                valid = False
                reasons.append(f"min_score {proof_score} < {MIN_PROOF_SCORE}")

            # Check research angles (multiple perspectives required)
            angles = proof.get("research_angles", [])
            if len(angles) < MIN_RESEARCH_ANGLES:
                valid = False
                reasons.append(
                    f"research_angles: {len(angles)} provided, need >= {MIN_RESEARCH_ANGLES}"
                )

            # Require at least one "codebase" angle (callers, imports, dependents)
            has_codebase = any(
                isinstance(a, dict) and a.get("angle") == "codebase"
                for a in angles
            )
            if not has_codebase:
                valid = False
                reasons.append(
                    "research_angles: missing 'codebase' angle. "
                    "You must search the surrounding codebase (callers, imports, "
                    "dependents) before editing, not just the target file"
                )

            # Require quality aspects (code quality proof at multiple levels)
            quality = proof.get("quality_aspects", [])
            if len(quality) < MIN_QUALITY_ASPECTS:
                valid = False
                reasons.append(
                    f"quality_aspects: {len(quality)} provided, need >= {MIN_QUALITY_ASPECTS}. "
                    "You must consider code quality from multiple angles before editing: "
                    "architecture, patterns, maintainability, security, performance, testing"
                )

            # At least one must be architecture or patterns (macro quality)
            if quality:
                has_macro = any(
                    isinstance(q, dict)
                    and q.get("aspect") in MACRO_QUALITY_ASPECTS
                    for q in quality
                )
                if not has_macro:
                    valid = False
                    reasons.append(
                        "quality_aspects: missing macro quality aspect. "
                        "At least one aspect must be 'architecture' or 'patterns' "
                        "to prove the code fits the project structure, not just "
                        "that it works correctly"
                    )

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
                # Proof was invalid. Show specific failures with remediation.
                reason_str = "; ".join(reasons)
                remediation = _build_remediation_for_reasons(reasons)
                print(
                    f"proof-gate: proof rejected\n{remediation}",
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

    # 5. No valid proof. Check server health and block with guidance.
    _tel_block(file_path, "no_valid_proof")
    _maybe_write_debug_fix(state_dir, file_path, "no_valid_proof")

    if not _server_reachable(port):
        # Server is down. Give a clear "start the server" message
        # instead of instructions that reference an unreachable server.
        print(
            BLOCK_MESSAGE_SERVER_DOWN.format(file=file_path, port=port),
            file=sys.stderr,
        )
        return 2

    # Server is up. Show full research instructions with expected proof path.
    index_guidance = _build_index_guidance(file_path, port)
    proof_path = _proof_file_for(state_dir, canonical)

    print(
        BLOCK_MESSAGE.format(
            file=file_path,
            port=port,
            state_dir=str(state_dir).replace("\\", "/"),
            min_score=MIN_PROOF_SCORE,
            window=PROOF_WINDOW_S,
            index_guidance=index_guidance,
            proof_file=proof_path.name,
        ),
        file=sys.stderr,
    )
    return 2


def _build_index_guidance(file_path: str, port: str) -> str:
    """Build the index guidance section for the block message.

    Detects the project root and checks whether it's indexed, then
    returns the appropriate guidance text.
    """
    project_root = _detect_project_root(file_path)

    if not project_root:
        return INDEX_GUIDANCE_UNKNOWN

    info = _check_project_indexed(project_root)

    if info:
        return INDEX_GUIDANCE_INDEXED.format(
            project_root=project_root.replace("\\", "/"),
            port=port,
        )
    else:
        return INDEX_GUIDANCE_NOT_INDEXED.format(
            project_root=project_root.replace("\\", "/"),
            port=port,
        )


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
    if "research_angles" in reason:
        return "insufficient_angles"
    if "quality_aspects" in reason or "macro quality" in reason:
        return "insufficient_quality"
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
    if "research_angles" in reason:
        return (
            "The proof needs at least 2 research angles. Each angle is a "
            "different search perspective: technology (how it works), "
            "codebase (existing patterns), pitfalls (common mistakes), "
            "security (implications), or best_practices (recommended approach). "
            "Search from multiple angles, then include them in the proof."
        )
    if "quality_aspects" in reason or "macro quality" in reason:
        return (
            "The proof needs at least 2 quality aspects proving you considered "
            "code quality at multiple levels. Each aspect is "
            '{"aspect": "<name>", "assertion": "<what you verified>"}. '
            "Valid aspects: architecture (right file, right layer), "
            "patterns (follows existing project patterns), "
            "maintainability (clear, low coupling), security (no vulns), "
            "performance (no unnecessary cost), testing (how to test it). "
            "At least one must be 'architecture' or 'patterns' (macro quality)."
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
