# Project Research Brief

Last updated: 2026-06-14
Project: C:/Users/grayw/OneDrive/prj/ClaudeBoost

## Technologies Researched

| Technology | Version | Role | Sources | Confidence |
|------------|---------|------|---------|------------|
| chromadb | >=1.5.9 | Vector store | 8 (Tier A: 6, B: 2) | High |
| sentence-transformers | >=3.0 | Embedding models | 7 (Tier A: 4, B: 3) | High |
| starlette + uvicorn | >=0.37 / >=0.29 | HTTP server | 8 (Tier A: 4, B: 4) | High |
| networkx | >=3.0 | Dependency graph | 3 (Tier A: 1, B: 2) | Medium |
| httpx + bs4 + pymupdf | >=0.27/4.12/1.24 | Web fetching stack | 5 (Tier A: 3, B: 2) | High |
| tree-sitter | >=0.23 | AST code parsing | 6 (Tier A: 2, B: 4) | High |

## Coverage by Technology

### chromadb
| Angle | Sources | Key Takeaway |
|-------|---------|--------------|
| Official docs | 2 | get_or_create_collection silently ignores metadata updates in 1.x; list_collections() returns Collection objects |
| Security | 2 | CVE-2026-45829 unpatched RCE — must bind to 127.0.0.1 only; built-in auth removed in v1.0 |
| Performance | 1 | HNSW params locked at collection creation; set hnsw:space=cosine explicitly; batch 50-250 |
| Migration | 1 | Migrations irreversible; 0.x→1.x requires JSON export/import; back up .rag-index before any upgrade |
| Integration | 2 | Never pass embedding_function when storing pre-computed vectors; normalize_embeddings=True required for cosine |
| Pitfalls | 2 | Dimensionality locked after first insert; memory not freed after delete_collection without restart |

### sentence-transformers
| Angle | Sources | Key Takeaway |
|-------|---------|--------------|
| Official docs | 1 | encode(inputs=) in v5.4+; normalize_embeddings=False default; 512-token hard truncation for BGE |
| Security | 2 | Pin model revision= to prevent Hub supply-chain substitution; prefer safetensors over pytorch_model.bin |
| Performance | 1 | ONNX-O4 gives 3x CPU speedup; sort inputs by length before batching; Flash Attention 2 for variable-length |
| Migration | 1 | v5.4 renames sentences= to inputs=; encode_query()/encode_document() for asymmetric BGE retrieval |
| Integration | 1 | Distance metric must match training: cosine for BGE, normalized dot-product for code-search distilroberta |
| Pitfalls | 2 | Thread-unsafe with shared instances; known early-inference memory leak — pre-warm with dummy batch |

### starlette + uvicorn
| Angle | Sources | Key Takeaway |
|-------|---------|--------------|
| Official docs | 2 | Route('/path', handler, methods=["POST"]) — no decorators; always specify methods= explicitly |
| Security | 2 | No CSRF needed for REST API; validate JSON bodies manually; never allow_origins=["*"] |
| Performance | 2 | uvicorn[standard] activates uvloop + httptools; all handlers must be async def; never block event loop |
| Migration | 1 | 1.0rc1 removes on_startup/on_shutdown and @app.route() — migration target is lifespan context manager |
| Integration | 2 | Plain uvicorn.run() fine for localhost; Gunicorn only if multi-worker or crash recovery needed |
| Pitfalls | 2 | BaseHTTPMiddleware body consumption bug; no default timeout; middleware order matters for auth |

### networkx
| Angle | Sources | Key Takeaway |
|-------|---------|--------------|
| Official docs | 1 | DiGraph for directed edges; successors()=imports, predecessors()=imported-by; nodes must be hashable |
| Performance | 1 | ~100 bytes/edge; entire graph in Python dicts; fine at ClaudeBoost scale (hundreds of files) |
| Pitfalls | 1 | Not thread-safe — protect with write lock; G.copy() is shallow; never mutate during iteration |
| Security | 0 | ⚠ Not researched (no known CVEs; local data only) |
| Migration | 0 | ⚠ Not researched (stable API) |
| Integration | 0 | ⚠ Not researched (internal use, patterns derivable from codebase) |

### httpx + beautifulsoup4 + pymupdf
| Angle | Sources | Key Takeaway |
|-------|---------|--------------|
| Official docs | 2 | follow_redirects=False by default; split timeouts per axis; always use async with client.stream() |
| Security | 1 | PyMuPDF is AGPL v3 — commercial licence required for hosted SaaS |
| Performance | 1 | PyMuPDF flags=0 to skip image decoding; always use lxml parser with bs4 |
| Pitfalls | 2 | httpx connection leak on task cancellation; PoolTimeout on long-lived clients; bs4 pass response.text not .content |
| Migration | 0 | ⚠ Not researched (stable APIs in scope) |
| Integration | 0 | ⚠ Not researched (internal pipeline only) |

### tree-sitter
| Angle | Sources | Key Takeaway |
|-------|---------|--------------|
| Official docs | 1 | 0.25: QueryCursor required for .captures()/.matches(); parser.language = lang (not set_language) |
| Security | 1 | Pure text parser — no code execution risk; not thread-safe per Parser instance |
| Performance | 1 | Under 100ms for 10K-line files; TreeCursor much faster than recursive Node access |
| Migration | 1 | 0.25 breaks Query.captures() API; 0.23 breaks set_language() and keep_text kwarg |
| Integration | 1 | S-expression queries for function/class extraction; Tree must stay in scope while Nodes referenced |
| Pitfalls | 2 | Grammar/core ABI mismatch crashes silently; ERROR nodes collapse subtrees — check has_error before embedding |

