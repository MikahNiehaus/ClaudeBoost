"""
Convert java-design-patterns READMEs into ClaudeBoost RAG knowledge XML files.

Reads from: references/java-design-patterns/*/README.md
Writes to:  knowledge/patterns-design-{category}.xml

Each pattern directory has a README.md with YAML frontmatter (title, category,
tags) and structured sections (Intent, Detailed Explanation, etc.).
We extract the language-agnostic design knowledge, skip Java-specific code.
"""

import re
import yaml
from pathlib import Path
from xml.sax.saxutils import escape

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent.parent
PATTERNS_DIR = ROOT / "references" / "java-design-patterns"
OUTPUT_DIR = ROOT / "knowledge"

# Group categories into output files
CATEGORY_GROUPS = {
    "behavioral": {
        "categories": ["Behavioral"],
        "triggers": "behavioral patterns, strategy, observer, command, state, visitor, mediator, chain of responsibility, template method",
        "overview": "Behavioral design patterns: algorithms, responsibilities between objects, and communication patterns. From java-design-patterns, adapted for any language.",
    },
    "structural": {
        "categories": ["Structural"],
        "triggers": "structural patterns, adapter, bridge, composite, decorator, facade, flyweight, proxy",
        "overview": "Structural design patterns: composition of classes/objects into larger structures while keeping flexibility and efficiency.",
    },
    "creational": {
        "categories": ["Creational"],
        "triggers": "creational patterns, factory, builder, singleton, prototype, abstract factory, object creation",
        "overview": "Creational design patterns: object creation mechanisms that increase flexibility and reuse.",
    },
    "architectural": {
        "categories": ["Architectural"],
        "triggers": "architectural patterns, MVC, CQRS, event sourcing, hexagonal, layered, microservices, clean architecture",
        "overview": "Architectural design patterns: high-level structural decisions for applications and systems.",
    },
    "concurrency": {
        "categories": ["Concurrency"],
        "triggers": "concurrency patterns, thread safety, async, parallel, mutex, producer-consumer, thread pool",
        "overview": "Concurrency design patterns: managing parallel execution, thread safety, and asynchronous operations.",
    },
    "integration": {
        "categories": ["Data access", "Integration", "Messaging", "Service Discovery"],
        "triggers": "data access, repository, DAO, integration, messaging, service discovery, API gateway, event-driven",
        "overview": "Data access, integration, and messaging patterns: database access, service communication, and event-driven architectures.",
    },
    "resilience": {
        "categories": ["Resilience", "Resource management", "Performance optimization"],
        "triggers": "resilience, circuit breaker, retry, bulkhead, rate limiting, resource management, caching, pooling, performance",
        "overview": "Resilience and performance patterns: fault tolerance, resource management, caching, and optimization strategies.",
    },
    "other": {
        "categories": ["Functional", "Testing"],
        "triggers": "functional patterns, monad, currying, testing patterns, arrange-act-assert, page object",
        "overview": "Functional programming and testing patterns: immutability, composition, and test organization.",
    },
}


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Extract YAML frontmatter and remaining content."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
    if not match:
        return {}, text

    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        meta = {}

    return meta or {}, match.group(2)


def extract_pattern(readme_path: Path) -> dict | None:
    """Extract pattern knowledge from a README.md."""
    text = readme_path.read_text(encoding="utf-8", errors="replace")
    meta, body = parse_frontmatter(text)

    if not meta.get("category"):
        return None

    # Only English
    if meta.get("language", "en") != "en":
        return None

    pattern_name = meta.get("shortTitle", readme_path.parent.name.replace("-", " ").title())
    category = meta.get("category", "")
    tags = meta.get("tag", [])
    if isinstance(tags, str):
        tags = [tags]

    # Extract key sections
    sections = {}
    current_header = None
    current_lines = []

    for line in body.split("\n"):
        h2_match = re.match(r"^## (.+)", line)
        if h2_match:
            if current_header:
                sections[current_header] = "\n".join(current_lines).strip()
            current_header = h2_match.group(1).strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_header:
        sections[current_header] = "\n".join(current_lines).strip()

    # Extract intent (most important)
    intent = ""
    for key in sections:
        if "intent" in key.lower():
            intent = sections[key]
            break

    if not intent:
        return None

    # Clean markdown
    def clean(t):
        t = re.sub(r"<p[^>]*>.*?</p>", "", t, flags=re.DOTALL)
        t = re.sub(r"!\[.*?\]\(.*?\)", "", t)  # Remove images
        t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)  # Links -> text
        t = re.sub(r"<[^>]+>", "", t)
        t = re.sub(r"\n{3,}", "\n\n", t)
        return t.strip()

    intent = clean(intent)

    # Extract "also known as"
    also_known = ""
    for key in sections:
        if "also known" in key.lower():
            also_known = clean(sections[key])
            break

    # Extract detailed explanation (real-world example + "in plain words")
    explanation = ""
    for key in sections:
        if "detailed explanation" in key.lower():
            raw = sections[key]
            # Get "In plain words" and "Real-world example" but skip code blocks
            plain_match = re.search(
                r"In plain words\s*>\s*(.+?)(?=\n\n|\nWikipedia|\nClass|\nFlowchart)",
                raw, re.DOTALL
            )
            if plain_match:
                explanation = clean(plain_match.group(1))
            elif len(raw) < 1500:
                explanation = clean(raw)
            else:
                # Take first 1000 chars
                explanation = clean(raw[:1000]).rsplit("\n", 1)[0] + "..."
            break

    # Extract applicability
    applicability = ""
    for key in sections:
        if "applicability" in key.lower() or "when to use" in key.lower():
            raw = clean(sections[key])
            if len(raw) > 800:
                raw = raw[:800].rsplit("\n", 1)[0] + "..."
            applicability = raw
            break

    # Extract consequences/trade-offs
    tradeoffs = ""
    for key in sections:
        if "trade" in key.lower() or "consequence" in key.lower() or "benefit" in key.lower():
            raw = clean(sections[key])
            if len(raw) > 800:
                raw = raw[:800].rsplit("\n", 1)[0] + "..."
            tradeoffs = raw
            break

    return {
        "name": pattern_name,
        "category": category,
        "tags": tags,
        "intent": intent,
        "also_known_as": also_known,
        "explanation": explanation,
        "applicability": applicability,
        "tradeoffs": tradeoffs,
        "slug": readme_path.parent.name,
    }


