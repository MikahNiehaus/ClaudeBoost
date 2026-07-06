"""Proof logging utilities for clean-rag."""

import hashlib
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def _canonicalize(file_path: str) -> str:
    """Resolve and normalize a file path for safe comparison."""
    try:
        resolved = Path(file_path).resolve()
    except (OSError, ValueError):
        resolved = Path(file_path)
    return resolved.as_posix().lower()


def _proof_file_for(state_dir: Path, canonical_path: str) -> Path:
    """Return the keyed proof file path for a given canonical file path.

    Each file being edited gets its own proof file so concurrent edits
    to different files don't overwrite each other.
    """
    path_hash = hashlib.sha256(canonical_path.encode("utf-8")).hexdigest()[:16]
    return state_dir / f"pending-proof-{path_hash}.json"


def write_pending_proof(
    state_dir: str | Path,
    file_path: str,
    verdict: str,
    verifier_response: str,
    rag_results_count: int = 0,
    topics_cited: list[str] | None = None,
    project_cited: bool = False,
    content_hash: str = "",
    min_score: float = 0.0,
    research_angles: list[dict] | None = None,
    quality_aspects: list[dict] | None = None,
) -> Path:
    """Write a keyed proof file for the proof gate to read.

    Uses atomic write (tempfile + os.replace) so the proof gate never
    reads a partially written file. The file is keyed by a hash of the
    canonical file path, allowing concurrent proofs for different files.

    Returns the path to the written file.
    """
    state = Path(state_dir)
    state.mkdir(parents=True, exist_ok=True)

    # Normalize the file path before storing so the gate can match it
    canonical = _canonicalize(file_path)
    proof_path = _proof_file_for(state, canonical)

    proof = {
        "file": file_path,
        "file_canonical": canonical,
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "verdict": verdict,
        "verifier_response": verifier_response,
        "rag_results_count": rag_results_count,
        "topics_cited": topics_cited or [],
        "project_cited": project_cited,
        "content_hash": content_hash,
        "min_score": min_score,
        "research_angles": research_angles or [],
        "quality_aspects": quality_aspects or [],
    }

    fd, tmp_path = tempfile.mkstemp(dir=str(state), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(proof, f, indent=2)
        os.replace(tmp_path, str(proof_path))
    except Exception:
        logger.error("Failed to write pending proof for %s", file_path)
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return proof_path


def read_proof_log(state_dir: str | Path, limit: int = 50) -> list[dict]:
    """Read the most recent entries from proof-log.jsonl.

    Returns entries newest-first, up to `limit`.
    """
    log_path = Path(state_dir) / "proof-log.jsonl"
    if not log_path.exists():
        return []

    entries = []
    try:
        for line in log_path.read_text(encoding="utf-8").strip().split("\n"):
            if line.strip():
                entries.append(json.loads(line))
    except Exception as e:
        logger.warning("Failed to read proof log: %s", e)
        return []

    return list(reversed(entries[-limit:]))
