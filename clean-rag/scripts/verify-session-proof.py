#!/usr/bin/env python3
"""verify-session-proof.py: post-session audit for claude -p sessions.

Citation: github.com/anthropics/claude-code#40506 (PreToolUse hooks do not
fire in non-interactive mode) and #38651 (Stop hook causes empty result in
print mode) -- both confirm hooks can silently not fire in `claude -p`
sessions, meaning proof-gate.py's enforcement may never run at all.

This script cannot fix that upstream bug. It runs *after* a `claude -p`
session exits and checks clean-rag/state/proof-log.jsonl and
search-log.jsonl for any activity in the session's time window. If files
changed in the target directory during that window but no proof-log entry
exists for them, that is direct evidence hooks did not fire.

Exit codes:
  0 = proof activity found for every file changed in the window (or no
      files changed at all)
  1 = files changed but zero proof-gate activity in the window -- hooks
      likely did not fire
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _clean_rag_home() -> Path:
    return Path(__file__).resolve().parent.parent


def _parse_ts(value: str) -> datetime:
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def _entries_in_window(entries: list[dict], since: datetime, until: datetime) -> list[dict]:
    result = []
    for entry in entries:
        ts_raw = entry.get("ts")
        if not ts_raw:
            continue
        try:
            ts = _parse_ts(ts_raw)
        except ValueError:
            continue
        if since <= ts <= until:
            result.append(entry)
    return result


def _files_changed_since(target_dir: Path, since: datetime) -> list[Path]:
    changed = []
    since_epoch = since.timestamp()
    for path in target_dir.rglob("*"):
        if not path.is_file():
            continue
        # skip common noise directories
        parts = {p.lower() for p in path.parts}
        if parts & {"node_modules", ".git", "__pycache__", ".rag-index"}:
            continue
        try:
            if path.stat().st_mtime >= since_epoch:
                changed.append(path)
        except OSError:
            continue
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", required=True, help="Session start, ISO 8601 (e.g. 2026-07-10T10:00:00Z)")
    parser.add_argument("--until", default=None, help="Session end, ISO 8601. Defaults to now.")
    parser.add_argument("--dir", required=True, help="Target directory the session was working in")
    args = parser.parse_args()

    since = _parse_ts(args.since)
    until = _parse_ts(args.until) if args.until else datetime.now(timezone.utc)
    target_dir = Path(args.dir)

    if not target_dir.exists():
        print(f"[ERROR] --dir does not exist: {target_dir}")
        return 1

    home = _clean_rag_home()
    proof_entries = _entries_in_window(_read_jsonl(home / "state" / "proof-log.jsonl"), since, until)
    search_entries = _entries_in_window(_read_jsonl(home / "state" / "search-log.jsonl"), since, until)

    changed_files = _files_changed_since(target_dir, since)

    proved_paths = set()
    for entry in proof_entries:
        file_str = entry.get("file", "")
        if file_str:
            proved_paths.add(str(Path(file_str).resolve()).lower())

    unproved = []
    for path in changed_files:
        if str(path.resolve()).lower() not in proved_paths:
            unproved.append(path)

    print(f"Session window: {since.isoformat()} .. {until.isoformat()}")
    print(f"Target dir: {target_dir}")
    print(f"Files changed in window: {len(changed_files)}")
    print(f"proof-log entries in window: {len(proof_entries)}")
    print(f"search-log entries in window: {len(search_entries)}")

    if not changed_files:
        print("[OK] No files changed in this window -- nothing to verify.")
        return 0

    if not proof_entries and not search_entries:
        print(
            "[FAIL] Files changed but zero proof-gate or search activity in the "
            "session window. This matches the known claude -p hooks-not-firing "
            "pattern (github.com/anthropics/claude-code#40506, #38651) -- "
            "proof-gate almost certainly never ran for this session."
        )
        for path in changed_files:
            print(f"  unverified: {path}")
        return 1

    if unproved:
        print(
            f"[WARN] {len(unproved)} of {len(changed_files)} changed files have "
            "no matching proof-log entry, even though some proof/search activity "
            "did happen this session:"
        )
        for path in unproved:
            print(f"  unverified: {path}")
        return 1

    print("[OK] Every changed file has a matching proof-log entry.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
