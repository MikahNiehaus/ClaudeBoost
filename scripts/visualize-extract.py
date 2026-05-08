#!/usr/bin/env python3
"""ClaudeBoost self-map extractor. Outputs a clean layered graph for the visualize viewer."""

import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


def extract_agents(base: Path) -> list[dict]:
    """Extract agent cards from agents/*.xml."""
    cards = []
    agents_dir = base / "agents"
    if not agents_dir.exists():
        return cards

    opus_agents = {"architect-agent", "reviewer-agent", "ticket-analyst-agent"}

    for xml_file in sorted(agents_dir.glob("*.xml")):
        if xml_file.name.startswith("_"):
            continue
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
        except ET.ParseError:
            continue

        name = root.attrib.get("name", xml_file.stem)
        role = ""
        goal = ""

        role_el = root.find("role")
        if role_el is not None and role_el.text:
            role = role_el.text.strip()

        goal_el = root.find("goal")
        if goal_el is not None and goal_el.text:
            goal = goal_el.text.strip()

        model = "Opus" if name in opus_agents else "Sonnet"
        subtitle = f"{model} · {role[:60]}{'...' if len(role) > 60 else ''}" if role else model

        cards.append({
            "id": name,
            "title": name,
            "subtitle": subtitle,
            "detail": goal or role,
            "citations": [{"file": f"agents/{xml_file.name}", "lines": "1-end", "shows": "agent definition"}],
        })

    return cards


