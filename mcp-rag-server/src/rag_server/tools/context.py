"""build_context — tiered context assembly for rag_context tool.

Extracted from server.py so changes hot-reload without a server restart.
Called by server.py with explicit store/embedder/project_root dependencies.
"""

import logging
import re as _re
from pathlib import Path

logger = logging.getLogger(__name__)


def build_context(
    agent: str,
    task_description: str,
    max_tokens: int,
    store,
    embedder,
    project_root: Path,
    weight: str = "standard",
    project_path: str | None = None,
    code_embedder=None,
) -> dict:
    """Build a tiered context package for an agent.

    Tier 0: Agent definition (always included, full text)
    Tier 1: Universal guardrails (skipped for lightweight agents)
    Tier 2: Agent-declared knowledge bases (from <knowledge-base> tags)
    Tier 3: Semantic search fills remaining budget (knowledge only, not agents)
    Tier 4: Codebase search (if project_path provided and index exists)
    Tier 4b: Graph structural neighbours (auto-appended to Tier 4 when graph index exists)
    """
    from rag_server.indexing.markdown_chunker import estimate_tokens

    tier_errors: list[dict] = []

    # --- Tier 0: Agent definition ---
    agent_file = f"agents/{agent}.md"
    agent_def = ""
    agent_path = project_root / agent_file
    try:
        if agent_path.exists():
            agent_def = agent_path.read_text(encoding="utf-8")
        else:
            agent_path_xml = project_root / f"agents/{agent}.xml"
            if agent_path_xml.exists():
                agent_def = agent_path_xml.read_text(encoding="utf-8")
                agent_file = f"agents/{agent}.xml"
    except Exception as e:
        logger.error("Tier 0: failed to read agent definition for %r: %s", agent, e)
        tier_errors.append({"tier": "agent_definition", "error": str(e)})

    agent_tokens = estimate_tokens(agent_def)
    remaining_budget = max(0, max_tokens - agent_tokens)

    # Pre-reserve Tier 4 budget before Tiers 1-3 consume everything.
    # Without this, Tiers 1-3 starve Tier 4 at tight max_tokens budgets.
    tier4_reserved = 0
    if project_path and remaining_budget > 400:
        tier4_reserved = min(600, remaining_budget // 4)
        remaining_budget -= tier4_reserved

    # --- Parse agent's declared knowledge bases ---
    declared_files = []
    if agent_def:
        for match in _re.finditer(r'<(?:primary|secondary)\s+file="([^"]+)"', agent_def):
            declared_files.append(match.group(1))

    # --- Tier 1: Universal guardrails (skipped for lightweight agents) ---
    GUARDRAIL_FILES = [
        "knowledge/security.xml",
        "knowledge/observability.xml",
        "knowledge/coding-standards.xml",
        "knowledge/scope-governance.xml",
    ]

    tier1_chunks = []
    tier1_tokens = 0
    tier1_sources_seen = set()

    skip_guardrails = weight == "lightweight"

    for guardrail_file in GUARDRAIL_FILES:
        if skip_guardrails:
            break
        if tier1_tokens >= remaining_budget * 0.4:
            break
        try:
            chunks = store.get_by_source("knowledge", guardrail_file)
        except Exception as e:
            logger.error("Tier 1: failed to load guardrail %r: %s", guardrail_file, e)
            tier_errors.append({"tier": "guardrails", "file": guardrail_file, "error": str(e)})
            continue
        for chunk in chunks:
            chunk_tokens = chunk.metadata.get("token_count", estimate_tokens(chunk.content))
            if tier1_tokens + chunk_tokens > remaining_budget * 0.4:
                break
            tier1_chunks.append({
                "source": chunk.metadata.get("source_file", guardrail_file),
                "section": chunk.metadata.get("section", ""),
                "content": chunk.content,
                "score": 1.0,
                "tier": "guardrail",
            })
            tier1_tokens += chunk_tokens
            tier1_sources_seen.add(guardrail_file)

    remaining_budget -= tier1_tokens

    # --- Tier 2: Agent-declared knowledge bases ---
    tier2_chunks = []
    tier2_tokens = 0
    tier2_sources_seen = set()
    for declared_file in declared_files:
        if declared_file in tier1_sources_seen:
            continue
        if tier2_tokens >= remaining_budget * 0.5:
            break
        try:
            chunks = store.get_by_source("knowledge", declared_file)
        except Exception as e:
            logger.error("Tier 2: failed to load declared file %r: %s", declared_file, e)
            tier_errors.append({"tier": "declared", "file": declared_file, "error": str(e)})
            continue
        for chunk in chunks:
            chunk_tokens = chunk.metadata.get("token_count", estimate_tokens(chunk.content))
            if tier2_tokens + chunk_tokens > remaining_budget * 0.5:
                break
            tier2_chunks.append({
                "source": chunk.metadata.get("source_file", declared_file),
                "section": chunk.metadata.get("section", ""),
                "content": chunk.content,
                "score": 1.0,
                "tier": "declared",
            })
            tier2_tokens += chunk_tokens
            tier2_sources_seen.add(declared_file)

    remaining_budget -= tier2_tokens

    # --- Tier 3: Semantic search for task-relevant knowledge ---
    all_included_sources = tier1_sources_seen | tier2_sources_seen
    tier3_chunks = []
    tier3_tokens = 0

    if remaining_budget > 200 and store.collection_exists("knowledge"):
        # Guard: skip embedding call if model isn't loaded yet.
        if not embedder.is_loaded:
            tier_errors.append({
                "tier": "search",
                "error": "Embedding model not ready yet — server is warming up. Tier 3 skipped.",
            })
        else:
            try:
                # Multi-query: 3 variants cover vocabulary gaps between task description
                # and knowledge file language. Deduplicate by source before budget gating.
                _agent_label = agent.replace("-agent", "").replace("-", " ")
                _queries = [
                    task_description,
                    f"{_agent_label} {task_description}",
                    f"how to {task_description}",
                ]
                _seen_ids: set[str] = set()
                _all_hits: list = []
                for _q in _queries:
                    _qe = embedder.embed_query(_q)
                    _hits = store.search("knowledge", _qe, limit=10, min_score=0.4)
                    for _h in _hits:
                        _src = _h.metadata.get("source_file", "")
                        _uid = f"{_src}::{_h.content[:60]}"
                        if _uid not in _seen_ids:
                            _seen_ids.add(_uid)
                            _all_hits.append(_h)
                # Sort merged results by score descending
                _all_hits.sort(key=lambda r: r.score, reverse=True)
                for r in _all_hits:
                    source = r.metadata.get("source_file", "")
                    if source in all_included_sources:
                        continue
                    chunk_tokens = r.metadata.get("token_count", estimate_tokens(r.content))
                    if tier3_tokens + chunk_tokens > remaining_budget:
                        break
                    tier3_chunks.append({
                        "source": source,
                        "section": r.metadata.get("section", ""),
                        "content": r.content,
                        "score": r.score,
                        "tier": "search",
                    })
                    tier3_tokens += chunk_tokens
            except Exception as e:
                logger.error("Tier 3: semantic search failed: %s", e)
                tier_errors.append({"tier": "search", "error": str(e)})

    remaining_budget -= tier3_tokens

    # --- Tier 4: Codebase search (if project indexed) ---
    tier4_chunks = []
    tier4_tokens = 0

    _code_emb = code_embedder if code_embedder is not None else embedder
    if project_path and (tier4_reserved > 100 or remaining_budget > 200) and _code_emb.is_loaded:
        try:
            from rag_server.core.project import project_index_dir
            from rag_server.core.store import ChromaStore as _ChromaStore

            idx_dir = project_index_dir(project_path)
            chroma_dir = idx_dir / "chroma"
            if chroma_dir.exists():
                project_store = _ChromaStore(persist_dir=str(chroma_dir))
                if project_store.collection_exists("codebase") and project_store.count("codebase") > 0:
                    tier4_budget = tier4_reserved if tier4_reserved > 0 else min(600, remaining_budget)
                    query_embedding = _code_emb.embed_query(task_description)
                    codebase_results = project_store.search(
                        "codebase", query_embedding, limit=10, min_score=0.35,
                    )
                    # Prose docs (.md/.rst/.txt) match query vocabulary well but rarely
                    # contain what agents need — penalise them so source code ranks first.
                    _DOC_EXTS = {".md", ".mdx", ".rst", ".txt"}
                    codebase_results.sort(
                        key=lambda r: r.score * (0.80 if any(
                            r.metadata.get("source_file", "").endswith(ext) for ext in _DOC_EXTS
                        ) else 1.0),
                        reverse=True,
                    )
                    for r in codebase_results:
                        chunk_tokens = r.metadata.get("token_count", estimate_tokens(r.content))
                        # Always include the first chunk even if it exceeds the budget —
                        # prevents returning 0 results when a single large chunk fills the slot.
                        if tier4_tokens > 0 and tier4_tokens + chunk_tokens > tier4_budget:
                            break
                        tier4_chunks.append({
                            "source": r.metadata.get("source_file", ""),
                            "section": r.metadata.get("section", ""),
                            "content": r.content,
                            "score": r.score,
                            "tier": "codebase",
                        })
                        tier4_tokens += chunk_tokens

                    # --- Tier 4b: Graph structural neighbours ---
                    graph_db = idx_dir / "graph.db"
                    if graph_db.exists() and tier4_chunks:
                        try:
                            from rag_server.adapters.sqlite_graph_store import SQLiteGraphStore
                            graph_store = SQLiteGraphStore(graph_db)
                            if graph_store.has_graph():
                                seen_sources = {c["source"] for c in tier4_chunks}
                                graph_budget = max(0, (remaining_budget - tier4_tokens) // 2)
                                graph_tokens = 0

                                for seed_chunk in tier4_chunks[:3]:
                                    seed_file = seed_chunk["source"]
                                    neighbours = graph_store.get_neighbours(seed_file, depth=1)
                                    for edge in neighbours:
                                        nb_file = (
                                            edge.target_file
                                            if edge.source_file == seed_file
                                            else edge.source_file
                                        )
                                        if not nb_file or nb_file == "_external_" or nb_file in seen_sources:
                                            continue
                                        if graph_tokens >= graph_budget:
                                            break
                                        nb_chunks = project_store.get_by_source("codebase", nb_file)
                                        for nb in nb_chunks[:2]:
                                            nb_tokens = nb.metadata.get("token_count", estimate_tokens(nb.content))
                                            if graph_tokens + nb_tokens > graph_budget:
                                                break
                                            tier4_chunks.append({
                                                "source": nb_file,
                                                "section": nb.metadata.get("section", ""),
                                                "content": nb.content,
                                                "score": max(0.0, seed_chunk["score"] - 0.15),
                                                "tier": "codebase_graph",
                                            })
                                            graph_tokens += nb_tokens
                                            tier4_tokens += nb_tokens
                                        seen_sources.add(nb_file)
                        except Exception as e:
                            logger.error("Tier 4b: graph expansion failed: %s", e)
                            tier_errors.append({"tier": "codebase_graph", "error": str(e)})

                    # --- Tier 4c: Community summaries for files in scope ---
                    _graph_db_4c = idx_dir / "graph.db"
                    if _graph_db_4c.exists() and tier4_chunks:
                        try:
                            from rag_server.adapters.sqlite_graph_store import SQLiteGraphStore as _SGS4c
                            _gs4c = _SGS4c(_graph_db_4c)
                            if _gs4c.has_graph():
                                _seen_cids: set[int] = set()
                                _community_budget = min(400, max(0, remaining_budget - tier4_tokens))
                                _community_tokens = 0
                                for _ck in list(tier4_chunks):
                                    if _community_tokens >= _community_budget:
                                        break
                                    _cid4 = _gs4c.get_community_for_file(_ck["source"])
                                    if _cid4 is None or _cid4 in _seen_cids:
                                        continue
                                    _seen_cids.add(_cid4)
                                    _crow = _gs4c.get_community_summary(_cid4)
                                    if not _crow or not _crow.get("summary"):
                                        continue
                                    _ctokens = estimate_tokens(_crow["summary"])
                                    if _community_tokens + _ctokens > _community_budget:
                                        break
                                    tier4_chunks.append({
                                        "source": f"community:{_cid4}",
                                        "section": "community_summary",
                                        "content": _crow["summary"],
                                        "score": 0.85,
                                        "tier": "community_summary",
                                    })
                                    _community_tokens += _ctokens
                                    tier4_tokens += _ctokens
                        except Exception as _e4c:
                            logger.debug("Tier 4c: community summary lookup failed: %s", _e4c)

                project_store.close()

        except Exception as e:
            logger.error("Tier 4: codebase search failed for project %r: %s", project_path, e)
            tier_errors.append({"tier": "codebase", "error": str(e)})

    all_knowledge = tier1_chunks + tier2_chunks + tier3_chunks + tier4_chunks
    total_tokens = agent_tokens + tier1_tokens + tier2_tokens + tier3_tokens + tier4_tokens

    result = {
        "agent_definition": agent_def,
        "agent_file": agent_file,
        "weight": weight,
        "relevant_knowledge": all_knowledge,
        "total_tokens_approx": total_tokens,
        "sources_used": len(all_knowledge) + (1 if agent_def else 0),
        "tier_summary": {
            "guardrails": len(tier1_chunks),
            "declared": len(tier2_chunks),
            "search": len(tier3_chunks),
            "codebase": sum(1 for c in tier4_chunks if c["tier"] != "community_summary"),
            "community_summaries": sum(1 for c in tier4_chunks if c["tier"] == "community_summary"),
        },
    }
    if agent_tokens > max_tokens:
        result["warning"] = (
            f"Agent definition ({agent_tokens} tokens) exceeds max_tokens={max_tokens}. "
            "No knowledge chunks were loaded. Increase max_tokens to at least "
            f"{agent_tokens + 500} to include guardrails and declared knowledge."
        )
    elif not agent_def:
        result["warning"] = f"Agent definition not found for {agent!r} (checked .md and .xml)."
        logger.error("Tier 0: no agent definition found for %r under %s", agent, project_root)
    if tier_errors:
        result["tier_errors"] = tier_errors
    return result
