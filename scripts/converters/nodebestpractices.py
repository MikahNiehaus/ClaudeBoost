"""
Convert nodebestpractices markdown files into ClaudeBoost RAG knowledge XML files.

Reads from: references/nodebestpractices/sections/
Writes to:  knowledge/patterns-{section}.xml

Each section directory becomes one XML knowledge file. Practices are extracted
with their title, one-paragraph explainer, and code examples (condensed).
"""

import re
import os
from pathlib import Path
from xml.sax.saxutils import escape

# Resolve paths relative to ClaudeBoost root
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent.parent
SECTIONS_DIR = ROOT / "references" / "nodebestpractices" / "sections"
OUTPUT_DIR = ROOT / "knowledge"

# Map section dirs to readable names and triggers for RAG
SECTION_META = {
    "errorhandling": {
        "name": "Error Handling Best Practices",
        "triggers": "error handling, exceptions, error recovery, centralized errors, async errors, logging errors, monitoring",
        "overview": "Production-grade error handling patterns from Node.js best practices. Applicable to any backend: centralized handlers, async error flows, operational vs programmer errors.",
    },
    "security": {
        "name": "Security Best Practices",
        "triggers": "security, authentication, authorization, XSS, CSRF, injection, secrets, JWT, rate limiting, dependencies",
        "overview": "Security hardening patterns from Node.js best practices. Covers auth, input validation, dependency safety, secret management, and common vulnerability prevention.",
    },
    "production": {
        "name": "Production Readiness Practices",
        "triggers": "production, deployment, monitoring, logging, APM, process management, graceful shutdown, memory leaks",
        "overview": "Production readiness patterns: monitoring, graceful shutdown, process management, memory safety, and operational excellence.",
    },
    "docker": {
        "name": "Docker & Container Practices",
        "triggers": "docker, container, dockerfile, multi-stage build, image security, container orchestration",
        "overview": "Docker and containerization best practices: secure images, multi-stage builds, graceful shutdown, caching, and production-ready container patterns.",
    },
    "testingandquality": {
        "name": "Testing & Quality Practices",
        "triggers": "testing, TDD, test coverage, integration tests, mocking, test structure, quality assurance",
        "overview": "Testing and code quality patterns: test structure, integration testing, mutation testing, and quality gates.",
    },
    "projectstructre": {
        "name": "Project Structure Practices",
        "triggers": "project structure, folder structure, layering, modularity, configuration, dependencies",
        "overview": "Project organization patterns: folder structure, layered architecture, configuration management, and dependency organization.",
    },
    "performance": {
        "name": "Performance Practices",
        "triggers": "performance, event loop, blocking, optimization, throughput, latency",
        "overview": "Performance optimization patterns: event loop management, non-blocking patterns, and throughput optimization.",
    },
    "codestylepractices": {
        "name": "Code Style Practices",
        "triggers": "code style, linting, formatting, eslint, prettier, code consistency",
        "overview": "Code style and formatting automation with ESLint and Prettier.",
    },
}