## Uncovered Areas
- networkx: security, migration, and integration angles not researched (low priority, stable library)
- httpx+bs4+pymupdf: migration and integration angles not researched (stable APIs, internal use)
- graspologic: security and migration angles not researched (no known CVEs, local compute only)
- html2text: migration angle not researched (stable API, no breaking changes in scope)

---

# Run 2 — 2026-06-14

Last updated: 2026-06-14
Project: C:/Users/grayw/OneDrive/prj/ClaudeBoost

## Technologies Researched

| Technology | Version | Role | Sources | Confidence |
|------------|---------|------|---------|------------|
| watchdog | >=4.0 | File system monitoring | 5 (Tier A: 3, B: 2) | High |
| pathspec | >=0.12 | Gitignore path filtering | 4 (Tier A: 3, B: 1) | High |
| lxml | >=5.0 | XML/HTML parsing | 6 (Tier A: 4, B: 2) | High |
| html2text | >=2024.2 | HTML→Markdown conversion | 3 (Tier A: 2, B: 1) | Medium |
| graspologic | >=3.0 | Graph statistics [optional] | 3 (Tier A: 2, B: 1) | Medium |
| ollama | >=0.3 | Local LLM embeddings [optional] | 5 (Tier A: 2, B: 3) | High |

## Coverage by Technology

### watchdog
| Angle | Sources | Key Takeaway |
|-------|---------|--------------|
| Official docs | 2 | Observer.schedule() + start() + stop() + join() is the full lifecycle |
| Security | 1 | No CVEs; risk is in handler callbacks with attacker-controlled paths |
| Performance | 1 | Keep handlers fast; debounce for bulk writes |
| Migration | 1 | v4.0: FileSystemEvent is dataclass (repr changed); v5.0: keyword args enforced |
| Integration | 1 | ClaudeBoost uses _DebouncedHandler at 2.0s in core/watcher.py |
| Pitfalls | 2 | stop()+join() in finally; Windows delete ambiguity; BaseObserver for type hints |

### pathspec
| Angle | Sources | Key Takeaway |
|-------|---------|--------------|
| Official docs | 2 | GitIgnoreSpec.from_lines() for gitignore edge cases; PathSpec for basic use |
| Security | 0 | ⚠ Not researched (no known CVEs; pure string matching) |
| Performance | 1 | Compile once, reuse; pure Python so not a bottleneck at ClaudeBoost scale |
| Migration | 1 | 0.12: dir/* now matches all descendants; check_*() methods added |
| Integration | 0 | ⚠ Not researched (derivable from codebase) |
| Pitfalls | 2 | Forward-slash normalization on Windows critical; anchoring confusion; use GitIgnoreSpec |

### lxml
| Angle | Sources | Key Takeaway |
|-------|---------|--------------|
| Official docs | 2 | etree for XML; html for lenient HTML; XPath via .xpath() or compiled etree.XPath() |
| Security | 2 | 5.0 BREAKING: resolve_entities='internal' default; upgrade to 5.4.0+ for libxml2 2.13.8 |
| Performance | 1 | iterparse+elem.clear() for large files; compile XPath once; avoid // axis |
| Migration | 1 | 5.0→5.x: resolve_entities changed; iterparse fix landed post-5.0 |
| Integration | 1 | Use "lxml" as bs4 parser; trusted files use etree.parse(); untrusted use explicit parser |
| Pitfalls | 2 | Clark notation for namespaces; lxml.html silently recovers from malformed HTML |

### html2text
| Angle | Sources | Key Takeaway |
|-------|---------|--------------|
| Official docs | 2 | HTML2Text().handle(html); body_width, ignore_links, bypass_tables are the key options |
| Security | 0 | ⚠ Not researched (no known CVEs; pure text conversion) |
| Performance | 1 | Configuration choices drive downstream embedding cost, not conversion speed |
| Migration | 0 | ⚠ Not researched (stable API) |
| Integration | 1 | Set body_width=0, ignore_links=True, bypass_tables=True for RAG pipelines |
| Pitfalls | 2 | body_width=78 default hard-wraps text and breaks RAG quality |

### graspologic
| Angle | Sources | Key Takeaway |
|-------|---------|--------------|
| Official docs | 2 | ASE and LSE via pipeline module; sklearn-style API; auto elbow detection |
| Security | 0 | ⚠ Not researched (no CVEs; local in-memory computation) |
| Performance | 1 | SVD-based O(n^2) memory; randomized solver default is fast |
| Migration | 0 | ⚠ Not researched (API stable in 3.x) |
| Integration | 1 | adjacency_spectral_embedding(nx_graph) returns Embeddings object |
| Pitfalls | 2 | Edges must have numeric weights; no multigraph; DiGraph ASE returns latent_left |

### ollama
| Angle | Sources | Key Takeaway |
|-------|---------|--------------|
| Official docs | 2 | ollama.embed() for batching; AsyncClient for async; nomic-embed-text=768d |
| Security | 1 | No auth on Ollama by default; bind to 127.0.0.1; ChromaDB telemetry must be disabled |
| Performance | 1 | Use /api/embed (batch) not /api/embeddings (single); AsyncClient+gather for parallelism |
| Migration | 1 | qwen3-embedding is 2025-2026 SOTA; models are not dimension-compatible with each other |
| Integration | 1 | nomic-embed-text=768d matches BGE; never swap to mxbai-embed-large without rebuilding collections |
| Pitfalls | 2 | nomic-embed-text truncates at 2048 tokens (set num_ctx=8192); ChromaDB telemetry hangs in air-gapped env |

## Deferred (run /research-project again)
None — all dependencies from pyproject.toml now covered.
