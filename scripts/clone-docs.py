"""
clone-docs.py — Clone documentation from GitHub repos via sparse checkout.

Layer 1 of the four layer research system. Highest quality source: official
docs already in markdown, no HTML conversion needed, no rate limiting.

Usage:
  python clone-docs.py --repo "fastapi/fastapi" --path "docs/en/docs" --kb-dir /path/to/kb
  python clone-docs.py --repo "reactjs/react.dev" --path "src/content" --topic "react" --branch "main"
  python clone-docs.py --repo "django/django" --path "docs" --kb-dir /path/to/kb --extensions ".txt,.rst"

What it does:
  1. Clones the repo with --filter=blob:none --sparse (no file content until needed)
  2. Sets sparse-checkout to only the docs path
  3. Copies all markdown/rst files to the KB directory with topic prefix
  4. Cleans up the temp clone

deps: git (must be on PATH)
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


DEFAULT_EXTENSIONS = {".md", ".mdx", ".rst"}
GITHUB_BASE = "https://github.com/"


def run_git(args: list[str], cwd: str | None = None, timeout: int = 120) -> str:
    """Run a git command and return stdout. Raises on failure."""
    cmd = ["git"] + args
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed:\n{result.stderr.strip()}")
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"git {' '.join(args)} timed out after {timeout}s")


def make_slug(filename: str, topic: str) -> str:
    """Create a KB-friendly filename with topic prefix."""
    # Strip leading path separators and normalize
    name = filename.replace("\\", "/").strip("/")
    # Replace path separators with dashes
    name = name.replace("/", "-")
    # Clean up
    name = re.sub(r"[^a-z0-9.\-]", "", name.lower())
    name = re.sub(r"-+", "-", name).strip("-")
    topic_slug = re.sub(r"[^a-z0-9\-]", "", topic.lower().replace(" ", "-"))[:30]
    return f"{topic_slug}-{name}"


def clone_docs(
    repo: str,
    docs_path: str,
    kb_dir: pathlib.Path,
    topic: str,
    branch: str = "main",
    extensions: set[str] | None = None,
) -> dict:
    """Clone a GitHub repo's docs folder and copy files to kb_dir.

    Returns a summary dict with counts.
    """
    if extensions is None:
        extensions = DEFAULT_EXTENSIONS

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

    # Create a temp directory for the sparse clone
    tmp_dir = tempfile.mkdtemp(prefix="cb_clone_")

    try:
        print(f"Cloning {repo} (sparse, branch: {branch})...")
        t0 = time.time()

        # Step 1: Clone with blob filter (downloads no file content yet)
        run_git(
            ["clone", "--filter=blob:none", "--sparse", "--branch", branch,
             "--single-branch", "--depth", "1", repo_url, tmp_dir],
            timeout=180,
        )

        # Step 2: Set sparse-checkout to only the docs path
        run_git(["sparse-checkout", "set", docs_path], cwd=tmp_dir)

        clone_time = time.time() - t0
        print(f"  Clone completed in {clone_time:.1f}s")

        # Step 3: Find all doc files in the checked-out path
        source_dir = pathlib.Path(tmp_dir) / docs_path.replace("/", os.sep)
        if not source_dir.exists():
            stats["errors"].append(f"Path {docs_path} not found in repo after checkout")
            print(f"  ERROR: {docs_path} not found in {repo}")
            return stats

        kb_dir.mkdir(parents=True, exist_ok=True)
        fetched_date = time.strftime("%Y-%m-%d")

        # Walk the docs directory
        doc_files = []
        for root, _dirs, files in os.walk(source_dir):
            for fname in files:
                fpath = pathlib.Path(root) / fname
                if fpath.suffix.lower() in extensions:
                    # Relative path from the docs root
                    rel = fpath.relative_to(source_dir)
                    doc_files.append((fpath, str(rel)))

        print(f"  Found {len(doc_files)} doc files in {docs_path}/")

        # Step 4: Copy files to KB directory
        for fpath, rel_path in doc_files:
            slug = make_slug(rel_path, topic)
            out_path = kb_dir / slug

            if out_path.exists():
                stats["files_skipped"] += 1
                continue

            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")

                # Skip tiny files (likely index stubs or empty)
                if len(content.strip()) < 50:
                    stats["files_skipped"] += 1
                    continue

                # Add source header
                header = (
                    f"<!-- Source: github.com/{repo}/{docs_path}/{rel_path} | "
                    f"Tier: A | Topic: {topic} | Fetched: {fetched_date} -->\n\n"
                )
                out_path.write_text(header + content, encoding="utf-8")
                file_size = out_path.stat().st_size
                stats["files_copied"] += 1
                stats["bytes_total"] += file_size
            except Exception as exc:
                stats["errors"].append(f"{rel_path}: {exc}")
                continue

        # Progress report
        size_mb = stats["bytes_total"] / (1024 * 1024)
        print(f"  Copied {stats['files_copied']} files ({size_mb:.1f}MB), "
              f"skipped {stats['files_skipped']}")
        if stats["errors"]:
            print(f"  Errors: {len(stats['errors'])}")
            for err in stats["errors"][:5]:
                print(f"    {err}")

    finally:
        # Step 5: Clean up temp clone
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Clone documentation from GitHub repos via sparse checkout"
    )
    parser.add_argument(
        "--repo", required=True,
        help="GitHub repo in owner/name format (e.g. fastapi/fastapi)"
    )
    parser.add_argument(
        "--path", required=True,
        help="Path to docs folder within the repo (e.g. docs/en/docs)"
    )
    parser.add_argument(
        "--kb-dir", required=True,
        help="Output KB directory for the markdown files"
    )
    parser.add_argument(
        "--topic", default="",
        help="Topic name for file prefixing (default: derived from repo name)"
    )
    parser.add_argument(
        "--branch", default="main",
        help="Git branch to clone (default: main)"
    )
    parser.add_argument(
        "--extensions", default=".md,.mdx,.rst",
        help="Comma separated file extensions to include (default: .md,.mdx,.rst)"
    )

    args = parser.parse_args()

    topic = args.topic or args.repo.split("/")[-1]
    kb_dir = pathlib.Path(args.kb_dir)
    extensions = {ext.strip() for ext in args.extensions.split(",")}

    stats = clone_docs(
        repo=args.repo,
        docs_path=args.path,
        kb_dir=kb_dir,
        topic=topic,
        branch=args.branch,
        extensions=extensions,
    )

    print(f"\n{'=' * 60}")
    print(f"Done: {stats['files_copied']} files from {stats['repo']}")
    print(f"KB directory: {kb_dir}")
    print(f"Files in KB: {len(list(kb_dir.glob('*.md')))}")

    if stats["errors"]:
        print(f"\nErrors ({len(stats['errors'])}):")
        for err in stats["errors"]:
            print(f"  {err}")

    print(f"\nIndex into RAG:")
    print(
        f'  curl -s -X POST http://127.0.0.1:8612/index '
        f'-H "Content-Type: application/json" '
        f'-d \'{{"project_path":"{kb_dir.parent}","force":true}}\''
    )


if __name__ == "__main__":
    main()
