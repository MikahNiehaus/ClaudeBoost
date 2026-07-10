---
argument-hint: <anything — a topic, a question, or nothing to infer from the conversation>
description: "Spawn a background agent to grab, convert, and index real documentation for any topic"
allowed-tools: Agent, Bash, Glob, Grep, Read
---

# /research-rag — Background Research Agent

Arguments: **$ARGUMENTS**

Spawns a single background agent that grabs real documentation for any topic, converts it to markdown, saves it to the clean-rag knowledge tree, and indexes it. The agent never reads content it fetches. It evaluates source quality by domain/URL signals only.

Works for code topics (FastAPI, React) and anything else (project management, data science, design, business).

**Two usage modes:**
- **Reactive** (after Fast Path): Main agent hit proof gate, did Fast Path to unblock, then calls this in background to fill out the full topic for future queries.
- **Proactive** (standalone): Build up a topic before anyone needs it.

---

## Step 1: Figure Out The Topic

`$ARGUMENTS` is free text, not a rigid `<slug> [category]` format. Read it like a request, not a
command line. Do NOT require the user to already know the kebab-case slug or category — figure
those out yourself.

**1a — Understand intent from `$ARGUMENTS` plus the conversation so far.**

- If `$ARGUMENTS` names a clear subject ("kubernetes ingress", "how litellm routing works",
  "look up FastAPI background tasks"), that subject is the topic — regardless of phrasing.
- If `$ARGUMENTS` is vague or empty ("do more on that", "research it", "go deeper", or nothing at
  all), look back at the current conversation for what "it"/"that" refers to: the most recently
  discussed library, framework, error, or subject. Use that.
- If `$ARGUMENTS` contains explicit flags (`--sources`, `--supplement`) anywhere in the text,
  honor them regardless of position — don't require them to trail a fixed positional prefix.
- If after checking both `$ARGUMENTS` and recent conversation there is still no identifiable
  subject, THEN print usage and stop. This should be rare — only truly cold, contextless
  invocations with nothing to go on.

**1b — Derive `TOPIC_SLUG`** (kebab-case) from whatever subject you identified. "How does LiteLLM
route requests" → `litellm`. "kubernetes ingress" → `kubernetes-ingress` or just `kubernetes` if
that's already an existing topic (prefer extending an existing topic over fragmenting into a new
near-duplicate one — check existing `knowledge/*/` directories first).

**1c — Derive `CATEGORY`:**
1. Check `source_map.py` `TOPIC_CATEGORIES` dict for the topic
2. Check existing `knowledge/*/` directories for a folder matching the topic
3. Infer from subject matter if neither matches (a language → `languages`, a framework →
   `frontend`/`python-frameworks`/etc. matching the existing category naming, a non-code subject →
   whatever existing category fits, or `uncategorized`)

**1d — Confirm briefly before spawning** (one line, not a question the user has to answer): state
the resolved `TOPIC_SLUG` and `CATEGORY` so the user can redirect if you inferred wrong, then
proceed — don't block on it.

---

## Step 2: Spawn Background Agent

Spawn a single background agent (Haiku model for cost) with `run_in_background=true`.

The agent prompt must include ALL of the following. Copy this template, filling in `TOPIC_SLUG` and `CATEGORY`:

