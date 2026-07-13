#!/usr/bin/env python
"""PLACEHOLDER. Does nothing. Exits 0.

This file exists so a branch switch cannot brick Claude. Hook commands live in
the global ~/.claude/settings.json and survive a checkout, but the scripts they
point at live in this repo. A missing script makes python exit 2, and a
PreToolUse hook exiting 2 blocks the tool call outright. A file that exits 0
turns that into a no op.

WHAT THIS ONE USED TO BE, AND WHY IT IS NOT COMING BACK

_crawl_runner.py drove the web crawler that automatically wrote search results
into the permanent knowledge base.

It was removed because it polluted that knowledge base for real, not
hypothetically. Casual conversational messages were triggering the web search
fallback, and whatever came back got indexed under an auto generated topic name
as though it were a real technical source. At one point a message that used the
word "injection" in the RAG sense caused literal medical content about injections
to be indexed.

The knowledge base it fed no longer exists either. Deleted deliberately, on the
CleanRag branch. Do not restore it.
"""

import sys

sys.exit(0)
