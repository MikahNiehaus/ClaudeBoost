"""
Convert system-design-primer README.md into ClaudeBoost RAG knowledge XML files.

Reads from: references/system-design-primer/README.md
Writes to:  knowledge/patterns-system-design.xml

The README is one giant file. We split by ## headers, keep only the actual
design topic sections (Performance vs scalability through Security), and
extract the explanatory content with advantages/disadvantages.
"""

import re
from pathlib import Path
from xml.sax.saxutils import escape

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent.parent
README = ROOT / "references" / "system-design-primer" / "README.md"
OUTPUT_DIR = ROOT / "knowledge"

# Only extract these sections (the actual design knowledge)
# Everything before "Performance vs scalability" is intro/meta
# Everything after "Security" is appendix/credits
SKIP_SECTIONS = {
    "Motivation", "Anki flashcards", "Contributing",
    "Index of system design topics", "Study guide",
    "How to approach a system design interview question",
    "System design interview questions with solutions",
    "Object-oriented design interview questions with solutions",
    "System design topics: start here",
    "Under development", "Credits", "Contact info", "License",
    "Appendix",
}

# Group sections into output topics for better RAG chunking
TOPIC_GROUPS = {
    "fundamentals": {
        "sections": [
            "Performance vs scalability",
            "Latency vs throughput",
            "Availability vs consistency",
            "Consistency patterns",
            "Availability patterns",
        ],
        "triggers": "scalability, latency, throughput, availability, consistency, CAP theorem, performance",
        "overview": "Core system design fundamentals: scalability, consistency, availability trade-offs, and foundational patterns.",
    },
    "networking": {
        "sections": [
            "Domain name system",
            "Content delivery network",
            "Load balancer",
            "Reverse proxy (web server)",
        ],
        "triggers": "DNS, CDN, load balancer, reverse proxy, networking, HTTP, routing, caching",
        "overview": "Network infrastructure patterns: DNS, CDN, load balancing strategies, and reverse proxy architectures.",
    },
    "application": {
        "sections": [
            "Application layer",
            "Database",
            "Cache",
        ],
        "triggers": "microservices, database, SQL, NoSQL, sharding, replication, cache, Redis, Memcached, denormalization",
        "overview": "Application and data layer patterns: service architectures, database design (SQL/NoSQL/sharding/replication), and caching strategies.",
    },
    "communication": {
        "sections": [
            "Asynchronism",
            "Communication",
            "Security",
        ],
        "triggers": "message queue, async, REST, RPC, GraphQL, TCP, UDP, HTTP, websocket, security",
        "overview": "Communication patterns: async processing, message queues, protocol selection (REST/RPC/GraphQL), and security fundamentals.",
    },
}


def split_sections(text: str) -> dict[str, str]:
    """Split README into sections by ## headers. Returns {title: content}."""
    sections = {}
    current_title = None
    current_lines = []

    for line in text.split("\n"):
        if line.startswith("## "):
            if current_title:
                sections[current_title] = "\n".join(current_lines).strip()
            current_title = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_title:
        sections[current_title] = "\n".join(current_lines).strip()

    return sections


def clean_content(text: str) -> str:
    """Clean markdown content for XML embedding."""
    # Remove image tags
    text = re.sub(r"<p[^>]*>.*?</p>", "", text, flags=re.DOTALL)
    # Remove HTML tags but keep content
    text = re.sub(r"</?(?:sup|sub|br|i|b|a|strong|em)[^>]*>", "", text)
    # Remove markdown links, keep text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Remove reference-style footnotes
    text = re.sub(r"\[\d+\]", "", text)
    # Collapse excessive whitespace
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


def extract_subsections(content: str) -> dict:
    """Extract structured subsections (### headers) from a section."""
    result = {
        "intro": "",
        "subsections": [],
        "disadvantages": "",
        "advantages": "",
    }

    parts = re.split(r"\n(?=### )", content)
    for part in parts:
        header_match = re.match(r"### (.+)\n(.*)", part, re.DOTALL)
        if not header_match:
            result["intro"] += part
            continue

        header = header_match.group(1).strip()
        body = header_match.group(2).strip()

        # Skip "Source(s) and further reading" sections
        if "source" in header.lower() and "reading" in header.lower():
            continue

        lower = header.lower()
        if "disadvantage" in lower:
            result["disadvantages"] = clean_content(body)
        elif "advantage" in lower:
            result["advantages"] = clean_content(body)
        else:
            result["subsections"].append({
                "title": header,
                "content": clean_content(body),
            })

    result["intro"] = clean_content(result["intro"])
    return result


def build_topic_xml(topic_key: str, topic_meta: dict, all_sections: dict) -> str:
    """Build XML for one topic group."""
    lines = [
        f'<knowledge-base name="patterns-sysdesign-{topic_key}" version="1.0">',
        f'<triggers>{escape(topic_meta["triggers"])}</triggers>',
        f'<overview>{escape(topic_meta["overview"])}</overview>',
        '<source license="CC-BY-4.0">donnemartin/system-design-primer</source>',
        "",
    ]

    idx = 0
    for section_title in topic_meta["sections"]:
        content = all_sections.get(section_title, "")
        if not content:
            continue

        idx += 1
        slug = re.sub(r"[^a-z0-9]+", "-", section_title.lower()).strip("-")
        parsed = extract_subsections(content)

        lines.append(f'<topic id="{topic_key}-{idx:02d}" slug="{slug}">')
        lines.append(f"  <title>{escape(section_title)}</title>")

        if parsed["intro"]:
            # Truncate very long intros
            intro = parsed["intro"]
            if len(intro) > 2000:
                intro = intro[:2000].rsplit("\n", 1)[0] + "\n..."
            lines.append(f"  <description>{escape(intro)}</description>")

        for sub in parsed["subsections"]:
            sub_content = sub["content"]
            if len(sub_content) > 1000:
                sub_content = sub_content[:1000].rsplit("\n", 1)[0] + "\n..."
            lines.append(f'  <subsection title="{escape(sub["title"])}">')
            lines.append(f"    {escape(sub_content)}")
            lines.append("  </subsection>")

        if parsed["advantages"]:
            lines.append(f"  <advantages>{escape(parsed['advantages'])}</advantages>")

        if parsed["disadvantages"]:
            lines.append(f"  <disadvantages>{escape(parsed['disadvantages'])}</disadvantages>")

        lines.append("</topic>")
        lines.append("")

    lines.append("</knowledge-base>")
    return "\n".join(lines)


def main():
    if not README.exists():
        print(f"ERROR: {README} not found")
        return

    text = README.read_text(encoding="utf-8", errors="replace")
    all_sections = split_sections(text)

    print(f"Found {len(all_sections)} sections in README")
    kept = {k: v for k, v in all_sections.items() if k not in SKIP_SECTIONS}
    print(f"Keeping {len(kept)} design topic sections")

    total_topics = 0
    for topic_key, topic_meta in TOPIC_GROUPS.items():
        xml = build_topic_xml(topic_key, topic_meta, all_sections)
        out_path = OUTPUT_DIR / f"patterns-sysdesign-{topic_key}.xml"
        out_path.write_text(xml, encoding="utf-8")

        count = sum(1 for t in topic_meta["sections"] if t in all_sections)
        total_topics += count
        print(f"  {out_path.name}: {count} topics")

    print(f"\nDone: {total_topics} topics across {len(TOPIC_GROUPS)} knowledge files")


if __name__ == "__main__":
    main()