```
You are a research agent for the clean-rag knowledge base. Your job is to grab real documentation, convert it, save it, and index it. You NEVER read content you fetch. You NEVER write content from your training data. You only grab and convert.

FIRST ACTION: Call POST http://127.0.0.1:8612/context with {"agent":"research-rag-agent","task_description":"research and index topic: TOPIC_SLUG in category CATEGORY"}

TOPIC: TOPIC_SLUG
CATEGORY: CATEGORY
CLEAN_RAG_HOME: resolve this from your own CLAUDEBOOST_HOME environment variable, joined with
  /clean-rag — do not hardcode a path, it differs per machine (e.g. C:/prj/ClaudeBoost/clean-rag
  on some setups, C:/Development/ClaudeBoost/clean-rag on others)
KNOWLEDGE_DIR: <CLEAN_RAG_HOME>/knowledge/CATEGORY/TOPIC_SLUG

## Step 1: Check if topic is in source_map

Run this search to check:
```bash
grep -c "\"TOPIC_SLUG\"" "<CLEAN_RAG_HOME>/research/source_map.py"
```

If the topic IS in source_map (count > 0), call acquire-topic directly:
```bash
curl -s -X POST http://127.0.0.1:8613/acquire-topic -H "Content-Type: application/json" -d '{"topic":"TOPIC_SLUG","category":"CATEGORY"}'
```
This runs the 4 layer waterfall (GitHub sparse checkout, llms.txt, BFS crawl) automatically. Skip to Step 5.

If NOT in source_map, continue to Step 2.

## Step 2: Source Discovery

Run 3 WebSearch queries:
1. "TOPIC_SLUG best practices guide"
2. "TOPIC_SLUG comprehensive reference documentation"
3. "TOPIC_SLUG patterns examples"

Also try microsoft_docs_search MCP tool if the topic relates to Microsoft technologies.

Collect all URLs from search results.

## Step 3: Source Quality Filtering

Filter URLs by domain tier. Do NOT read any page content to evaluate quality. Use the domain/URL only.

Tier A (auto include, fetch these):
.gov, .edu, .org (standards bodies), github.com, wikipedia.org, learn.microsoft.com,
developer.mozilla.org, owasp.org, refactoring.guru, martinfowler.com, 12factor.net,
docs.python.org, react.dev, angular.dev, vuejs.org, nextjs.org

Tier B (include if relevant):
stackoverflow.com, dev.to, freecodecamp.org, baeldung.com, digitalocean.com,
realpython.com, geeksforgeeks.org, w3schools.com, tutorialspoint.com

Tier C (EXCLUDE, never fetch):
medium.com, hashnode.dev, personal blogs, SEO content farms, paywalled sites

Cap at 15 URLs max.

## Step 4: Fetch and Save

Create the knowledge directory if it does not exist:
```bash
mkdir -p "<KNOWLEDGE_DIR>"
```

For each Tier A/B URL:
1. Use WebFetch to grab the page (returns markdown)
2. Save with the Write tool to: <KNOWLEDGE_DIR>/<slugified-url>.md
3. Add this header at the top of each saved file:
   <!-- Source: <url> | Tier: <A or B> | Topic: TOPIC_SLUG | Fetched: <YYYY-MM-DD> -->
4. After saving, check file size. If under 500 bytes, delete it (navigation only page).
5. If WebFetch fails on a URL, skip it and note it in your report.

CRITICAL RULES:
- NEVER read any saved file after writing it
- NEVER write content from your training data
- NEVER analyze or summarize fetched content
- Only check file size as a quality signal
- If a domain is blocked, try other domains. Do not fall back to writing from memory.

## Step 5: Check for Existing Files

If the topic already has files in the knowledge directory, do NOT delete or overwrite them. Save new files alongside existing ones with different names.

## Step 6: Index

```bash
curl -s -X POST http://127.0.0.1:8613/index-topic -H "Content-Type: application/json" -d '{"topic":"TOPIC_SLUG","category":"CATEGORY","force":true}'
```

## Step 7: Verify and Report

```bash
curl -s -X POST http://127.0.0.1:8613/search -H "Content-Type: application/json" -d '{"query":"TOPIC_SLUG","sources":["topic:TOPIC_SLUG"],"limit":3,"min_score":0.5}'
```

End your response with ## Summary (under 300 words):
- Files fetched: N
- Files saved (passed quality): N
- Existing files kept: N
- Chunks indexed: N (from index-topic response)
- Top 3 search scores
- URLs that failed (for retry)
- Any issues encountered
```

After spawning, tell the user:
"Background research agent spawned for topic `TOPIC_SLUG` (category: `CATEGORY`). You'll be notified when it completes."

---

## What's Next After /research-rag

| If... | Then run... |
|-------|------------|
| You want to seed an entire category | `/seed-clean-rag <category>` |
| The clean-rag server is down | `/fix-rag` |
| You want to check what topics exist | `curl http://127.0.0.1:8613/status` |
| You want to search the new topic | `POST /search {"query":"...","sources":["topic:TOPIC_SLUG"]}` |
