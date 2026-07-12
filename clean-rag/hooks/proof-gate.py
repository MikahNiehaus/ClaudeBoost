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
import re
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

# Kept in sync manually with verifier/offline_prove.py's copy of this same
# pattern -- both need to agree on what counts as security-sensitive, since
# offline_prove.py refuses independently too (defense in depth, not just
# relying on this check happening first).
_SECURITY_PATH_RE = re.compile(
    r"(auth|session|token|password|passwd|crypto|secret|api[_-]?key)", re.IGNORECASE,
)


def _is_security_sensitive_path(file_path: str) -> bool:
    return bool(_SECURITY_PATH_RE.search(file_path))

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
CLEAN-RAG: Edit blocked, no verified proof for {file}.
Expected proof: {state_dir}/{proof_file}

1. SEARCH: POST http://127.0.0.1:{port}/search {{"query": "<what you need>", "sources": ["all_topics", "project:<path>"]}} -- need score >= {min_score}.
   Nothing found? Grep/Read/WebSearch directly (counts as research), optionally POST /index-topic {{"topic":"<name>","category":"<cat>"}} to persist it, then re-search.

2. PROVE: POST http://127.0.0.1:{port}/prove {{"file_path": "<file>", "search_ids": ["<id1>", "<id2>"], "quality_aspects": [{{"aspect":"architecture","assertion":"<fits project how>"}}, {{"aspect":"patterns","assertion":"<follows what existing pattern>"}}]}}
   search_ids must be real (from step 1's responses, logged server-side, <=30min old). Needs >=2 angles incl. one "codebase" (a project:<path> search). Needs >=2 quality_aspects incl. one "architecture" or "patterns". Do not call write_pending_proof() yourself -- only /prove's own server-side check counts.
{methodology_guidance}
3. RETRY the edit once /prove returns verdict VERIFIED. (Also checks: min_score >= {min_score}, timestamp within {window}s and timezone-aware.)
{index_guidance}
"""

BLOCK_MESSAGE_SERVER_DOWN = """
===================================================================
CLEAN-RAG: Edit blocked. No verified proof for this file, and the
clean-rag server is unreachable (port {port}).

  File: {file}

This does NOT have to block you -- server downtime should never stop real
work. But the server needs to actually get fixed, not just worked around
every time, so do both:

1. SPAWN clean-rag-doctor-agent via the Task tool right now, in the
   background, to diagnose and restart the server. (Same nudge
   rag-enforce.py already gives on the health-check path -- this is the
   PreToolUse path hitting the same problem, so it gets the same fix.)

2. WHILE that runs, verify your research locally instead of waiting:
   python clean-rag/verifier/offline_prove.py < payload.json
   where payload.json is:
   {{"file_path": "{file}",
     "checks": [
       {{"files_examined": ["<file you greped>"], "method": "grep", "pattern": "<what you searched>"}},
       {{"files_examined": ["<another file>"], "method": "read"}}
     ],
     "quality_aspects": [
       {{"aspect": "architecture", "assertion": "<how this fits the project>"}},
       {{"aspect": "patterns", "assertion": "<what existing pattern this follows>"}}
     ]}}

   This verifies your claims itself (real file existence, real regex match
   counts) before writing a proof -- same principle as /prove, just
   running locally since the server can't. Needs >=2 checks, same as
   /prove needs >=2 search_ids. Every offline-verified proof gets logged to
   clean-rag/state/rag-down-events.jsonl so this doesn't go unnoticed.

3. RETRY the edit once the script reports success.

===================================================================
"""

BLOCK_MESSAGE_SERVER_DOWN_SECURITY = """
===================================================================
CLEAN-RAG: Edit blocked. This file matches a security-sensitive path
(auth/session/token/password/crypto/secret/api-key), and the clean-rag
server is unreachable (port {port}).

  File: {file}

Unlike other files, there is no offline path for security-sensitive edits.
Per OWASP's RAG security guidance ("the system must deny the request rather
than fall back to potentially unsafe behavior" when a RAG pipeline
component fails), this fails CLOSED, not open -- this edit must wait.

1. SPAWN clean-rag-doctor-agent via the Task tool right now to fix the
   server. This is the only path forward for this file.
