"""Git sparse checkout for documentation repos.

Extracted from ClaudeBoost scripts/clone-docs.py. Layer 1 of the
four-layer research waterfall.

Usage:
  python -m clean_rag.research.clone_docs \
    --repo "fastapi/fastapi" --path "docs/en/docs" \
    --topic "fastapi"
"""

import argparse
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

from server.config import KNOWLEDGE_DIR

DEFAULT_EXTENSIONS = {".md", ".mdx", ".rst"}
GITHUB_BASE = "https://github.com/"


def run_git(args: list[str], cwd: str | None = None, timeout: int = 120) -> str:
    """Run a git command and return stdout. Raises on failure."""
    cmd = ["git"] + args
    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed:\n{result.stderr.strip()}")
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"git {' '.join(args)} timed out after {timeout}s")


def make_slug(filename: str, topic: str) -> str:
    """Create a KB-friendly filename with topic prefix."""
    name = filename.replace("\\", "/").strip("/")
    name = name.replace("/", "-")
    name = re.sub(r"[^a-z0-9.\-]", "", name.lower())
    name = re.sub(r"-+", "-", name).strip("-")
    topic_slug = re.sub(r"[^a-z0-9\-]", "", topic.lower().replace(" ", "-"))[:30]
    return f"{topic_slug}-{name}"


def clone_docs(
    repo: str,
    docs_path: str,
    topic: str,
    branch: str = "main",
    extensions: set[str] | None = None,
    kb_dir: pathlib.Path | None = None,
) -> dict:
    """Clone a GitHub repo's docs folder and copy files to knowledge/<topic>/.

    Returns a summary dict with counts.
    """
    if extensions is None:
        extensions = DEFAULT_EXTENSIONS

    if kb_dir is None:
        kb_dir = KNOWLEDGE_DIR / topic

    repo_url = f"{GITHUB_BASE}{repo}.git"
    stats = {
        "repo": repo,
        "docs_path": docs_path,
        "branch": branch,
        "files_copied": 0,
        "files_skipped": 0,
        "bytes_total": 0,
        "errors": [],
    }

    tmp_dir = tempfile.mkdtemp(prefix="crag_clone_")

    try:
        print(f"Cloning {repo} (sparse, branch: {branch})...")
        t0 = time.time()

        run_git(
            ["clone", "--filter=blob:none", "--sparse", "--branch", branch,
             "--single-branch", "--depth", "1", repo_url, tmp_dir],
            timeout=180,
        )
        run_git(["sparse-checkout", "set", docs_path], cwd=tmp_dir)

        clone_time = time.time() - t0
        print(f"  Clone completed in {clone_time:.1f}s")

        source_dir = pathlib.Path(tmp_dir) / docs_path.replace("/", os.sep)
        if not source_dir.exists():
            stats["errors"].append(f"Path {docs_path} not found in repo")
            return stats

        kb_dir.mkdir(parents=True, exist_ok=True)
        fetched_date = time.strftime("%Y-%m-%d")

        doc_files = []
        for root, _dirs, files in os.walk(source_dir):
            for fname in files:
                fpath = pathlib.Path(root) / fname
                if fpath.suffix.lower() in extensions:
                    rel = fpath.relative_to(source_dir)
                    doc_files.append((fpath, str(rel)))

        print(f"  Found {len(doc_files)} doc files")

        for fpath, rel_path in doc_files:
            slug = make_slug(rel_path, topic)
            out_path = kb_dir / slug

            if out_path.exists():
                stats["files_skipped"] += 1
                continue

            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                if len(content.strip()) < 50:
                    stats["files_skipped"] += 1
                    continue

                header = (
                    f"<!-- Source: github.com/{repo}/{docs_path}/{rel_path} | "
                    f"Tier: A | Topic: {topic} | Fetched: {fetched_date} -->\n\n"
                )
                out_path.write_text(header + content, encoding="utf-8")
                stats["files_copied"] += 1
                stats["bytes_total"] += out_path.stat().st_size
            except Exception as exc:
                stats["errors"].append(f"{rel_path}: {exc}")

        size_mb = stats["bytes_total"] / (1024 * 1024)
        print(f"  Copied {stats['files_copied']} files ({size_mb:.1f}MB), "
              f"skipped {stats['files_skipped']}")

    finally:
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass

    return stats


def main():
    parser = argparse.ArgumentParser(description="Clone docs from GitHub repos")
    parser.add_argument("--repo", required=True, help="GitHub repo (owner/name)")
    parser.add_argument("--path", required=True, help="Docs path within repo")
    parser.add_argument("--topic", default="", help="Topic name")
    parser.add_argument("--branch", default="main", help="Git branch")
    parser.add_argument("--extensions", default=".md,.mdx,.rst",
                        help="File extensions to include")
    parser.add_argument("--kb-dir", default="", help="Output directory override")

    args = parser.parse_args()
    topic = args.topic or args.repo.split("/")[-1]
    extensions = {ext.strip() for ext in args.extensions.split(",")}
    kb_dir = pathlib.Path(args.kb_dir) if args.kb_dir else None

    stats = clone_docs(
        repo=args.repo, docs_path=args.path, topic=topic,
        branch=args.branch, extensions=extensions, kb_dir=kb_dir,
    )
    print(f"\nDone: {stats['files_copied']} files from {stats['repo']}")


if __name__ == "__main__":
    main()
