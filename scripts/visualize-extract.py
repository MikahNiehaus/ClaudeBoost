#!/usr/bin/env python3
"""ClaudeBoost self-map extractor. Outputs a rich layered graph for the visualize viewer."""

import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


# Agent groupings for column layout
OPUS_AGENTS = {"architect-agent", "reviewer-agent", "ticket-analyst-agent"}
QUALITY_AGENTS = {
    "security-agent", "test-agent", "debug-agent",
    "performance-agent", "refactor-agent", "evaluator-agent",
}
SUPPORT_AGENTS = {
    "docs-agent", "ui-agent", "workflow-agent",
    "explore-agent", "estimator-agent", "browser-agent",
    "ticket-analyst-agent",  # also Opus, handled above
}


def extract_agents(base: Path) -> list[dict]:
    """Extract agent cards from agents/*.xml."""
    cards = []
    agents_dir = base / "agents"
    if not agents_dir.exists():
        return cards

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

        is_opus = name in OPUS_AGENTS
        model = "Opus" if is_opus else "Sonnet"
        subtitle = f"{model} · {role[:55]}{'...' if len(role) > 55 else ''}" if role else model

        card: dict = {
            "id": name,
            "title": name,
            "subtitle": subtitle,
            "detail": goal or role,
            "citations": [{"file": f"agents/{xml_file.name}", "lines": "1-end", "shows": "agent definition"}],
        }
        if is_opus:
            card["badge"] = "Opus"
            card["badge_color"] = "#8e44ad"
            card["accent"] = "#8e44ad"

        cards.append(card)

    return cards


def build_agent_columns(agent_cards: list[dict]) -> list[dict]:
    """Split agents into columns by category."""
    opus_cards = [c for c in agent_cards if c["id"] in OPUS_AGENTS]
    quality_cards = [c for c in agent_cards if c["id"] in QUALITY_AGENTS and c["id"] not in OPUS_AGENTS]
    support_cards = [c for c in agent_cards if c["id"] in SUPPORT_AGENTS and c["id"] not in OPUS_AGENTS]
    other_cards = [
        c for c in agent_cards
        if c["id"] not in OPUS_AGENTS and c["id"] not in QUALITY_AGENTS and c["id"] not in SUPPORT_AGENTS
    ]

    columns = []
    if opus_cards:
        columns.append({"label": "Opus — Strategic", "cards": opus_cards})
    if quality_cards:
        columns.append({"label": "Sonnet — Quality", "cards": quality_cards})
    if support_cards:
        columns.append({"label": "Sonnet — Support", "cards": support_cards})
    if other_cards:
        columns.append({"label": "Sonnet — Other", "cards": other_cards})

    if not columns:
        columns = [{"label": "Agents", "cards": agent_cards}]

    return columns


def count_layer_cards(layer: dict) -> int:
    """Count nodes across any layer type."""
    if "cards" in layer:
        return len(layer["cards"])
    if "columns" in layer:
        return sum(len(col.get("cards", [])) for col in layer["columns"])
    if "exchanges" in layer:
        return len(layer["exchanges"]) * 2
    if "decisions" in layer:
        return sum(1 + len(d.get("outcomes", [])) for d in layer["decisions"])
    return 0


