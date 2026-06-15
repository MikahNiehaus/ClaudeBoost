# Discovery Log

Audit trail of /research-project runs. NOT indexed — for human reference only.

---

## 2026-06-14 — chromadb (>=1.5.9)
- Role: vector store (Database/ORM)
- Angles run: official docs, security, performance, migration, integration, pitfalls
- Sources found: 8 (Tier A: 6, Tier B: 2)
- Retried angles: none
- No source found for: none
- KB file updated: stack.md, gotchas.md
- Critical finding: CVE-2026-45829 unpatched RCE — verify bind address in mcp-rag-server/

## 2026-06-14 — sentence-transformers (>=3.0)
- Role: embedding models (ML framework)
- Angles run: official docs, security, performance, migration, integration, pitfalls
- Sources found: 7 (Tier A: 4, Tier B: 3)
- Retried angles: none
- No source found for: none
- KB file updated: stack.md, gotchas.md
- Critical finding: BGE requires normalize_embeddings=True; 512-token silent truncation

## 2026-06-14 — starlette (>=0.37) + uvicorn[standard] (>=0.29)
- Role: HTTP server framework (Framework)
- Angles run: official docs, security, performance, migration, integration patterns, pitfalls
- Sources found: 8 (Tier A: 4, Tier B: 4)
- Retried angles: none
- No source found for: none
- KB file updated: stack.md
- Critical finding: 1.0rc1 removes on_startup/on_shutdown — check mcp-rag-server/ before upgrading

## 2026-06-14 — networkx (>=3.0)
- Role: dependency graph (utility)
- Angles run: official docs, performance, pitfalls
- Sources found: 3 (Tier A: 1, Tier B: 2)
- Retried angles: none
- No source found for: security (not applicable — no known CVEs, local data only), migration, integration
- KB file updated: stack.md
- Critical finding: not thread-safe — protect with write lock in RAG server

## 2026-06-14 — httpx (>=0.27) + beautifulsoup4 (>=4.12) + pymupdf (>=1.24)
- Role: web fetching/parsing stack (utility)
- Angles run: official docs, security, performance, pitfalls
- Sources found: 5 (Tier A: 3, Tier B: 2)
- Retried angles: none
- No source found for: migration (stable APIs, no major breaking changes in scope), integration (internal use only)
- KB file updated: stack.md
- Critical finding: PyMuPDF is AGPL v3 — needs commercial licence for hosted SaaS

## 2026-06-14 — tree-sitter (>=0.23)
- Role: AST code parsing (utility)
- Angles run: official docs, security, performance, migration, integration, pitfalls
- Sources found: 6 (Tier A: 2, Tier B: 4)
- Retried angles: none
- No source found for: none
- KB file updated: stack.md
- Critical finding: 0.25 moves Query.captures() to QueryCursor — check RAG server pin version

## 2026-06-14 — watchdog (>=4.0)
- Role: file system monitoring (utility)
- Angles run: official docs, security, performance, migration, integration, pitfalls
- Sources found: 5 (Tier A: 3, Tier B: 2)
- Retried angles: none
- No source found for: none
- KB file updated: stack.md
- Critical finding: always stop()+join() in finally block; v4.0 FileSystemEvent is now a dataclass (repr changed)

## 2026-06-14 — pathspec (>=0.12)
- Role: gitignore path filtering (utility)
- Angles run: official docs, security, performance, migration, pitfalls, integration
- Sources found: 4 (Tier A: 3, Tier B: 1)
- Retried angles: none
- No source found for: none
- KB file updated: stack.md
- Critical finding: normalize to forward slashes before match_file() on Windows; use GitIgnoreSpec not PathSpec for edge cases

## 2026-06-14 — lxml (>=5.0)
- Role: XML/HTML parsing (utility)
- Angles run: official docs, security, performance, migration, integration, pitfalls
- Sources found: 6 (Tier A: 4, Tier B: 2)
- Retried angles: none
- No source found for: none
- KB file updated: stack.md
- Critical finding: lxml 5.0 BREAKING — resolve_entities now 'internal' by default (was True); upgrade to 5.4.0+ for libxml2 2.13.8

## 2026-06-14 — html2text (>=2024.2)
- Role: HTML to Markdown conversion (utility)
- Angles run: official docs, security, performance, pitfalls, integration
- Sources found: 3 (Tier A: 2, Tier B: 1)
- Retried angles: none
- No source found for: migration (stable API, no breaking changes)
- KB file updated: stack.md
- Critical finding: body_width=78 default hard-wraps text and ruins RAG quality — always set body_width=0

## 2026-06-14 — graspologic (>=3.0)
- Role: graph statistics and spectral embedding (optional [graph])
- Angles run: official docs, performance, integration, pitfalls
- Sources found: 3 (Tier A: 2, Tier B: 1)
- Retried angles: security (no CVEs found — local compute only), migration (stable API in 3.x)
- No source found for: security, migration
- KB file updated: stack.md
- Critical finding: graph edges must have numeric weights; NetworkX DiGraph pipeline API accepts graphs directly

## 2026-06-14 — ollama (>=0.3)
- Role: local LLM embedding provider (optional [ollama])
- Angles run: official docs, security, performance, migration, integration, pitfalls
- Sources found: 5 (Tier A: 2, Tier B: 3)
- Retried angles: none
- No source found for: none
- KB file updated: stack.md
- Critical finding: nomic-embed-text silently truncates at 2048 tokens; dimension mismatch with chromadb collections if model is swapped
