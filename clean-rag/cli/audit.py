#!/usr/bin/env python
"""Walk the research audit chain and report anything that doesn't add up.

    python clean-rag/cli/audit.py verify      # check the chain, list ungated edits
    python clean-rag/cli/audit.py tail [N]    # last N edits, human readable

The audit log cannot stop anyone forging a research stamp. What it can do is make
the forgery permanent: every entry's hash folds in the previous entry's hash, so
altering or deleting one breaks every entry after it, exactly like rewriting an
old git commit changes every commit id downstream.

So "did anything edit code without research" stops being an unknowable and
becomes this command.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
import research_audit  # noqa: E402


def _fmt_ts(ts) -> str:
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(ts)))
    except (TypeError, ValueError):
        return "?"


def cmd_verify() -> int:
    r = research_audit.verify()

    print(f"Audit log: {r['path']}")

    if not r["exists"]:
        print("\nNo audit log yet. Nothing has been edited since it was turned on.")
        return 0

    print(f"Entries:   {r['entries']}")
    print()

    if r["chain_ok"]:
        print("CHAIN INTACT. No entry has been altered, deleted, or reordered.")
    else:
        print(f"CHAIN BROKEN: {len(r['breaks'])} problem(s).")
        print("Someone edited the log after the fact. Details:")
        for b in r["breaks"]:
            print(f"\n  line {b['line']}: {b['problem']}")
            if b.get("file"):
                print(f"    file:     {b['file']}")
            if b.get("expected"):
                print(f"    expected: {b['expected'][:32]}...")
                print(f"    found:    {str(b.get('found'))[:32]}...")

    print()

    ungated = r["ungated_edits"]
    if not ungated:
        print("Every allowed edit was covered by a research stamp.")
    else:
        print(f"{len(ungated)} EDIT(S) WENT THROUGH WITH NO COVERING RESEARCH:")
        print("(the gate said yes but no agent had scoped that file)")
        for u in ungated:
            print(f"\n  {_fmt_ts(u['ts'])}  {u['file']}")
            print(f"    reason recorded: {u.get('reason', '?')}")

    print()
    if r["chain_ok"] and not ungated:
        print("Clean.")
        return 0
    return 1


def cmd_tail(n: int = 20) -> int:
    import json

    path = research_audit.audit_path()
    if not path.exists():
        print("No audit log yet.")
        return 0

    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    for ln in lines[-n:]:
        try:
            e = json.loads(ln)
        except json.JSONDecodeError:
            print("  <corrupt line>")
            continue
        mark = "ok   " if e.get("allowed") else "BLOCK"
        agent = e.get("covering_agent") or "-"
        print(f"{_fmt_ts(e.get('ts'))}  {mark}  {e.get('file')}")
        print(f"                       via {agent}: {e.get('reason', '')}")
    return 0


def main() -> int:
    args = sys.argv[1:]
    cmd = args[0] if args else "verify"

    if cmd == "verify":
        return cmd_verify()
    if cmd == "tail":
        n = int(args[1]) if len(args) > 1 and args[1].isdigit() else 20
        return cmd_tail(n)

    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
