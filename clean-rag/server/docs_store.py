"""Persistent, topic scoped storage and ingestion for the docs RAG feature.

Mirrors databases/_projects/<hash>/ for project code: databases/_docs/<topic>/
holds one Chroma collection plus a manifest, keyed by topic name instead of a
path hash, since a topic is a human chosen label, not a filesystem path.

Unlike research_rag's workspace scoped index (ephemeral, torn down per task),
this is meant to persist and be searched across sessions indefinitely, so
there is no force wipe teardown path here: re ingesting a source updates only
that source's chunks, keyed by content hash in the manifest, the same
incremental philosophy server/indexing.py already uses for project code.
"""

import hashlib
import json
import logging
import re
import time
import uuid
from pathlib import Path

from .config import DATABASES_DIR, DEFAULT_MIN_SCORE, DEFAULT_SEARCH_LIMIT
from .docs_chunker import chunk_by_heading
from .docs_citation import extract_citation, extract_related_citations
from .store import Chunk, ChromaStore

logger = logging.getLogger(__name__)

_TOPIC_SLUG_RE = re.compile(r"[^a-z0-9_-]+")


def topic_slug(topic: str) -> str:
    """Normalize a topic name into a safe directory/collection name."""
    slug = _TOPIC_SLUG_RE.sub("-", topic.strip().lower()).strip("-")
    if not slug:
        raise ValueError(f"topic name has no usable characters: {topic!r}")
    return slug


def _topic_dir(topic: str) -> Path:
    return DATABASES_DIR / "_docs" / topic_slug(topic)


def _manifest_path(topic: str) -> Path:
    return _topic_dir(topic) / "manifest.json"


def _load_manifest(topic: str) -> dict:
    path = _manifest_path(topic)
    if not path.exists():
        return {"topic": topic, "sources": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("manifest for topic %r unreadable, starting fresh", topic)
        return {"topic": topic, "sources": {}}


def _save_manifest(topic: str, manifest: dict) -> None:
    path = _manifest_path(topic)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def ingest_source(
    topic: str,
    source_id: str,
    text: str,
    heading_pattern: str,
    citation_prefix: str,
    source_url: str,
    jurisdiction: str,
    doc_embedder,
    force: bool = False,
) -> dict:
    """Chunk, citation tag, embed, and store one source's text under a topic.

    Skips re embedding when the source's content hash is unchanged since the
    last ingest, unless force is set. Returns stats: chunks_created,
    chunks_skipped_unchanged, chunks_dropped_no_citation.
    """
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()

    manifest = _load_manifest(topic)
    prior = manifest["sources"].get(source_id)
    if prior and prior.get("content_hash") == content_hash and not force:
        return {"source_id": source_id, "chunks_created": 0, "skipped_unchanged": True}

    chroma_dir = _topic_dir(topic) / "chroma"
    store = ChromaStore(persist_dir=str(chroma_dir))
    store.create_collection("docs")

    if prior:
        # Re ingesting a changed source: drop its old chunks first so a
        # shrunk or renumbered source doesn't leave stale citations behind.
        store.delete_by_source("docs", source_id)

    # Measure chunk size with the embedder's real subword tokenizer and cap it
    # at the model's real max sequence length, so no chunk silently overflows
    # and gets truncated at embed time (the 4-chars-per-token estimate
    # under-counts dense legal text).
    raw_chunks = chunk_by_heading(
        text,
        heading_pattern=heading_pattern,
        max_tokens=doc_embedder.max_tokens,
        token_counter=doc_embedder.count_tokens,
    )

    dropped_no_citation = 0
    docs_chunks: list[Chunk] = []
    embed_texts: list[str] = []
    metas: list[dict] = []
    for c in raw_chunks:
        citation = extract_citation(c.heading, citation_prefix)
        if not citation.strip():
            dropped_no_citation += 1
            continue
        embed_texts.append(c.content)
        # Chroma metadata values must be flat scalars, not lists, so related
        # citations (additive enrichment, see docs_citation's module
        # docstring for why they're never the primary citation) are joined
        # into one string rather than stored as a list.
        related = extract_related_citations(c.content)
        metas.append({
            "source_file": source_id,
            "topic": topic,
            "jurisdiction": jurisdiction,
            "citation": citation,
            "related_citations": "; ".join(related),
            "heading": c.heading,
            "source_url": source_url,
            "line_start": c.line_start,
            "line_end": c.line_end,
            "retrieved_at": manifest["sources"].get(source_id, {}).get(
                "first_retrieved_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            ),
        })

    if embed_texts:
        # embed_texts, metas, and embeddings are all built in the same
        # kept-chunk order (a dropped no-citation chunk skips all three
        # together), so they stay positionally aligned. Zipping against the
        # unfiltered raw_chunks instead would pair every chunk after the first
        # drop with the wrong content and silently truncate the tail.
        embeddings = doc_embedder.embed(embed_texts)
        for meta, embedding, content in zip(metas, embeddings, embed_texts):
            docs_chunks.append(Chunk(
                id=uuid.uuid4().hex,
                content=content,
                embedding=embedding,
                metadata=meta,
            ))
        store.add_chunks("docs", docs_chunks)

    manifest["sources"][source_id] = {
        "content_hash": content_hash,
        "chunks_created": len(docs_chunks),
        "last_ingested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "first_retrieved_at": manifest["sources"].get(source_id, {}).get(
            "first_retrieved_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        ),
        "source_url": source_url,
        "citation_prefix": citation_prefix,
    }
    _save_manifest(topic, manifest)

    return {
        "source_id": source_id,
        "chunks_created": len(docs_chunks),
        "chunks_dropped_no_citation": dropped_no_citation,
        "skipped_unchanged": False,
    }


def topic_status(topic: str) -> dict:
    """Report what's been ingested for a topic, for a /docs-status check."""
    manifest = _load_manifest(topic)
    chroma_dir = _topic_dir(topic) / "chroma"
    total_chunks = 0
    if chroma_dir.exists():
        store = ChromaStore(persist_dir=str(chroma_dir))
        if store.collection_exists("docs"):
            total_chunks = store.count("docs")
    return {
        "topic": topic,
        "sources": manifest.get("sources", {}),
        "total_chunks": total_chunks,
    }


def search_topic(query: str, topic: str, doc_embedder, limit: int = DEFAULT_SEARCH_LIMIT,
                  min_score: float = DEFAULT_MIN_SCORE) -> list[dict]:
    """Vector search over one topic's persistent docs collection."""
    chroma_dir = _topic_dir(topic) / "chroma"
    if not chroma_dir.exists():
        logger.warning("Docs topic not found: %s", topic)
        return []

    store = ChromaStore(persist_dir=str(chroma_dir))
    if not store.collection_exists("docs"):
        return []

    query_embedding = doc_embedder.embed_query(query)
    results = store.search("docs", query_embedding, limit=limit, min_score=min_score)

    return [
        {
            "content": r.content,
            "score": r.score,
            "source_type": "docs",
            "topic": r.metadata.get("topic", topic),
            "jurisdiction": r.metadata.get("jurisdiction", ""),
            "citation": r.metadata.get("citation", ""),
            "related_citations": r.metadata.get("related_citations", ""),
            "heading": r.metadata.get("heading", ""),
            "source_url": r.metadata.get("source_url", ""),
            "retrieved_at": r.metadata.get("retrieved_at", ""),
        }
        for r in results
    ]
