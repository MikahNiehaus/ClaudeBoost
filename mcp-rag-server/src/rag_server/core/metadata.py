"""Metadata extraction and tagging for chunks."""

import hashlib
from datetime import datetime, timezone


def file_hash(content: str) -> str:
    """SHA-256 hash prefix for change detection."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def chunk_id(source_file: str, chunk_index: int) -> str:
    """Generate a deterministic chunk ID."""
    raw = f"{source_file}::{chunk_index}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_metadata(
    source_file: str,
    scope: str,
    section: str,
    line_start: int,
    line_end: int,
    content_hash: str,
    chunk_index: int,
    token_count: int,
) -> dict:
    """Build the metadata dict for a chunk."""
    return {
        "source_file": source_file,
        "scope": scope,
        "section": section,
        "line_start": line_start,
        "line_end": line_end,
        "file_hash": content_hash,
        "indexed_at": datetime.now(timezone.utc).isoformat(),
        "chunk_index": chunk_index,
        "token_count": token_count,
    }
