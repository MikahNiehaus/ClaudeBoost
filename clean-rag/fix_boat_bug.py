#!/usr/bin/env python3
"""fix_boat_bug.py — detect and remove bloated ChromaDB project databases.

A healthy chroma.sqlite3 stays under 50 MB for most projects (up to ~10 000
chunks). When it exceeds 500 MB the index has accumulated free-list pages from
repeated delete-then-upsert cycles (ChromaDB issue #2143) and must be purged
and rebuilt from scratch.

Usage:
    python clean-rag/fix_boat_bug.py           # report only, prompt per project
    python clean-rag/fix_boat_bug.py --force   # delete all bloated without prompting

All deletions happen inside clean-rag/databases/_projects/ only.
Nothing outside this ClaudeBoost directory is touched.

After deletion, re-index each affected project:
    POST http://127.0.0.1:8613/index-project  {"project_path": "<path>"}
or from Claude Code:  /index-project <path>
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

CLEAN_RAG_HOME = Path(__file__).resolve().parent
DATABASES_DIR = CLEAN_RAG_HOME / "databases"
STATE_DIR = CLEAN_RAG_HOME / "state"
PROJECTS_JSON = STATE_DIR / "projects.json"

BLOAT_THRESHOLD_BYTES = 500 * 1024 * 1024  # 500 MB


def read_json(path: Path, default=None):
    if default is None:
        default = {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def fmt_size(n: int) -> str:
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.1f} GB"
    if n >= 1024 ** 2:
        return f"{n / 1024 ** 2:.1f} MB"
    return f"{n / 1024:.1f} KB"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Detect and remove bloated ChromaDB project databases"
    )
    parser.add_argument(
        "--force", action="store_true", help="Delete all bloated databases without prompting"
    )
    args = parser.parse_args()

    if not DATABASES_DIR.exists():
        print("No databases directory found. Nothing to check.")
        return 0

    projects = read_json(PROJECTS_JSON)
    pid_to_path = {
        pid: info.get("project_path", "<unknown>")
        for pid, info in projects.items()
        if isinstance(info, dict)
    }

    sqlite_files = sorted(DATABASES_DIR.glob("_projects/*/chroma/chroma.sqlite3"))

    if not sqlite_files:
        print("No project databases found.")
        return 0

    bloated = []
    print(f"\nScanning {len(sqlite_files)} project database(s) in:\n  {DATABASES_DIR}\n")
    for sqlite_path in sqlite_files:
        pid = sqlite_path.parent.parent.name
        size = sqlite_path.stat().st_size
        project_path = pid_to_path.get(pid, "<not in registry>")
        status = "BLOATED" if size >= BLOAT_THRESHOLD_BYTES else "ok    "
        print(f"  [{status}] {pid}  {fmt_size(size):>10}  {project_path}")
        if size >= BLOAT_THRESHOLD_BYTES:
            bloated.append((pid, sqlite_path.parent.parent, project_path, size))

    if not bloated:
        print("\nNo bloated databases found. All good.")
        return 0

    total_bloat = sum(s for _, _, _, s in bloated)
    print(f"\nFound {len(bloated)} bloated database(s) totalling {fmt_size(total_bloat)}:\n")
    for _, _, project_path, size in bloated:
        print(f"  {fmt_size(size):>10}  {project_path}")

    print()
    deleted = []
    for pid, pid_dir, project_path, size in bloated:
        if args.force:
            do_delete = True
        else:
            answer = input(f"Delete {project_path} ({fmt_size(size)})? [y/N] ").strip().lower()
            do_delete = answer == "y"

        if do_delete:
            shutil.rmtree(pid_dir, ignore_errors=True)
            projects.pop(pid, None)
            deleted.append(project_path)
            print(f"  Deleted: {pid_dir.name}  ({project_path})")
        else:
            print(f"  Skipped: {project_path}")

    if deleted:
        write_json(PROJECTS_JSON, projects)
        total_freed = sum(s for _, _, p, s in bloated if p in deleted)
        print(f"\nFreed ~{fmt_size(total_freed)} by removing {len(deleted)} database(s).")
        print("\nRe-index each deleted project to restore search:")
        for p in deleted:
            print(f"  /index-project {p}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
