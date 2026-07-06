"""Structured event logging for clean-rag observability.

Append-only JSONL event log. Each event has a type, timestamp, and
contextual fields. Based on structured audit logging patterns from
indexed research (chromadb observability, clean-rag-security audit trail).

Event types:
  gate_block   - proof-gate blocked an edit (no proof or invalid proof)
  gate_pass    - proof-gate accepted a proof and allowed the edit
  gate_exempt  - proof-gate skipped check (exempt path or extension)
  gate_auto    - proof-gate bypassed in AUTO mode
  search       - RAG search was performed
  acquire      - topic acquisition was triggered
  research     - parallel research agent was spawned
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _telemetry_path() -> Path:
    home = os.environ.get("CLEAN_RAG_HOME", "")
    if home:
        return Path(home) / "state" / "telemetry.jsonl"
    return Path(__file__).resolve().parent.parent / "state" / "telemetry.jsonl"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def log_event(event_type: str, **kwargs) -> None:
    entry = {"ts": _utc_now(), "event": event_type}
    entry.update(kwargs)
    try:
        path = _telemetry_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def gate_block(file: str, reason: str) -> None:
    log_event("gate_block", file=file, reason=reason)


def gate_pass(file: str, topics: list, score: float) -> None:
    log_event("gate_pass", file=file, topics=topics, score=score)


def gate_exempt(file: str, reason: str) -> None:
    log_event("gate_exempt", file=file, reason=reason)


def gate_auto(file: str) -> None:
    log_event("gate_auto", file=file)


def search_event(query: str, sources: list, result_count: int, best_score: float) -> None:
    log_event("search", query=query[:200], sources=sources,
              result_count=result_count, best_score=best_score)


def acquire_event(topic: str, category: str, covered: bool, files: int) -> None:
    log_event("acquire", topic=topic, category=category,
              covered=covered, files_acquired=files)


def research_spawn(topic: str, category: str) -> None:
    log_event("research_spawn", topic=topic, category=category)