def build_graph(base: Path) -> dict:
    """Build the layered graph for ClaudeBoost self-map."""
    agent_cards = extract_agents(base)

    # Resource counts
    kb_count = len(list((base / "knowledge").glob("*.xml"))) if (base / "knowledge").exists() else 0
    cmd_count = len(list((base / ".claude" / "commands").glob("*.md"))) if (base / ".claude" / "commands").exists() else 0

    hook_count = 0
    setup = base / "scripts" / "setup.ps1"
    if setup.exists():
        content = setup.read_text(encoding="utf-8-sig")
        hook_count = content.count("Install-HookEntry")

    agent_columns = build_agent_columns(agent_cards)

    return {
        "project": "ClaudeBoost",
        "title": "How ClaudeBoost Works",
        "subtitle": f"{len(agent_cards)} agents · {kb_count} knowledge bases · {hook_count} hooks · {cmd_count} commands",
        "generated_at": datetime.now(timezone.utc).isoformat(),

        # Cross-cutting concerns flanking the main layers
        "side_rails": [
            {
                "id": "global-rules",
                "title": "Global Rules",
                "subtitle": "~/.claude/CLAUDE.md",
                "detail": "jQuery ban, parameterized queries, logger.error in every catch block, no secrets in logs or URLs. Applied to every session — not debatable.",
                "side": "left",
                "icon": "🔒",
                "accent": "#e74c3c",
                "responsibilities": [
                    "jQuery ban — use React hooks / vanilla JS",
                    "Parameterized queries only (no SQL concatenation)",
                    "logger.error in every catch block",
                    "No secrets in logs, URLs, or source code",
                    "Localhost-only browser automation",
                ],
            },
            {
                "id": "slash-commands",
                "title": f"{cmd_count} Slash Commands",
                "subtitle": ".claude/commands/*.md",
                "detail": f"Installed globally in ~/.claude/commands/ — available in every project. Includes /boost, /visualize, /spawn-agent, /plan-task, /review, /consult, /auto, and more.",
                "side": "left",
                "icon": "⌨",
                "accent": "#3498db",
                "responsibilities": [
                    "/boost — activate all systems at session start",
                    "/visualize — interactive architecture board",
                    "/spawn-agent — delegate to a specialist",
                    "/plan-task — sweep-then-verify across 7 domains",
                    "/consult and /auto — toggle collaborative mode",
                ],
            },
            {
                "id": "knowledge-rail",
                "title": f"{kb_count} Knowledge Bases",
                "subtitle": "knowledge/*.xml — semantic search via RAG",
                "detail": f"XML files covering every domain agents need. Agents search these at runtime via RAG rather than memorizing them. Indexed automatically on startup.",
                "side": "right",
                "icon": "📚",
                "accent": "#27ae60",
                "responsibilities": [
                    "Security: OWASP top 10, parameterized queries, auth",
                    "Testing: methodology, coverage, TDD",
                    "Architecture: SOLID, DDD, patterns",
                    "Logging: structured, levels, no-PII",
                    "Performance: profiling, caching, bottlenecks",
                    f"...and {kb_count - 5} more domains",
                ],
                "citations": [{"file": "knowledge/", "lines": "dir", "shows": "all knowledge bases"}],
            },
        ],

        "layers": [
            # ── 1. INPUT ──────────────────────────────────────────────────────────
            {
                "id": "user",
                "label": "INPUT",
                "cards": [
                    {
                        "id": "you",
                        "title": "You",
                        "subtitle": "Chat · tickets · slash commands",
                        "detail": "You interact with Claude Code normally. ClaudeBoost changes how Claude thinks behind the scenes — enforcing standards, routing to specialists, and routing architectural decisions through you first.",
                        "icon": "👤",
                        "responsibilities": [
                            "Type requests, paste tickets, or run slash commands",
                            "Approve or adjust architectural proposals (CONSULT mode)",
                            "Add constraints the system can't infer (rate limits, size caps)",
                        ],
                    }
                ],
            },

            # ── 2. TASK CLASSIFICATION ────────────────────────────────────────────
            {
                "id": "classify",
                "label": "TASK CLASSIFICATION",
                "flow_label": "classifies as",
                "decisions": [
                    {
                        "question": {
                            "id": "classify-q",
                            "title": "Simple or Complex?",
                            "subtitle": "Orchestrator decides",
                            "detail": "A one-line fix, typo, or single-file rename is simple. Anything needing planning, multiple agents, workspace tracking, or architectural decisions is complex.",
                        },
                        "outcomes": [
                            {
                                "label": "SIMPLE",
                                "style": "success",
                                "id": "simple-path",
                                "title": "Direct Execution",
                                "subtitle": "No ceremony",
                                "detail": "Just do it. No workspace folder, no agents, no domain sweep. Claude handles it directly and responds immediately.",
                            },
                            {
                                "label": "COMPLEX",
                                "id": "complex-path",
                                "title": "Plan + Delegate",
                                "subtitle": "workspace/ + sweep + agents",
                                "detail": "Creates workspace/[task-id]/, runs sweep-then-verify across 7 domains (testing, docs, security, architecture, performance, review, clarity), then spawns specialist agents — up to 3 in parallel.",
                            },
                        ],
                    }
                ],
            },

            # ── 3. COLLABORATIVE MODE ─────────────────────────────────────────────
            {
                "id": "consult",
                "label": "COLLABORATIVE MODE",
                "flow_label": "routes through",
                "decisions": [
                    {
                        "question": {
                            "id": "consult-q",
                            "title": "CONSULT Mode?",
                            "subtitle": "Default: on — /auto to disable",
                            "detail": "Triggers on: new endpoints, tables, dependencies, modules, auth strategies, APIs, config surfaces, concurrency models. Not on: bugfixes, tests, docs, renames, config value tweaks.",
                            "citations": [{"file": "knowledge/consult-mode.xml", "lines": "1-108", "shows": "full protocol"}],
                        },
                        "outcomes": [
                            {
                                "label": "CONSULT (default)",
                                "style": "success",
                                "id": "consult-yes",
                                "title": "Research + Propose",
                                "subtitle": "architect-agent → 2-3 options → you pick",
                                "detail": "Spawns architect-agent (Opus) with >=2 file:line citations. Presents 2-3 options via AskUserQuestion. You pick and add constraints. Claude implements. Approvals logged to state/session-approvals.json.",
                                "responsibilities": [
                                    "Research project context first (RAG + 2-3 files)",
                                    "Present 2-3 options with clear tradeoffs",
                                    "Let you add constraints (size caps, rate limits)",
                                    "Log your approval for the session",
                                ],
                            },
                            {
                                "label": "AUTO",
                                "id": "consult-no",
                                "title": "Autonomous",
                                "subtitle": "/auto [reason] to enable · /consult to restore",
                                "detail": "Skips consultation gate for architectural decisions. Standards (parameterized queries, logger.error, input validation) still apply automatically. Best for prototyping or trivial work.",
                            },
                        ],
                    }
                ],
            },

            # ── 4. SPECIALIST AGENTS ──────────────────────────────────────────────
            {
                "id": "agents",
                "label": "SPECIALIST AGENTS",
                "flow_label": "delegates work to",
                "columns": agent_columns,
            },

            # ── 5. KNOWLEDGE RETRIEVAL ────────────────────────────────────────────
            {
                "id": "rag-layer",
                "label": "KNOWLEDGE RETRIEVAL",
                "flow_label": "each agent queries",
                "exchanges": [
                    {
                        "request_label": "rag_context(agent, task)",
                        "response_label": "tiered docs — guardrails + standards",
                        "left": {
                            "id": "agent-query",
                            "title": "Agent (First Action)",
                            "subtitle": "Must call rag_context before anything else",
                            "detail": "Every spawned agent calls rag_context as its very first action. This loads the 4-tier context: guardrails (tier 0), declared agent knowledge (tier 1-2), related standards (tier 3), project codebase (tier 4). The PreToolUse hook reminds if the spawn prompt omits it.",
                            "responsibilities": [
                                "Tier 0: hard guardrails (always applied)",
                                "Tier 1-2: declared knowledge for this agent",
                                "Tier 3: related standards from other domains",
                                "Tier 4: relevant chunks from project source code",
                            ],
                        },
                        "right": {
                            "id": "rag-server",
                            "title": "RAG MCP Server",
                            "subtitle": "Embeddings · auto-indexed · 2s updates",
                            "detail": "MCP server that indexes agents + knowledge bases using sentence-transformers. Starts automatically with Claude Code. Re-indexes changed files within 2 seconds via file watcher. Returns semantically ranked chunks.",
                            "responsibilities": [
                                "Index all agents and knowledge on startup",
                                "Watch for file changes, re-index within 2s",
                                "Return ranked chunks for natural language queries",
                                "Per-project index for source code (rag_index_project)",
                            ],
                            "citations": [{"file": "mcp-rag-server/", "lines": "dir", "shows": "MCP server source"}],
                        },
                    }
                ],
            },

            # ── 6. SAFETY & ENFORCEMENT ───────────────────────────────────────────
            {
                "id": "enforcement",
                "label": "SAFETY & ENFORCEMENT",
                "flow_label": "governed by",
                "cards": [
                    {
                        "id": "hooks",
                        "title": f"{hook_count} Safety Hooks",
                        "subtitle": "Fire automatically at key moments",
                        "detail": "Claude Code hooks that inject rules at key moments. Hooks are a mix of prompt-type (LLM reminders) and command-type scripts. bash-guard.py blocks cd+&& and backslash-space patterns; all other command-type hooks nudge without blocking.",
                        "badge": "Hooks",
                        "badge_color": "#e67e22",
                        "responsibilities": [
                            "SessionStart: load global rules into every session",
                            "PreToolUse: inject verify gate into agent spawns",
                            "PostToolUse: nudge evaluator-agent for unverified findings",
                            "PreCompact: re-inject rules after context compression",
                            "UserPromptSubmit: stop TTS playback on new input",
                            "Stop: speak response via TTS",
                        ],
                        "citations": [{"file": "scripts/setup.ps1", "lines": "146-415", "shows": "hook installation"}],
                    },
                    {
                        "id": "verify",
                        "title": "Verify Gate",
                        "subtitle": "Every finding must cite file:line",
                        "detail": "Anti-hallucination protocol: every finding an agent reports must be proven from actual code with a specific file and line number as evidence. If it can't point to real code, the finding is dropped. 'Nothing found' is always a valid outcome.",
                        "badge": "Anti-Hallucination",
                        "badge_color": "#c0392b",
                        "responsibilities": [
                            "Every finding cites specific file:line",
                            "If no proof: drop the finding (not report it)",
                            "'Nothing found' is always a valid outcome",
                            "Evaluator-agent verifies flagged findings",
                        ],
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

    total = sum(count_layer_cards(layer) for layer in graph["layers"])
    rail_count = len(graph.get("side_rails", []))
    print(f"Extracted {total} nodes across {len(graph['layers'])} layers + {rail_count} side rails -> {output}")


if __name__ == "__main__":
    main()
