"""Instruction files must not route work to agents that do not exist.

An unknown agent name silently becomes a generic agent. Prose docs are excluded.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PHANTOMS = (
    "architect", "reviewer", "ticket-analyst", "debug", "test", "security",
    "performance", "refactor", "ui", "docs", "explore", "browser", "e2e",
    "workflow", "compliance", "standards-validator", "estimator", "devops",
    "database", "observability", "rag-indexing", "evaluator", "triage",
    "verifier",
)
PATTERN = re.compile(r"\b(?:%s)-agent\b" % "|".join(map(re.escape, PHANTOMS)))
# Anchored to the name so an unrelated "removed" elsewhere on the line exempts nothing.
HISTORY = re.compile(r"\bremoved\s+`?$")

_PORTABLE = ROOT / "clean-rag" / "portable"
SOURCES = {
    ".claude/commands": lambda: (ROOT / ".claude" / "commands").glob("*.md"),
    ".claude/skills": lambda: (ROOT / ".claude" / "skills").rglob("*.md"),
    "portable/agents": lambda: (_PORTABLE / "agents").glob("*.md"),
    "portable/skills": lambda: (_PORTABLE / "skills").rglob("*.md"),
    "portable/CLAUDE.md": lambda: [_PORTABLE / "CLAUDE.md"],
    "clean-rag/CLAUDE.md": lambda: [ROOT / "clean-rag" / "CLAUDE.md"],
}


def _instruction_files():
    for files in SOURCES.values():
        yield from files()


def phantom_hits(line: str) -> list[str]:
    return [m.group(0) for m in PATTERN.finditer(line)
            if not HISTORY.search(line[:m.start()])]


def test_every_source_contributes_files():
    empty = [name for name, files in SOURCES.items()
             if not [p for p in files() if p.is_file()]]
    assert not empty, f"no instruction files found under {empty}"


def test_every_live_instruction_location_is_guarded():
    scanned = {p.resolve() for p in _instruction_files()}
    required = [
        ROOT / "clean-rag" / "CLAUDE.md",
        _PORTABLE / "CLAUDE.md",
        *(ROOT / ".claude" / "skills").rglob("*.md"),
        *(ROOT / ".claude" / "commands").glob("*.md"),
        *(_PORTABLE / "agents").glob("*.md"),
        *(_PORTABLE / "skills").rglob("*.md"),
    ]
    missing = [str(p.relative_to(ROOT)) for p in required if p.resolve() not in scanned]
    assert not missing, missing


def test_no_instruction_file_names_a_phantom_agent():
    hits = []
    for path in _instruction_files():
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if phantom_hits(line):
                hits.append(f"{path.relative_to(ROOT)}:{n}: {line.strip()}")
    assert not hits, "\n".join(hits)


def test_the_pattern_bites():
    assert phantom_hits("spawn architect-agent next")
    assert phantom_hits("| Docs | docs-agent |")
    assert not phantom_hits("spawn research-agent next")
    assert not phantom_hits("spawn bad-cop next")


def test_only_a_history_note_naming_the_agent_is_exempt():
    assert not phantom_hits("the removed triage-agent decided without reading")
    assert not phantom_hits("The removed `triage-agent` (Haiku) sat in front")
    assert phantom_hits("If unsure, spawn ui-agent. This note has not been removed yet.")
    assert phantom_hits("The removed triage-agent is gone; spawn ui-agent instead.")
