import re
from pathlib import Path

BAD_COP = Path(__file__).resolve().parents[1] / 'clean-rag' / 'portable' / 'agents' / 'bad-cop.md'
text = BAD_COP.read_text(encoding='utf-8')

# Parse frontmatter tools
in_fm = False
tools = set()
for line in text.splitlines():
    if line.strip() == '---':
        if not in_fm:
            in_fm = True
            continue
        break
    if in_fm and line.startswith('tools:'):
        tools = {t.strip() for t in line[len('tools:'):].split(',')}

# Find prose mcp refs
parts = text.split('---', 2)
prose = parts[2] if len(parts) >= 3 else text
prose_refs = set(re.findall(r'mcp__\w+', prose))

print('=== FRONTMATTER TOOLS (mcp__ only, sample) ===')
mcp_tools = {t for t in tools if 'mcp__' in t}
print(sorted(mcp_tools)[:15])

print()
print('=== PROSE MCP REFS ===')
print(sorted(prose_refs))

print()
print('=== UNLISTED (prose - frontmatter) ===')
unlisted = prose_refs - tools
print(sorted(unlisted))

print()
print('=== CONTEXT FOR EACH UNLISTED REF ===')
for ref in sorted(unlisted):
    for i, line in enumerate(text.splitlines()):
        if ref in line:
            print(f"  Line {i+1}: {line.strip()[:100]}")