def build_graph(base: Path) -> dict:
    """Build the layered graph for ClaudeBoost self-map."""
    agent_cards = extract_agents(base)

    # Split agents into featured (Opus) and others
    opus_cards = [c for c in agent_cards if "Opus" in c.get("subtitle", "")]
    sonnet_cards = [c for c in agent_cards if "Opus" not in c.get("subtitle", "")]

    # Count knowledge bases
    kb_count = len(list((base / "knowledge").glob("*.xml"))) if (base / "knowledge").exists() else 0

    # Count slash commands
    cmd_count = len(list((base / ".claude" / "commands").glob("*.md"))) if (base / ".claude" / "commands").exists() else 0

    # Count hooks from setup.ps1
    hook_count = 0
    setup = base / "scripts" / "setup.ps1"
    if setup.exists():
        content = setup.read_text(encoding="utf-8-sig")
        hook_count = content.count("Install-HookEntry")

    return {
        "project": "ClaudeBoost",
        "title": "How ClaudeBoost Works",
        "subtitle": f"{len(agent_cards)} agents · {kb_count} knowledge bases · {hook_count} hooks · {cmd_count} commands",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "layers": [
            {
                "id": "user",
                "label": "INPUT",
                "cards": [
                    {
                        "id": "you",
                        "title": "You",
                        "subtitle": "Slash commands, chat, or pasted tickets",
                        "detail": "You interact with Claude normally. ClaudeBoost changes how Claude thinks and acts behind the scenes — enforcing standards, routing to specialist agents, and making sure architectural decisions go through you first.",
                    }
                ]
            },
            {
                "id": "core",
                "label": "CORE SYSTEM",
                "flow_label": "sends request to",
                "cards": [
                    {
                        "id": "orchestrator",
                        "title": "Orchestrator",
                        "subtitle": "Routes requests to the right agents",
                        "detail": "The brain of ClaudeBoost. It reads your request, classifies it (simple → just do it, complex → plan + delegate), creates workspace folders, picks which agents to spawn, and combines their outputs. It never writes code itself.",
                        "responsibilities": [
                            "Classify: simple task or complex task?",
                            "Create workspace folders for complex work",
                            "Choose which specialist agents to spawn",
                            "Combine agent outputs into your response",
                        ],
                        "citations": [{"file": "agents/_orchestrator.xml", "lines": "1-50", "shows": "decision tree"}],
                    },
                    {
                        "id": "consult",
                        "title": "CONSULT Mode",
                        "subtitle": "Asks before big architectural decisions",
                        "detail": "Default mode. Before any major decision (new endpoint, new dependency, auth strategy), Claude researches first, proposes 2-3 options, and asks you to pick. You add constraints on top — size caps, rate limits, charset restrictions. RAG-required standards (SQL parameterization, error logging) apply automatically.",
                        "responsibilities": [
                            "Research the project before proposing anything",
                            "Present 2-3 options with clear tradeoffs",
                            "Let you add constraints on top",
                            "Remember your choices for the session",
                        ],
                        "citations": [{"file": "knowledge/consult-mode.xml", "lines": "1-108", "shows": "full protocol"}],
                    },
                ],
            },
            {
                "id": "agents",
                "label": "SPECIALIST AGENTS",
                "flow_label": "delegates work to",
                "cards": opus_cards + [
                    {
                        "id": "other-agents",
                        "title": f"+{len(sonnet_cards)} more agents",
                        "subtitle": "Sonnet · test, debug, security, UI, docs, refactor...",
                        "detail": f"All {len(sonnet_cards)} Sonnet-powered specialists: " + ", ".join(c["title"] for c in sonnet_cards[:12]) + (f", and {len(sonnet_cards)-12} more" if len(sonnet_cards) > 12 else "") + ". Each is an expert in one domain. Up to 3 can run in parallel.",
                    },
                ],
            },
            {
                "id": "knowledge",
                "label": "KNOWLEDGE & SEARCH",
                "flow_label": "searches for standards in",
                "cards": [
                    {
                        "id": "rag",
                        "title": "RAG Search",
                        "subtitle": "Semantic search over all knowledge",
                        "detail": "An MCP server that indexes every knowledge base and agent definition. Agents ask natural language questions like 'SQL security standards' and RAG returns the right file. This is how agents know the rules without memorizing 38 documents.",
                        "responsibilities": [
                            "Index all knowledge bases on startup",
                            "Return relevant docs for natural language queries",
                            "Every agent must call it as their first action",
                        ],
                        "citations": [{"file": "mcp-rag-server/", "lines": "dir", "shows": "MCP server"}],
                    },
                    {
                        "id": "knowledge",
                        "title": f"{kb_count} Knowledge Bases",
                        "subtitle": "Security, testing, logging, architecture, and more",
                        "detail": f"XML files covering every domain: security standards, testing methodology, logging requirements, debugging, architecture patterns, coding standards, and more. These are the rules agents follow — searchable through RAG.",
                        "citations": [{"file": "knowledge/", "lines": "dir", "shows": "all knowledge bases"}],
                    },
                ],
            },
            {
                "id": "enforcement",
                "label": "SAFETY & ENFORCEMENT",
                "flow_label": "enforced by",
                "cards": [
                    {
                        "id": "hooks",
                        "title": f"{hook_count} Safety Hooks",
                        "subtitle": "Invisible guardrails that fire automatically",
                        "detail": "Claude Code hooks that inject rules at key moments. They remind Claude to use CONSULT mode before edits, verify agents loaded RAG, warn about unsafe process kills, and re-inject rules after context compaction. bash-guard.py is the only hook that mechanically blocks (cd+&& and backslash-space patterns).",
                        "responsibilities": [
                            "SessionStart: load rules into every session",
                            "PreToolUse: check before edits and agent spawns",
                            "PostToolUse: verify agent output has evidence",
                            "PreCompact: re-inject rules after memory compression",
                        ],
                        "citations": [{"file": "scripts/setup.ps1", "lines": "92-200", "shows": "hook installation"}],
                    },
                    {
                        "id": "verify",
                        "title": "Verify Gate",
                        "subtitle": "Anti-hallucination — every finding needs proof",
                        "detail": "Every finding an agent reports must cite a specific file and line number as proof. If it can't point to actual code, the finding gets dropped. 'Nothing found' is always a valid outcome. This prevents agents from inventing problems.",
                        "citations": [{"file": "knowledge/verify-gate.xml", "lines": "1-end", "shows": "verify gate protocol"}],
                    },
                ],
            },
        ],
    }


def main() -> None:
    if len(sys.argv) < 2:
        base = Path.cwd()
    else:
        base = Path(sys.argv[1])

    output = sys.argv[2] if len(sys.argv) >= 3 else "graph.json"

    graph = build_graph(base)
    Path(output).write_text(json.dumps(graph, indent=2, ensure_ascii=False), encoding="utf-8")
    total_cards = sum(len(layer.get("cards", [])) for layer in graph["layers"])
    print(f"Extracted {total_cards} cards in {len(graph['layers'])} layers -> {output}")


if __name__ == "__main__":
    main()
