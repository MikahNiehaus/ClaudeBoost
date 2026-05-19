import sys
sys.path.insert(0, 'C:/Users/grayw/OneDrive/prj/ClaudeBoost/mcp-rag-server/src')

from rag_server.indexing.markdown_chunker import estimate_tokens

# Read the whole guardrails section
with open('C:/Users/grayw/OneDrive/prj/ClaudeBoost/knowledge/lang-typescript.xml', 'r') as f:
    content = f.read()

# Extract guardrails section (lines 13-142)
lines = content.split('\n')
guardrails_section = '\n'.join(lines[12:142])  # 0-indexed, so 13-142 is 12-141
print(f"Guardrails section token count: {estimate_tokens(guardrails_section)}")

# Also check individual guardrails
import re
guardrail_pattern = r'<guardrail id="([^"]+)".*?</guardrail>'
matches = re.findall(guardrail_pattern, content, re.DOTALL)
print(f"\nFound {len(matches)} guardrails")

# Extract each one and count tokens
for match in re.finditer(guardrail_pattern, content, re.DOTALL):
    g_id = match.group(1)
    g_content = match.group(0)
    g_tokens = estimate_tokens(g_content)
    print(f"  {g_id}: {g_tokens} tokens")
