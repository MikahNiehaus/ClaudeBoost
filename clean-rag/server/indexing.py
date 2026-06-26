"""Indexing engine for clean-rag. Handles chunking, embedding, and storage.

Extracted from ClaudeBoost mcp-rag-server, simplified for topic + project indexing.
"""

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import (
    CHUNK_OVERLAP_TOKENS,
    DATABASES_DIR,
    DEGENERATE_CHUNK_MIN_TOKENS,
    KNOWLEDGE_DIR,
    MAX_CHUNK_TOKENS,
    MIN_CHUNK_TOKENS,
    STATE_DIR,
)
from .store import Chunk, ChromaStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

@dataclass
class RawChunk:
    """A chunk of text before embedding."""
    content: str
    section: str
    line_start: int
    line_end: int
    token_count_approx: int


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English."""
    return len(text) // 4


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
    # Preserve directory tree path for organized retrieval
    parts = source_file.replace("\\", "/").split("/")
    tree_path = "/".join(parts[:-1]) if len(parts) > 1 else ""

    return {
        "source_file": source_file,
        "scope": scope,
        "section": section,
        "tree_path": tree_path,
        "line_start": line_start,
        "line_end": line_end,
        "file_hash": content_hash,
        "indexed_at": datetime.now(timezone.utc).isoformat(),
        "chunk_index": chunk_index,
        "token_count": token_count,
    }


def chunk_markdown(
    text: str,
    source_file: str,
    max_tokens: int = 500,
    min_tokens: int = 50,
    chunk_overlap: int = 0,
) -> list[RawChunk]:
    """Split a markdown file into chunks based on heading boundaries."""
    lines = text.split("\n")
    sections = _split_into_sections(lines)

    chunks = []
    for section in sections:
        section_chunks = _process_section(section, max_tokens, min_tokens, chunk_overlap)
        chunks.extend(section_chunks)

    # Merge trailing small chunks into the previous one
    if len(chunks) > 1 and chunks[-1].token_count_approx < min_tokens:
        last = chunks.pop()
        chunks[-1] = RawChunk(
            content=chunks[-1].content + "\n\n" + last.content,
            section=chunks[-1].section,
            line_start=chunks[-1].line_start,
            line_end=last.line_end,
            token_count_approx=chunks[-1].token_count_approx + last.token_count_approx,
        )

    return chunks


def chunk_code(
    content: str,
    source_file: str,
    max_tokens: int = 500,
    min_tokens: int = 50,
    chunk_overlap: int = 0,
) -> list[RawChunk]:
    """Split source code into chunks. Uses blank-line boundaries for splitting."""
    lines = content.split("\n")
    total_tokens = estimate_tokens(content)

    if total_tokens <= max_tokens:
        if total_tokens < min_tokens:
            return []
        return [RawChunk(
            content=content,
            section=Path(source_file).stem,
            line_start=1,
            line_end=len(lines),
            token_count_approx=total_tokens,
        )]

    # Split on double-newline boundaries (function/class gaps)
    chunks = []
    current_lines: list[str] = []
    current_start = 1
    overlap_lines: list[str] = []

    for i, line in enumerate(lines, 1):
        current_lines.append(line)
        current_text = "\n".join(current_lines)
        current_tokens = estimate_tokens(current_text)

        is_boundary = (line.strip() == "" and i < len(lines))
        is_last = (i == len(lines))

        if (current_tokens >= max_tokens and is_boundary) or is_last:
            text = current_text.strip()
            if text and estimate_tokens(text) >= min_tokens:
                chunks.append(RawChunk(
                    content=text,
                    section=Path(source_file).stem,
                    line_start=current_start,
                    line_end=i,
                    token_count_approx=estimate_tokens(text),
                ))
            if chunk_overlap > 0 and current_lines:
                # Carry last few lines as overlap
                overlap_count = max(1, chunk_overlap // 10)
                overlap_lines = current_lines[-overlap_count:]
            current_lines = list(overlap_lines)
            overlap_lines = []
            current_start = i + 1

    return chunks


@dataclass
class _Section:
    heading: str
    content: str
    line_start: int
    line_end: int


def _split_into_sections(lines: list[str]) -> list[_Section]:
    """Split lines into sections based on H1/H2/H3 headers."""
    sections = []
    current_heading = "Introduction"
    current_lines: list[str] = []
    current_start = 1

    for i, line in enumerate(lines):
        if re.match(r"^#{1,3}\s+", line):
            if current_lines or sections == []:
                content = "\n".join(current_lines).strip()
                if content:
                    sections.append(_Section(
                        heading=current_heading,
                        content=content,
                        line_start=current_start,
                        line_end=i,
                    ))
            current_heading = re.sub(r"^#{1,3}\s+", "", line).strip()
            current_lines = []
            current_start = i + 1
        else:
            current_lines.append(line)

    if current_lines:
        content = "\n".join(current_lines).strip()
        if content:
            sections.append(_Section(
                heading=current_heading,
                content=content,
                line_start=current_start,
                line_end=len(lines),
            ))

    return sections


def _process_section(
    section: _Section, max_tokens: int, min_tokens: int, chunk_overlap: int = 0,
) -> list[RawChunk]:
    """Process a single section, splitting at paragraph boundaries if too large."""
    tokens = estimate_tokens(section.content)

    if tokens <= max_tokens:
        return [RawChunk(
            content=section.content,
            section=section.heading,
            line_start=section.line_start,
            line_end=section.line_end,
            token_count_approx=tokens,
        )]

    paragraphs = re.split(r"\n\n+", section.content)
    chunks = []
    current_text = ""
    current_start = section.line_start
    _overlap_text = ""

    for para in paragraphs:
        para_tokens = estimate_tokens(para)
        current_tokens = estimate_tokens(current_text)

        if current_text and (current_tokens + para_tokens) > max_tokens:
            line_count = current_text.count("\n") + 1
            chunks.append(RawChunk(
                content=current_text.strip(),
                section=section.heading,
                line_start=current_start,
                line_end=current_start + line_count - 1,
                token_count_approx=current_tokens,
            ))
            if chunk_overlap > 0:
                tail = current_text.rsplit("\n\n", 1)[-1].strip()
                _overlap_text = tail if tail and estimate_tokens(tail) <= chunk_overlap else ""
            else:
                _overlap_text = ""
            current_start = current_start + line_count
            current_text = (_overlap_text + "\n\n" + para).strip() if _overlap_text else para
        else:
            current_text = (current_text + "\n\n" + para).strip() if current_text else para

    if current_text.strip():
        chunks.append(RawChunk(
            content=current_text.strip(),
            section=section.heading,
            line_start=current_start,
            line_end=section.line_end,
            token_count_approx=estimate_tokens(current_text),
        ))

    return chunks


# ---------------------------------------------------------------------------
# Code file scanning (for project indexing)
# ---------------------------------------------------------------------------

# Extensions considered indexable source code
CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs",
    ".go", ".rs", ".java", ".kt", ".scala",
    ".cs", ".fs", ".vb",
    ".c", ".cpp", ".cc", ".h", ".hpp",
    ".rb", ".php", ".swift", ".m",
    ".lua", ".r", ".jl", ".dart", ".zig",
    ".sh", ".bash", ".zsh", ".ps1",
    ".sql", ".graphql", ".proto",
    ".html", ".css", ".scss", ".less", ".vue", ".svelte",
    ".yaml", ".yml", ".toml", ".json", ".xml",
    ".md", ".mdx", ".rst", ".txt",
}

# Directories to skip during project scanning
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", ".nuxt", "target",
    "vendor", ".tox", ".mypy_cache", ".pytest_cache",
    "coverage", ".coverage", "bin", "obj",
    "workspace",  # ClaudeBoost workspace dirs
}

MAX_FILE_SIZE = 500_000  # 500KB


def scan_project(project_path: str) -> list[str]:
    """Scan a project directory for indexable source files.

    Returns a list of absolute file paths.
    """
    root = Path(project_path).resolve()
    files = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        # Skip directories in SKIP_DIRS
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.suffix.lower() not in CODE_EXTENSIONS:
            continue
        try:
            if path.stat().st_size > MAX_FILE_SIZE:
                continue
        except OSError:
            continue
        files.append(str(path))

    return sorted(files)


# ---------------------------------------------------------------------------
# Topic indexing
# ---------------------------------------------------------------------------

def _resolve_topic_paths(
    topic: str, category: str | None = None,
) -> tuple[Path, Path, Path]:
    """Resolve knowledge dir, chroma dir, and manifest path for a topic.

    If category is provided, uses category tree: knowledge/<cat>/<topic>/.
    Otherwise looks up from topics.json registry, then falls back to flat.
    """
    if category is None:
        # Try registry lookup
        reg = _read_topic_registry()
        category = reg.get(topic, {}).get("category")

    if category is None:
        # Try source map
        try:
            from research.source_map import get_category
            cat = get_category(topic)
            if cat != "uncategorized":
                category = cat
        except (ImportError, Exception):
            pass

    if category is None:
        # Scan knowledge dir for category/<topic>/ as final fallback
        if KNOWLEDGE_DIR.exists():
            for subdir in KNOWLEDGE_DIR.iterdir():
                if subdir.is_dir() and (subdir / topic).is_dir():
                    category = subdir.name
                    break

    if category:
        topic_dir = KNOWLEDGE_DIR / category / topic
        chroma_dir = DATABASES_DIR / category / topic / "chroma"
        manifest_path = DATABASES_DIR / category / topic / "manifest.json"
    else:
        # Flat fallback for topics not in any category
        topic_dir = KNOWLEDGE_DIR / topic
        chroma_dir = DATABASES_DIR / topic / "chroma"
        manifest_path = DATABASES_DIR / topic / "manifest.json"

    return topic_dir, chroma_dir, manifest_path


def _read_topic_registry() -> dict:
    """Read topics.json registry."""
    registry_path = STATE_DIR / "topics.json"
    if registry_path.exists():
        try:
            return json.loads(registry_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def index_topic(
    topic: str,
    embedder,
    force: bool = False,
    category: str | None = None,
) -> dict:
    """Index all files in knowledge/[category/]<topic>/ into databases/[category/]<topic>/chroma/.

    If category is provided, uses the tree structure. Otherwise looks up
    the category from the topics.json registry or source_map.

    Returns stats dict with files_indexed, chunks_created, etc.
    """
    topic_dir, chroma_dir, manifest_path = _resolve_topic_paths(topic, category)

    if not topic_dir.exists():
        logger.error("Topic directory not found: %s", topic_dir)
        return {"error": f"Topic directory not found: {topic_dir}"}

    # Load existing manifest for incremental indexing
    manifest: dict = {}
    if not force and manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}

    store = ChromaStore(persist_dir=str(chroma_dir))

    if force and store.collection_exists("docs"):
        store.delete_collection("docs")

    store.create_collection("docs")

    # Find all doc files in the topic directory
    doc_extensions = {".md", ".mdx", ".rst", ".txt", ".html"}
    files = []
    for ext in doc_extensions:
        files.extend(str(p) for p in topic_dir.rglob(f"*{ext}"))
    files.sort()

    files_indexed = 0
    chunks_created = 0
    files_unchanged = 0
    files_failed = 0
    start_time = time.time()

    for file_path in files:
        rel_path = str(Path(file_path).relative_to(topic_dir)).replace("\\", "/")

        try:
            content = Path(file_path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            logger.warning("Failed to read %s: %s", rel_path, e)
            files_failed += 1
            continue

        current_hash = file_hash(content)
        if not force and manifest.get(rel_path) == current_hash:
            files_unchanged += 1
            continue

        store.delete_by_source("docs", rel_path)

        raw_chunks = chunk_markdown(
            content, rel_path,
            max_tokens=MAX_CHUNK_TOKENS,
            min_tokens=MIN_CHUNK_TOKENS,
            chunk_overlap=CHUNK_OVERLAP_TOKENS,
        )

        if not raw_chunks:
            files_unchanged += 1
            continue

        try:
            texts = [f"[{topic}/{rel_path}] [{c.section}]\n{c.content}" for c in raw_chunks]
            embeddings = embedder.embed(texts)

            store_chunks = []
            for i, (raw, embedding) in enumerate(zip(raw_chunks, embeddings)):
                cid = chunk_id(f"{topic}/{rel_path}", i)
                metadata = build_metadata(
                    source_file=rel_path,
                    scope=f"topic:{topic}",
                    section=raw.section,
                    line_start=raw.line_start,
                    line_end=raw.line_end,
                    content_hash=current_hash,
                    chunk_index=i,
                    token_count=raw.token_count_approx,
                )
                metadata["topic"] = topic
                store_chunks.append(Chunk(
                    id=cid,
                    content=raw.content,
                    embedding=embedding,
                    metadata=metadata,
                ))

            added = store.add_chunks("docs", store_chunks)
            chunks_created += added
            files_indexed += 1
            manifest[rel_path] = current_hash
        except Exception as e:
            logger.error("Failed to embed/store %s/%s: %s", topic, rel_path, e)
            files_failed += 1

    # Save manifest
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # Update topic registry (include category for tree lookup)
    resolved_cat = category
    if resolved_cat is None:
        try:
            from research.source_map import get_category
            cat = get_category(topic)
            if cat != "uncategorized":
                resolved_cat = cat
        except ImportError:
            pass
    _update_topic_registry(topic, store.count("docs"), store.count_sources("docs"), resolved_cat)

    elapsed = round(time.time() - start_time, 1)
    return {
        "topic": topic,
        "files_indexed": files_indexed,
        "chunks_created": chunks_created,
        "files_unchanged": files_unchanged,
        "files_failed": files_failed,
        "elapsed_s": elapsed,
    }


def _update_topic_registry(
    topic: str, chunk_count: int, file_count: int, category: str | None = None,
) -> None:
    """Update state/topics.json with current topic stats and category."""
    registry_path = STATE_DIR / "topics.json"
    registry: dict = {}
    if registry_path.exists():
        try:
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
        except Exception:
            registry = {}

    entry = {
        "chunks": chunk_count,
        "files": file_count,
        "indexed_at": datetime.now(timezone.utc).isoformat(),
    }
    if category:
        entry["category"] = category

    registry[topic] = entry

    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    logger.info("Registry updated: %s (category=%s, chunks=%d, files=%d)",
                topic, category or "flat", chunk_count, file_count)


# ---------------------------------------------------------------------------
# Project indexing
# ---------------------------------------------------------------------------

def index_project(
    project_path: str,
    code_embedder,
    force: bool = False,
) -> dict:
    """Index a project's source code into databases/_projects/<hash>/chroma/.

    Returns stats dict.
    """
    # Embedder loads lazily on first embed() call. If called via HTTP, app.py
    # warms it up beforehand. If called directly, the first embed() triggers
    # the model download automatically.

    project_root = Path(project_path).resolve()
    pid = hashlib.sha256(str(project_root).encode("utf-8")).hexdigest()[:12]

    index_dir = DATABASES_DIR / "_projects" / pid
    chroma_dir = index_dir / "chroma"
    manifest_path = index_dir / "manifest.json"

    # Load manifest
    manifest: dict = {}
    if not force and manifest_path.exists():
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = {k: v for k, v in raw.items() if not k.startswith("__")}
        except Exception:
            manifest = {}

    store = ChromaStore(persist_dir=str(chroma_dir))
    collection = "codebase"

    if force and store.collection_exists(collection):
        store.delete_collection(collection)

    store.create_collection(collection)

    file_paths = scan_project(project_path)

    files_indexed = 0
    chunks_created = 0
    files_unchanged = 0
    files_failed = 0
    start_time = time.time()

    for file_path in file_paths:
        try:
            rel_path = str(Path(file_path).relative_to(project_root)).replace("\\", "/")
        except ValueError:
            rel_path = file_path.replace("\\", "/")

        suffix = Path(rel_path).suffix.lower()
        is_doc = suffix in {".md", ".mdx", ".rst", ".txt"}

        try:
            content = Path(file_path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            logger.warning("Failed to read %s: %s", rel_path, e)
            files_failed += 1
            continue

        current_hash = file_hash(content)
        if not force and manifest.get(rel_path) == current_hash:
            files_unchanged += 1
            continue

        store.delete_by_source(collection, rel_path)

        # Route to the right chunker
        if is_doc:
            raw_chunks = chunk_markdown(
                content, rel_path,
                max_tokens=MAX_CHUNK_TOKENS,
                min_tokens=MIN_CHUNK_TOKENS,
                chunk_overlap=CHUNK_OVERLAP_TOKENS,
            )
        else:
            raw_chunks = chunk_code(
                content, rel_path,
                max_tokens=MAX_CHUNK_TOKENS,
                min_tokens=MIN_CHUNK_TOKENS,
                chunk_overlap=CHUNK_OVERLAP_TOKENS,
            )

        if not raw_chunks:
            files_unchanged += 1
            continue

        try:
            texts = [c.content for c in raw_chunks]
            embeddings = code_embedder.embed(texts)

            store_chunks = []
            for i, (raw, embedding) in enumerate(zip(raw_chunks, embeddings)):
                if raw.token_count_approx < DEGENERATE_CHUNK_MIN_TOKENS:
                    continue
                cid = chunk_id(rel_path, i)
                metadata = build_metadata(
                    source_file=rel_path,
                    scope="project",
                    section=raw.section,
                    line_start=raw.line_start,
                    line_end=raw.line_end,
                    content_hash=current_hash,
                    chunk_index=i,
                    token_count=raw.token_count_approx,
                )
                store_chunks.append(Chunk(
                    id=cid,
                    content=raw.content,
                    embedding=embedding,
                    metadata=metadata,
                ))

            added = store.add_chunks(collection, store_chunks)
            chunks_created += added
            files_indexed += 1
            manifest[rel_path] = current_hash
        except Exception as e:
            logger.error("Failed to embed/store %s: %s", rel_path, e)
            files_failed += 1

    # Save manifest
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    save_data = {"__project_path__": str(project_root)}
    save_data.update(manifest)
    manifest_path.write_text(json.dumps(save_data, indent=2), encoding="utf-8")

    # Update project registry
    _update_project_registry(pid, str(project_root), files_indexed, chunks_created)

    elapsed = round(time.time() - start_time, 1)
    return {
        "project_id": pid,
        "project_path": str(project_root),
        "files_indexed": files_indexed,
        "chunks_created": chunks_created,
        "files_unchanged": files_unchanged,
        "files_failed": files_failed,
        "elapsed_s": elapsed,
    }


def _update_project_registry(
    pid: str, project_path: str, files_indexed: int, chunks_created: int,
) -> None:
    """Update state/projects.json with current project stats."""
    registry_path = STATE_DIR / "projects.json"
    registry: dict = {}
    if registry_path.exists():
        try:
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
        except Exception:
            registry = {}

    registry[pid] = {
        "project_path": project_path,
        "files_indexed": files_indexed,
        "chunks_created": chunks_created,
        "indexed_at": datetime.now(timezone.utc).isoformat(),
    }

    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
