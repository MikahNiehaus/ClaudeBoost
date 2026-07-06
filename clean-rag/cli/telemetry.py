#!/usr/bin/env python3
"""CLI viewer for clean-rag telemetry.

Usage:
  python clean-rag/cli/telemetry.py              # summary of all events
  python clean-rag/cli/telemetry.py --tail 20     # last 20 events
  python clean-rag/cli/telemetry.py --type gate_block  # filter by type
  python clean-rag/cli/telemetry.py --stats       # aggregated stats
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def _telemetry_path() -> Path:
    import os
    home = os.environ.get("CLEAN_RAG_HOME", "")
    if home:
        return Path(home) / "state" / "telemetry.jsonl"
    return Path(__file__).resolve().parent.parent / "state" / "telemetry.jsonl"


def read_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").strip().split("\n"):
        if line.strip():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def show_tail(events: list[dict], n: int) -> None:
    for e in events[-n:]:
        ts = e.get("ts", "?")[:19]
        evt = e.get("event", "?")
        file = e.get("file", e.get("topic", e.get("query", "")))
        if len(str(file)) > 60:
            file = "..." + str(file)[-57:]
        reason = e.get("reason", "")
        score = e.get("score", e.get("best_score", ""))
        extra = ""
        if reason:
            extra = f" ({reason})"
        elif score:
            extra = f" (score={score})"
        print(f"  {ts}  {evt:15s}  {file}{extra}")


def show_stats(events: list[dict]) -> None:
    if not events:
        print("  No telemetry events recorded yet.")
        return

    type_counts = Counter(e.get("event", "unknown") for e in events)
    topic_counts = Counter()
    block_reasons = Counter()
    scores = []

    for e in events:
        if e.get("event") == "gate_pass":
            for t in e.get("topics", []):
                topic_counts[t] += 1
            if e.get("score"):
                scores.append(e["score"])
        elif e.get("event") == "gate_block":
            block_reasons[e.get("reason", "unknown")] += 1

    print("  Event counts:")
    for evt, count in type_counts.most_common():
        print(f"    {evt:20s}  {count}")

    if topic_counts:
        print("\n  Topics cited in passed proofs:")
        for topic, count in topic_counts.most_common(10):
            print(f"    {topic:20s}  {count}")

    if scores:
        avg = sum(scores) / len(scores)
        print(f"\n  Proof scores: avg={avg:.3f}, min={min(scores):.3f}, max={max(scores):.3f}")

    if block_reasons:
        print("\n  Block reasons:")
        for reason, count in block_reasons.most_common():
            print(f"    {reason:30s}  {count}")

    total = len(events)
    passes = type_counts.get("gate_pass", 0)
    blocks = type_counts.get("gate_block", 0)
    exempts = type_counts.get("gate_exempt", 0)
    if passes + blocks > 0:
        pass_rate = passes / (passes + blocks) * 100
        print(f"\n  Pass rate: {pass_rate:.1f}% ({passes} passed, {blocks} blocked, {exempts} exempt)")


def main():
    parser = argparse.ArgumentParser(description="clean-rag telemetry viewer")
    parser.add_argument("--tail", type=int, default=0, help="Show last N events")
    parser.add_argument("--type", default="", help="Filter by event type")
    parser.add_argument("--stats", action="store_true", help="Show aggregated stats")
    args = parser.parse_args()

    path = _telemetry_path()
    events = read_events(path)

    if args.type:
        events = [e for e in events if e.get("event") == args.type]

    if not events:
        print("No telemetry events recorded yet.")
        print(f"  Log path: {path}")
        return

    if args.stats:
        show_stats(events)
    elif args.tail > 0:
        show_tail(events, args.tail)
    else:
        print(f"clean-rag telemetry: {len(events)} events")
        print(f"  Log: {path}")
        print()
        show_stats(events)
        print()
        print("  Recent events:")
        show_tail(events, 10)


if __name__ == "__main__":
    main()
