"""Reinstall RAG server in editable mode."""
import subprocess, os
rag_dir = os.path.join(os.environ.get("CLAUDEBOOST_HOME", "."), "mcp-rag-server")
subprocess.run(["pip", "install", "-e", "."], cwd=rag_dir, check=True)
