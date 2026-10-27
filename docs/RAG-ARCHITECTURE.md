# RAG Architecture

This file described the old search server: `mcp-rag-server/` on port 8612, its
`/context` and `/index` routes, a ports and adapters module layout, ChromaDB
storage, and a separate index over `agents/*.xml` and `knowledge/*.xml`. None of
that exists any more.

The search server today is clean-rag on port 8613. Read `clean-rag/CLAUDE.md`
for its routes and internals, and section 8 of `docs/CLAUDEBOOST-REFERENCE.md`
for how the rest of ClaudeBoost uses it.
