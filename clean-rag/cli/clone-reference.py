"""Clone an external reference repo, strip .git, and index it into clean-rag.

For studying or pattern-matching against a third-party repo without turning
it into a nested git repo or a tracked dependency: shallow clone, capture
provenance (URL + commit SHA) before .git is gone, then hand the plain
directory to the same /index-project endpoint any other project uses.

Never triggers a GraphRAG build. That stays manual, via the /graphrag skill.

Usage:
  python clean-rag/cli/clone-reference.py <repo-url> <dest-path>
  python clean-rag/cli/clone-reference.py <repo-url> <dest-path> --force
"""

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

DANGEROUS_FLAGS = {"--upload-pack", "--template", "--config", "-c"}


def _base_url() -> str:
    port = os.environ.get("CLEAN_RAG_PORT", "8613")
    return f"http://127.0.0.1:{port}"


def _clear_readonly_and_retry(func, path, _exc):
    """shutil.rmtree error handler for Windows.

    Git writes pack/idx files read-only (-r--r--r--), and Windows refuses to
    delete a read-only file, so rmtree raises PermissionError [Errno 13] on
    them. Clear the read-only bit and reattempt the removal. This is the
    canonical CPython-documented workaround (shutil.rmtree onexc example).
    The third argument is the exception (onexc) or exc_info tuple (onerror);
    unused, so the handler works for either signature.
    """
    os.chmod(path, stat.S_IWRITE)
    func(path)


def _validate_repo_url(url: str) -> None:
    """Same denylist clean-rag already enforces on research-agent's caged
    Bash (hooks/research-agent-bash-guard.py, _check_git_clone): https only,
    no ext:: transport, no flag-injection lookalikes. git's own flag surface
    is a documented arbitrary-command vector (CVE-2022-25900,
    GHSA-jcxm-m3jx-f287), and this script builds an argv list from a
    user-typed string, so the same checks apply here.
    """
    if not url.startswith("https://"):
        sys.exit(
            f"Error: repo URL must start with https:// "
            f"(blocks git://, ssh://, local paths, and the ext:: transport vector): {url!r}"
        )
    if "ext::" in url:
        sys.exit(f"Error: ext:: transport is a documented command-execution vector: {url!r}")
    for flag in DANGEROUS_FLAGS:
        if flag in url:
            sys.exit(
                f"Error: {flag!r} in the URL is a documented git command-execution "
                f"vector (CVE-2022-25900 / GHSA-jcxm-m3jx-f287): {url!r}"
            )


def run_git(args: list[str], cwd: str | None = None, timeout: int = 180) -> str:
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


def cmd_clone(args):
    _validate_repo_url(args.repo_url)

    dest = Path(args.dest).resolve()
    if dest.exists() and any(dest.iterdir()):
        sys.exit(f"Error: destination {dest} already exists and is not empty")
    dest.parent.mkdir(parents=True, exist_ok=True)

    print(f"Cloning {args.repo_url} (shallow, --depth 1)...")
    run_git(["clone", "--depth", "1", args.repo_url, str(dest)])

    commit_sha = run_git(["rev-parse", "HEAD"], cwd=str(dest))

    provenance = {
        "repo_url": args.repo_url,
        "commit_sha": commit_sha,
        "cloned_at": datetime.now(timezone.utc).isoformat(),
    }
    (dest / ".claudeboost-provenance.json").write_text(
        json.dumps(provenance, indent=2), encoding="utf-8"
    )

    git_dir = dest / ".git"
    if git_dir.exists():
        # Python 3.12 renamed rmtree's error hook onerror to onexc; use whichever
        # this interpreter supports so the read only pack files actually get removed.
        if sys.version_info >= (3, 12):
            shutil.rmtree(git_dir, onexc=_clear_readonly_and_retry)
        else:
            shutil.rmtree(git_dir, onerror=_clear_readonly_and_retry)
    if git_dir.exists():
        sys.exit(
            f"Error: failed to strip .git from {dest}; it still exists after removal. "
            "Refusing to report success or index a directory that is still a git repo."
        )
    print(f"  Commit: {commit_sha}")
    print(f"  Stripped .git, wrote provenance to {dest / '.claudeboost-provenance.json'}")

    try:
        resp = httpx.post(
            f"{_base_url()}/index-project",
            json={"project_path": str(dest), "force": args.force},
            timeout=600,
        )
        data = resp.json()
        if "error" in data:
            print(f"Error: {data['error']}")
            sys.exit(1)
        print(f"Indexed: {data.get('project_path', str(dest))}")
        print(f"  ID: {data.get('project_id', '?')}")
        print(f"  Files indexed: {data.get('files_indexed', 0)}")
        print(f"  Chunks created: {data.get('chunks_created', 0)}")
        print(f"  Elapsed: {data.get('elapsed_s', 0)}s")
        print(
            "\nVector + import graph index only. GraphRAG was NOT built — "
            "that stays manual, run the /graphrag skill against this path "
            "if you want the semantic layer too."
        )
    except httpx.ConnectError:
        print("clean-rag server not running. Start it first.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Clone a reference repo, strip .git, and index it into clean-rag"
    )
    parser.add_argument("repo_url", help="https:// URL of the repo to clone")
    parser.add_argument("dest", help="Destination directory (must not already exist with content)")
    parser.add_argument("--force", action="store_true",
                        help="Force full reindex (discard existing)")
    args = parser.parse_args()
    cmd_clone(args)


if __name__ == "__main__":
    main()
