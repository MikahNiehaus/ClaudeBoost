"""
Download and cache the Jina code embedding model for ClaudeBoost.

Run this ONCE before setting RAG_CODE_EMBEDDING_MODEL:
    python benchmarks/codesearchnet/setup_code_model.py

Then restart the RAG server with:
    set RAG_CODE_EMBEDDING_MODEL=jinaai/jina-code-embeddings-0.5b
    python scripts/rag-server-start.py

After restart, re-index any codebase you want to search:
    POST http://127.0.0.1:8612/index  {"project_path": "...", "force": true}

Requirements: transformers>=4.53.0, torch>=2.7.1  (no trust_remote_code needed)
"""
import sys

print("Downloading jinaai/jina-code-embeddings-0.5b (~500M params, ~1GB download)...")
print("This is a one-time download. Subsequent starts use the cached version.")

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    print("ERROR: sentence-transformers not installed.")
    print("Run: pip install sentence-transformers")
    sys.exit(1)

model_id = "jinaai/jina-code-embeddings-0.5b"

try:
    model = SentenceTransformer(model_id)
    dims = model.get_sentence_embedding_dimension()
    print(f"Downloaded and cached: {model_id}")
    print(f"Dimensions: {dims}")

    # Smoke test — asymmetric query/doc prefixes
    doc_prefix   = "Represent the following code: "
    query_prefix = "Represent the following query to retrieve code: "

    code_vec  = model.encode(doc_prefix + "def hello(): return 'world'")
    query_vec = model.encode(query_prefix + "function that returns hello world")
    print(f"Smoke test OK — code embedding shape: {code_vec.shape}, query embedding shape: {query_vec.shape}")
    print()
    print("Next steps:")
    print("  1. set RAG_CODE_EMBEDDING_MODEL=jinaai/jina-code-embeddings-0.5b")
    print("  2. Restart the RAG server")
    print("  3. Re-index your codebase (force=true)")
    print("  4. Run: python benchmarks/codesearchnet/benchmark.py")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