2. Once the server is back, search for real research and retry through the
   normal /prove flow.

If this file was flagged incorrectly (not actually security-relevant),
that's a real finding worth telling the user about, not something to work
around here.
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
  Include "project:{project_root}" in your search sources with mode="both" for the codebase angle.
  mode="both" runs vector + graph search together, finding semantically similar code AND
  structural neighbors (what imports this file, what calls its functions, what inherits from it).
  Example: "sources": ["topic:fastapi", "project:{project_root}"], "mode": "both" """

# Appended when we can't detect the project root
INDEX_GUIDANCE_UNKNOWN = """PROJECT INDEX STATUS: UNKNOWN
  Could not detect the project root for this file.
  For the codebase research angle, use Grep to search the project
  directory for existing patterns, then cite grep results in the proof."""


METHODOLOGY_TOPICS = {
    "baseline": ["clean-code-principles", "code-smells"],
    "class_structure": ["solid-principles", "design-patterns"],
    "api": ["api-design", "error-handling"],
    "test": ["testing-strategy"],
    "config": ["configuration-management"],
    "database": ["database-design"],
    "performance": ["performance-optimization"],
    "concurrency": ["concurrency"],
}

_SOURCE_EXTS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".cs", ".java", ".go", ".rs",
    ".rb", ".php", ".swift", ".kt", ".scala", ".cpp", ".c", ".h",
}

_API_PATTERNS = {"route", "endpoint", "controller", "api", "handler", "view"}
_DB_PATTERNS = {"model", "migration", "schema", "database", "db", "query", "orm"}
_TEST_PATTERNS = {"test", "spec", "tests", "specs", "__tests__"}
_CONFIG_PATTERNS = {"config", "settings", "env"}
_PERF_PATTERNS = {"cache", "queue", "worker", "batch", "stream"}
_CONCURRENCY_PATTERNS = {"async", "thread", "parallel", "concurrent", "lock"}


def _suggest_methodology_topics(file_path: str, tool_input: dict) -> list[str]:
    """Suggest relevant methodology topics based on the file being edited.

    Returns 2 to 4 topic slugs most relevant to the file type.
    """
    topics = list(METHODOLOGY_TOPICS["baseline"])
    path_lower = file_path.lower().replace("\\", "/")
    ext = Path(file_path).suffix.lower()

    if ext not in _SOURCE_EXTS:
        return topics

    path_parts = set(path_lower.split("/"))

    # Check edit content for class/module structure keywords
    content = tool_input.get("content", "") + tool_input.get("new_string", "")
    if any(kw in content for kw in ("class ", "interface ", "abstract ", "extends ", "implements ")):
        topics.extend(METHODOLOGY_TOPICS["class_structure"])

    if path_parts & _API_PATTERNS:
        topics.extend(METHODOLOGY_TOPICS["api"])
    if path_parts & _DB_PATTERNS:
        topics.extend(METHODOLOGY_TOPICS["database"])
    if path_parts & _TEST_PATTERNS:
        topics.extend(METHODOLOGY_TOPICS["test"])
    if path_parts & _CONFIG_PATTERNS:
        topics.extend(METHODOLOGY_TOPICS["config"])
    if path_parts & _PERF_PATTERNS:
        topics.extend(METHODOLOGY_TOPICS["performance"])
    if path_parts & _CONCURRENCY_PATTERNS:
        topics.extend(METHODOLOGY_TOPICS["concurrency"])

    seen = set()
    unique = []
    for t in topics:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique[:4]


def _is_new_or_substantial_addition(file_path: str, tool_input: dict) -> bool:
    """Heuristic trigger for the Stage 6 prior-art check: a brand new file,
    or an edit that goes from near-nothing to a large block of new code --
    not exact, just a reasonable signal for "scaffolding something new"
    as opposed to a small fix or refactor.
    """
    if "content" in tool_input:
        try:
            already_exists = Path(file_path).exists()
        except OSError:
            already_exists = True  # unknown -- don't flag on uncertainty
        return not already_exists and len(tool_input.get("content", "")) > 200
    if "old_string" in tool_input and "new_string" in tool_input:
        old_s = tool_input.get("old_string", "")
        new_s = tool_input.get("new_string", "")
        return len(old_s) < 10 and len(new_s) > 200
    if "edits" in tool_input:
        for e in tool_input["edits"]:
            if len(e.get("old_string", "")) < 10 and len(e.get("new_string", "")) > 200:
                return True
    return False


# Keywords that count as an explicit "checked for prior art, building
# custom is the right call" justification in a quality_aspects assertion.
# Simple substring matching (proof-gate.py has no AI judge), same pattern
# as app.py's _has_no_callers_acknowledgment.
_PRIOR_ART_KEYWORDS = (
    "no existing library", "no suitable library", "checked for existing",
    "no existing solution", "custom because", "building custom because",
    "core differentiat", "no library found", "searched for existing",
    "no existing pattern",
)


def _has_prior_art_justification(quality_aspects: list) -> bool:
    for q in quality_aspects:
        if not isinstance(q, dict):
            continue
        text = str(q.get("assertion", "")).lower()
        if any(kw in text for kw in _PRIOR_ART_KEYWORDS):
            return True
    return False


def _gate_mode() -> str:
    """Read the edit-gate enforcement mode.

    'pretooluse' (default): every Edit/Write/MultiEdit is blocked immediately
    until proof exists -- unchanged original behavior.

    'stop': edits are allowed through immediately; proof is required before
    the turn can end (the proof-stop-gate.py Stop hook enforces it). This
    turns a burst of N new files in one batch into one consolidated
    rejection instead of N individual ones -- see workspace/
    llama-server-wifi-switch-2026-07-01/context.md for the measured burst-
    cost problem this fixes. Opt-in via the CLEAN_RAG_GATE_MODE env var so
    projects that don't set it keep today's behavior unchanged.

    Security-sensitive paths always use 'pretooluse' behavior regardless of
    this setting -- see _is_security_sensitive_path and the call site in
    main() that excludes them from deferral.
    """
    mode = os.environ.get("CLEAN_RAG_GATE_MODE", "pretooluse").strip().lower()
    return mode if mode in ("pretooluse", "stop") else "pretooluse"


_SESSION_ID_RE = re.compile(r"[^A-Za-z0-9_.-]")


def _safe_session_id(session_id: str) -> str:
    """Sanitize a session_id for safe use as a filename component."""
    return _SESSION_ID_RE.sub("_", session_id)[:128]


def stop_pending_path(state_dir: Path, session_id: str) -> Path:
    return state_dir / "stop-pending" / f"{_safe_session_id(session_id)}.json"


def load_stop_pending(state_dir: Path, session_id: str) -> dict:
    path = stop_pending_path(state_dir, session_id)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_stop_pending(state_dir: Path, session_id: str, data: dict) -> None:
    path = stop_pending_path(state_dir, session_id)
    if data:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    else:
        # Nothing left pending -- remove the file instead of writing "{}"
        try:
            path.unlink()
        except OSError:
            pass


def _record_stop_pending(
    state_dir: Path, session_id: str, canonical: str, file_path: str,
    needs_methodology: bool, suggested_methodology_topics: list,
    needs_best_practices: bool,
) -> None:
    data = load_stop_pending(state_dir, session_id)
    data[canonical] = {
        "file_path": file_path,
        "ts": _utc_now_iso(),
        "needs_methodology": needs_methodology,
        "suggested_methodology_topics": suggested_methodology_topics,
        "needs_best_practices": needs_best_practices,
    }
    save_stop_pending(state_dir, session_id, data)


def _clear_stop_pending(state_dir: Path, session_id: str, canonical: str) -> None:
    data = load_stop_pending(state_dir, session_id)
    if canonical in data:
        del data[canonical]
        save_stop_pending(state_dir, session_id, data)


def _try_consume_proof(state_dir: Path, canonical: str) -> dict | None:
    """Atomically consume and parse the keyed proof file for a path.

    Returns None if no proof file exists. Raises json.JSONDecodeError or
    OSError if a proof file existed but was corrupt -- callers should catch
    and treat that the same as "no proof", after logging the corruption.
    Shared by main()'s PreToolUse check and proof-stop-gate.py's Stop check
    so both use the exact same atomic TOCTOU-safe consumption.
    """
    proof_path = _proof_file_for(state_dir, canonical)
    consumed_path = proof_path.with_suffix(".consumed")
    try:
        os.replace(str(proof_path), str(consumed_path))
    except (OSError, FileNotFoundError):
        return None
    try:
        raw = consumed_path.read_text(encoding="utf-8")
        return json.loads(raw)
    finally:
        try:
            consumed_path.unlink()
        except OSError:
            pass


def _validate_proof(
    proof: dict, canonical: str,
    needs_methodology: bool, suggested_methodology_topics: list,
    needs_best_practices: bool, needs_security: bool,
) -> tuple[bool, list[str]]:
    """Run every mechanical proof check. Returns (valid, reasons).

    Pulled out of main() so proof-stop-gate.py can run the identical checks
    against proof files that show up after the edit already happened (stop
    gate mode), using needs_* flags captured at write time since the Stop
    hook has no tool_input to re-derive them from.
    """
    valid = True
    reasons: list[str] = []

    proof_canonical = _canonicalize(proof.get("file", ""))
    if proof_canonical != canonical:
        valid = False
        reasons.append(f"file mismatch: proof={proof_canonical}, edit={canonical}")

    if proof.get("verdict") != "VERIFIED":
        valid = False
        reasons.append(f"verdict={proof.get('verdict', 'missing')}")

    if not _is_fresh_strict(proof):
        valid = False
        reasons.append("timestamp expired or missing timezone")

    # Note: content_hash is informational only (tracked for audit trail).
    # We do NOT block on content_hash mismatch -- see clean-rag/CLAUDE.md.

    proof_score = proof.get("min_score", 0)
    if proof_score < MIN_PROOF_SCORE:
        valid = False
        reasons.append(f"min_score {proof_score} < {MIN_PROOF_SCORE}")

    angles = proof.get("research_angles", [])
    if len(angles) < MIN_RESEARCH_ANGLES:
        valid = False
        reasons.append(
            f"research_angles: {len(angles)} provided, need >= {MIN_RESEARCH_ANGLES}"
        )

    has_codebase = any(
        isinstance(a, dict) and a.get("angle") == "codebase" for a in angles
    )
    if not has_codebase:
        valid = False
        reasons.append(
            "research_angles: missing 'codebase' angle. "
            "You must search the surrounding codebase (callers, imports, "
            "dependents) before editing, not just the target file"
        )

    quality = proof.get("quality_aspects", [])
    if len(quality) < MIN_QUALITY_ASPECTS:
        valid = False
        reasons.append(
            f"quality_aspects: {len(quality)} provided, need >= {MIN_QUALITY_ASPECTS}. "
            "You must consider code quality from multiple angles before editing: "
            "architecture, patterns, maintainability, security, performance, testing"
        )

    if quality:
        has_macro = any(
            isinstance(q, dict) and q.get("aspect") in MACRO_QUALITY_ASPECTS
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

    if needs_methodology:
        has_methodology = any(
            isinstance(a, dict) and a.get("angle") == "methodology" for a in angles
        )
        if not has_methodology:
            valid = False
            reasons.append(
                "research_angles: missing 'methodology' angle. This file's structure "
                f"suggests {', '.join(suggested_methodology_topics)} -- search one of these "
                "topics and cite it as a methodology angle"
            )

    if needs_best_practices:
        has_best_practices = any(
            isinstance(a, dict) and a.get("angle") == "best_practices" for a in angles
        )
        if not has_best_practices and not _has_prior_art_justification(quality):
            valid = False
            reasons.append(
                "This looks like new functionality being built from scratch. Either cite "
                "a 'best_practices' research angle checking for an existing library/pattern "
                "first, or add a quality_aspects entry explicitly justifying why building "
                "custom is the right call here"
            )

    if needs_security:
        has_security = any(
            isinstance(a, dict) and a.get("angle") == "security" for a in angles
        )
        if not has_security:
            valid = False
            reasons.append(
                "research_angles: missing 'security' angle. This file's path matches a "
                "security-sensitive pattern (auth/session/token/password/crypto/secret/"
                "api-key) -- cite a search against the owasp topic (or equivalent) as a "
                "security angle before editing"
            )

    return valid, reasons


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

    # Atomic proof consumption + validation, shared with proof-stop-gate.py.
    proof = None
    try:
        proof = _try_consume_proof(state_dir, canonical)
    except (json.JSONDecodeError, OSError) as e:
        print(f"proof-gate: corrupt proof file: {e}", file=sys.stderr)
        _tel_block(file_path, f"corrupt_proof: {e}")

    if proof is not None:
        suggested_methodology = _suggest_methodology_topics(file_path, tool_input)
        needs_methodology = bool(
            set(suggested_methodology) - set(METHODOLOGY_TOPICS["baseline"])
        )
        needs_best_practices = _is_new_or_substantial_addition(file_path, tool_input)
        needs_security = _is_security_sensitive_path(file_path)

        valid, reasons = _validate_proof(
            proof, canonical,
            needs_methodology, suggested_methodology,
            needs_best_practices, needs_security,
        )

        if valid:
            _log_proof(state_dir, file_path, proof, edit_hash)
            _tel_pass(file_path, proof.get("topics_cited", []), proof.get("min_score", 0))
            if _gate_mode() == "stop":
                session_id = payload.get("session_id", "")
                if session_id:
                    _clear_stop_pending(state_dir, session_id, canonical)
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

    # 5. No valid proof yet. In 'stop' gate mode, defer to the Stop hook
    # instead of blocking this call immediately -- unless the file is
    # security-sensitive (those always fail closed at PreToolUse time, same
    # as the server-down path below) or we have no session_id to key the
    # pending list on (fail safe to normal blocking behavior).
    if (
        _gate_mode() == "stop"
        and payload.get("session_id", "")
        and not _is_security_sensitive_path(file_path)
    ):
        suggested_methodology = _suggest_methodology_topics(file_path, tool_input)
        needs_methodology = bool(
            set(suggested_methodology) - set(METHODOLOGY_TOPICS["baseline"])
        )
        needs_best_practices = _is_new_or_substantial_addition(file_path, tool_input)
        _record_stop_pending(
            state_dir, payload["session_id"], canonical, file_path,
            needs_methodology, suggested_methodology, needs_best_practices,
        )
        _tel_block(file_path, "deferred_to_stop_gate")
        return 0

    # No valid proof. Check server health and block with guidance.
    _tel_block(file_path, "no_valid_proof")
    _maybe_write_debug_fix(state_dir, file_path, "no_valid_proof")

    if not _server_reachable(port):
        # Server is down. Security-sensitive files fail closed (no offline
        # path, must wait for the server) -- everything else gets pointed
        # at verifier/offline_prove.py instead of just "start the server".
        if _is_security_sensitive_path(file_path):
            print(
                BLOCK_MESSAGE_SERVER_DOWN_SECURITY.format(file=file_path, port=port),
                file=sys.stderr,
            )
        else:
            print(
                BLOCK_MESSAGE_SERVER_DOWN.format(file=file_path, port=port),
                file=sys.stderr,
            )
        return 2

    # Server is up. Show full research instructions with expected proof path.
    index_guidance = _build_index_guidance(file_path, port)
    methodology_guidance = _build_methodology_guidance(file_path, tool_input, port)
    proof_path = _proof_file_for(state_dir, canonical)

    print(
        BLOCK_MESSAGE.format(
            file=file_path,
            port=port,
            state_dir=str(state_dir).replace("\\", "/"),
            min_score=MIN_PROOF_SCORE,
            window=PROOF_WINDOW_S,
            index_guidance=index_guidance,
            methodology_guidance=methodology_guidance,
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


def _build_methodology_guidance(file_path: str, tool_input: dict, port: str) -> str:
    """Build methodology topic suggestions for the block message.

    Analyzes the file path and edit content to suggest which code quality
    methodology topics are most relevant to search before making this edit.
    """
    topics = _suggest_methodology_topics(file_path, tool_input)
    if not topics:
        return ""

    sources = ", ".join(f'"topic:{t}"' for t in topics)
    return (
        f"METHODOLOGY TOPICS (search these for code quality guidance):\n"
        f'  POST http://127.0.0.1:{port}/search\n'
        f'  {{"query": "<your code quality question>", "sources": [{sources}]}}\n'
        f"  Suggested topics: {', '.join(topics)}\n"
        f'  Add a "methodology" angle to your proof for stronger quality grounding.'
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
