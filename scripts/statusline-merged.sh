#!/bin/sh
# ClaudeBoost RAG status + Claude subscription 5h/7d usage, one line, no throttle.
input="$(cat)"

rag_out=""
for py in "$CLAUDEBOOST_PYTHON" python python3 py; do
  [ -z "$py" ] && continue
  rag_out="$(printf '%s' "$input" | "$py" "$CLAUDEBOOST_HOME/scripts/rag-statusline.py" 2>/dev/null)"
  [ -n "$rag_out" ] && break
done

usage_out=""
if command -v node >/dev/null 2>&1; then
  usage_out="$(printf '%s' "$input" | node "$CLAUDEBOOST_HOME/scripts/claude-usage-line.js" 2>/dev/null)"
fi

if [ -n "$usage_out" ]; then
  printf '%s %s %s' "$rag_out" "$(printf '\033[2m|\033[0m')" "$usage_out"
else
  printf '%s' "$rag_out"
fi
