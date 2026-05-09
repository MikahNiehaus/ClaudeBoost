"""Reinstall RAG server and repair ML dependency drift.

Run when check-rag-health.py returns non-zero.

What this does:
  1. Reinstalls rag_server in editable mode from $CLAUDEBOOST_HOME/mcp-rag-server.
  2. Force-upgrades the three ML packages whose versions drift independently
     (transformers, tokenizers, sentence-transformers). Another project installing
     a newer tokenizers can leave an older transformers in an incompatible state,
     producing ImportError("tokenizers>=0.14,<0.19 required") at RAG startup.
     Upgrading all three together restores a consistent set.

Computer-agnostic:
  - Uses sys.executable so the right Python's pip is invoked even in venvs.
  - Uses CLAUDEBOOST_HOME env var, falls back to the parent of this script.
"""
import os
import subprocess
import sys


def boost_home() -> str:
    env = os.environ.get("CLAUDEBOOST_HOME")
    if env and os.path.isdir(env):
        return env
    # Fallback: assume this file lives at <home>/scripts/reinstall-rag.py
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def run(args: list[str]) -> None:
    print(f"$ {' '.join(args)}")
    subprocess.run(args, check=True)


def main() -> int:
    rag_dir = os.path.join(boost_home(), "mcp-rag-server")
    pip = [sys.executable, "-m", "pip", "install"]

    # 1. Editable reinstall (fixes wrong install path).
    run(pip + ["-e", rag_dir])

    # 2. Upgrade ML deps as a set (fixes version drift). --upgrade-strategy eager
    # forces transitive deps to also move up so tokenizers can't stay stale.
    run(pip + [
        "--upgrade",
        "--upgrade-strategy", "eager",
        "sentence-transformers",
        "transformers",
        "tokenizers",
    ])

    # 3. Remove torchvision if it's incompatible with the installed torch.
    # We only do text embeddings — torchvision is never needed. A CUDA-built
    # torchvision installed alongside CPU torch raises RuntimeError on import,
    # which breaks the entire sentence_transformers import chain.
    tv_check = subprocess.run(
        [sys.executable, "-c", "import torchvision"],
        capture_output=True,
    )
    if tv_check.returncode != 0:
        print("torchvision import failed — uninstalling incompatible build")
        run([sys.executable, "-m", "pip", "uninstall", "torchvision", "-y"])

    print("RAG reinstall complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
