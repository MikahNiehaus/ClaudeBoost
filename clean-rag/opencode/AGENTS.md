# clean-rag rules for OpenCode

OpenCode reads this file. It is the soft enforcement layer that sits next to the
research gate plugin. The plugin blocks code edits mechanically. This file tells
you the workflow the plugin is trying to hold you to, so you follow it on purpose
rather than only when a block stops you.

## Before you write code, research it

Call the clean-rag `rag_search` tool with a query about what you are changing. It
searches the indexed project and its import graph, so you find what already exists
and what your change touches.

If `rag_search` returns zero results, the project is not indexed yet. That is not
"nothing to find". Call `web_search_fallback` and research from the web instead.
Either way, do the research before the edit. A zero result search does not open
the gate, and it should not stop you either.

For anything beyond a trivial change, spawn `research-agent`. It covers depth and
breadth, checks whether the thing already exists, and ends with a `COVERS:` line
naming the files it researched. The gate reads that line and only then lets you
edit those files.

## Research the whole problem, not the happy path

One search is not research. Cover the quality lenses every time:

- Correctness and edge cases: what inputs break this? Empty, zero, huge, null.
- Security: injection, untrusted input, secrets, auth. See the standards below.
- Test quality: how will you prove this works?

If you only asked "how do I build X" and never "how does X break", you have not
finished researching.

## After you write non trivial code, test it for real

Write a test and run it. Fix from the actual failure output, not from reading your
own code and deciding it looks right. Do not self review in place of running
something. The reminder the gate appends to a block ("you wrote X and have not run
a test on it") is there because OpenCode cannot nudge you passively. Beat it to the
punch: run the test yourself.

Trivial one liners do not need a test. Anything with a branch, a loop, a parser, or
a money or security path does.

## Standards that are never optional

These apply automatically. They are not up for debate and not something research
decides:

- Parameterized queries. Never build SQL by string concatenation.
- `logger.error` (or the language equivalent) in every catch or error block.
- No secrets in logs, URLs, or source.
- Validate input at the boundary.
- Auth and authorization checks on every endpoint.
