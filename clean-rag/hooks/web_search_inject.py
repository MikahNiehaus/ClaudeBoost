#!/usr/bin/env python3
"""Web search fallback injection hook for preprompt context.

Fires on agent spawn (PreToolUse on Task). If prior search returned
fallback_triggered=true, this injects web_search_results as markdown
into the agent's system prompt so it sees the results as input context.

Exit codes:
  0 = always
"""

import json
import os
import sys
from pathlib import Path


def _get_last_search_state() -> dict:
    """Read the last search fallback state from environment or temp file."""
    env_state = os.environ.get("CLEAN_RAG_LAST_SEARCH")
    if env_state:
        try:
            return json.loads(env_state)
        except json.JSONDecodeError:
            pass
    return {}


def _format_web_results(results: list[dict]) -> str:
    """Format web search results as markdown section."""
    if not results:
        return ""

    markdown = "## Fallback Web Search Results\n\n"
    markdown += "(These results were retrieved because clean-rag KB had low matches. "
    markdown += "They are supplementary—background indexing is underway.)\n\n"

    for i, result in enumerate(results, 1):
        title = result.get("title", "Result")
        url = result.get("url", "")
        snippet = result.get("snippet", "")

        markdown += f"### {i}. {title}\n"
        if url:
            markdown += f"**Source:** {url}\n\n"
        if snippet:
            markdown += f"{snippet}\n\n"

    return markdown


def main():
    """Inject web search results if fallback was triggered."""
    search_state = _get_last_search_state()

    if search_state.get("fallback_triggered") and search_state.get("web_search_results"):
        web_results = search_state["web_search_results"]
        injected = _format_web_results(web_results)

        if injected:
            print(injected, file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