def extract_practice(filepath: Path) -> dict | None:
    """Extract structured content from a practice markdown file."""
    text = filepath.read_text(encoding="utf-8", errors="replace")

    # Extract title (first H1)
    title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else filepath.stem.replace("-", " ").title()

    # Extract "One Paragraph Explainer" section
    explainer = ""
    exp_match = re.search(
        r"###?\s+One\s+Paragraph\s+Explainer\s*\n+(.*?)(?=\n###?\s|\n##\s|\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if exp_match:
        explainer = exp_match.group(1).strip()
        # Remove markdown links but keep text: [text](url) -> text
        explainer = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", explainer)
        # Remove HTML tags
        explainer = re.sub(r"<[^>]+>", "", explainer)
        # Collapse whitespace
        explainer = re.sub(r"\n{3,}", "\n\n", explainer).strip()

    if not explainer:
        return None  # Skip files without a real explainer

    # Extract code examples (first JS/TS block only, keep it short)
    code_example = ""
    # Look inside <details> blocks or bare code blocks
    code_blocks = re.findall(
        r"```(?:javascript|typescript|js|ts)\n(.*?)```",
        text,
        re.DOTALL,
    )
    if code_blocks:
        # Take first meaningful block, truncate if huge
        block = code_blocks[0].strip()
        lines = block.split("\n")
        if len(lines) > 30:
            lines = lines[:30] + ["// ... (truncated)"]
        code_example = "\n".join(lines)

    # Extract "Otherwise" / "what could happen" section (the anti-pattern)
    otherwise = ""
    ow_match = re.search(
        r"###?\s+(?:Otherwise|What could happen)\s*\n+(.*?)(?=\n###?\s|\n##\s|\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if ow_match:
        otherwise = ow_match.group(1).strip()
        otherwise = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", otherwise)
        otherwise = re.sub(r"<[^>]+>", "", otherwise)
        otherwise = re.sub(r"\n{3,}", "\n\n", otherwise).strip()
        # Keep it concise
        if len(otherwise) > 500:
            otherwise = otherwise[:500].rsplit(" ", 1)[0] + "..."

    return {
        "title": title,
        "explainer": explainer,
        "code_example": code_example,
        "otherwise": otherwise,
        "source_file": str(filepath.relative_to(ROOT)),
    }


def build_xml(section: str, practices: list[dict]) -> str:
    """Build XML knowledge file for a section."""
    meta = SECTION_META.get(section, {
        "name": section.replace("-", " ").title() + " Practices",
        "triggers": section.replace("-", ", "),
        "overview": f"Best practices for {section}.",
    })

    lines = [
        f'<knowledge-base name="patterns-{section}" version="1.0">',
        f'<triggers>{escape(meta["triggers"])}</triggers>',
        f'<overview>{escape(meta["overview"])}</overview>',
        f'<source license="CC-BY-SA-4.0">goldbergyoni/nodebestpractices</source>',
        "",
    ]

    for i, p in enumerate(practices, 1):
        lines.append(f'<practice id="{section}-{i:02d}">')
        lines.append(f"  <title>{escape(p['title'])}</title>")
        lines.append(f"  <explainer>{escape(p['explainer'])}</explainer>")

        if p["otherwise"]:
            lines.append(f"  <anti-pattern>{escape(p['otherwise'])}</anti-pattern>")

        if p["code_example"]:
            lines.append("  <example><![CDATA[")
            lines.append(p["code_example"])
            lines.append("  ]]></example>")

        lines.append("</practice>")
        lines.append("")

    lines.append("</knowledge-base>")
    return "\n".join(lines)


def main():
    if not SECTIONS_DIR.exists():
        print(f"ERROR: {SECTIONS_DIR} not found")
        return

    total_practices = 0
    total_files = 0

    for section_dir in sorted(SECTIONS_DIR.iterdir()):
        if not section_dir.is_dir():
            continue
        section = section_dir.name

        # Skip non-content dirs
        if section in ("drafts", "examples"):
            continue

        # Find English-only markdown files (no second dot = no language suffix)
        md_files = sorted([
            f for f in section_dir.glob("*.md")
            if not f.name.startswith("template")
            and f.name.count(".") == 1  # only "name.md", not "name.lang.md"
        ])

        if not md_files:
            continue

        practices = []
        for md_file in md_files:
            practice = extract_practice(md_file)
            if practice:
                practices.append(practice)

        if not practices:
            print(f"  SKIP {section}: no extractable practices")
            continue

        xml = build_xml(section, practices)
        out_path = OUTPUT_DIR / f"patterns-{section}.xml"
        out_path.write_text(xml, encoding="utf-8")

        total_practices += len(practices)
        total_files += 1
        print(f"  {out_path.name}: {len(practices)} practices from {len(md_files)} files")

    print(f"\nDone: {total_practices} practices across {total_files} knowledge files")


if __name__ == "__main__":
    main()