def build_group_xml(group_key: str, group_meta: dict, patterns: list[dict]) -> str:
    """Build XML for one pattern group."""
    lines = [
        f'<knowledge-base name="patterns-design-{group_key}" version="1.0">',
        f'<triggers>{escape(group_meta["triggers"])}</triggers>',
        f'<overview>{escape(group_meta["overview"])}</overview>',
        '<source license="MIT">iluwatar/java-design-patterns (language-agnostic extracts)</source>',
        "",
    ]

    for i, p in enumerate(patterns, 1):
        tag_str = ", ".join(p["tags"]) if p["tags"] else ""
        lines.append(f'<pattern id="{group_key}-{i:02d}" slug="{p["slug"]}">')
        lines.append(f"  <name>{escape(p['name'])}</name>")
        lines.append(f"  <category>{escape(p['category'])}</category>")
        if tag_str:
            lines.append(f"  <tags>{escape(tag_str)}</tags>")
        if p["also_known_as"]:
            lines.append(f"  <also-known-as>{escape(p['also_known_as'])}</also-known-as>")
        lines.append(f"  <intent>{escape(p['intent'])}</intent>")

        if p["explanation"]:
            lines.append(f"  <explanation>{escape(p['explanation'])}</explanation>")

        if p["applicability"]:
            lines.append(f"  <applicability>{escape(p['applicability'])}</applicability>")

        if p["tradeoffs"]:
            lines.append(f"  <tradeoffs>{escape(p['tradeoffs'])}</tradeoffs>")

        lines.append("</pattern>")
        lines.append("")

    lines.append("</knowledge-base>")
    return "\n".join(lines)


def main():
    if not PATTERNS_DIR.exists():
        print(f"ERROR: {PATTERNS_DIR} not found")
        return

    # Build reverse map: category -> group key
    cat_to_group = {}
    for group_key, meta in CATEGORY_GROUPS.items():
        for cat in meta["categories"]:
            cat_to_group[cat] = group_key

    # Extract all patterns
    all_patterns: dict[str, list[dict]] = {k: [] for k in CATEGORY_GROUPS}
    skipped = 0

    for pattern_dir in sorted(PATTERNS_DIR.iterdir()):
        readme = pattern_dir / "README.md"
        if not readme.exists():
            continue

        pattern = extract_pattern(readme)
        if not pattern:
            skipped += 1
            continue

        group = cat_to_group.get(pattern["category"])
        if not group:
            skipped += 1
            continue

        all_patterns[group].append(pattern)

    # Write XML files
    total = 0
    for group_key, meta in CATEGORY_GROUPS.items():
        patterns = all_patterns[group_key]
        if not patterns:
            print(f"  SKIP {group_key}: no patterns")
            continue

        xml = build_group_xml(group_key, meta, patterns)
        out_path = OUTPUT_DIR / f"patterns-design-{group_key}.xml"
        out_path.write_text(xml, encoding="utf-8")

        total += len(patterns)
        print(f"  {out_path.name}: {len(patterns)} patterns")

    print(f"\nDone: {total} patterns across {len(CATEGORY_GROUPS)} knowledge files (skipped {skipped})")


if __name__ == "__main__":
    main()
