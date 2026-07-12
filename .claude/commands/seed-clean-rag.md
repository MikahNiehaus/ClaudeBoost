---
argument-hint: <category> [--topics topic1 topic2 ...] [--discover] [--batch-size N]
description: "Bulk seed the clean-rag knowledge base by discovering and researching topics in a category"
allowed-tools: Agent, Bash, Glob, Grep, Read, WebSearch, WebFetch, Write
---

# /seed-clean-rag — Bulk Topic Seeding

Arguments: **$ARGUMENTS**

Discovers topics within a category, checks existing coverage, then loops through each topic calling `/research-rag` to build up the knowledge base with real fetched sources. This is the bulk version of `/research-rag`.

---

## Step 1: Parse Arguments

Split `$ARGUMENTS` on whitespace.

- First token: `CATEGORY` (required). Example: `methodology`, `languages`, `security`, `business`
- `--topics topic1 topic2 ...`: explicit list of topic slugs. If omitted, uses discovery or predefined lists.
- `--discover`: force WebSearch discovery of topics (even if a predefined list exists for this category)
- `--batch-size N`: how many topics to research per round (default: 3). Controls parallelism and cost.

If no `CATEGORY` provided, print usage and stop.

---

## Step 2: Build Topic List

### 2a: Check for predefined lists

These predefined lists cover common categories. Use them unless `--discover` is specified:

**methodology** (code quality and development practices):
```
clean-code-principles, solid-principles, code-smells, refactoring-techniques,
error-handling, code-review, api-design, defensive-programming,
logging-observability, testing-strategy, concurrency, performance-optimization,
dependency-management, technical-debt, documentation-practices,
database-design, configuration-management, ci-cd, code-complexity-metrics,
design-patterns, architectural-patterns, microservices-patterns
```

**security**:
```
owasp-top-10, authentication-patterns, authorization-patterns,
input-validation, cryptography-basics, secure-coding, vulnerability-management,
api-security, session-management, secrets-management
```

For any other category (or if `--discover` is set), go to step 2b.

### 2b: Discover topics via WebSearch

Run 3 searches:
1. `"<CATEGORY> topics list comprehensive guide"`
2. `"<CATEGORY> best practices areas subtopics"`
3. `"<CATEGORY> knowledge areas comprehensive"`

Extract topic slugs from search results. Convert each to kebab case. Deduplicate. Cap at 25 topics max.

### 2c: Merge with explicit topics

If `--topics` was provided, merge those into the list (they go first, as priority).

---

## Step 3: Check Existing Coverage

For each topic in the list:

```bash
# Check if knowledge directory exists and count files. Resolve the base path from your own
# CLAUDEBOOST_HOME env var joined with /clean-rag -- do not hardcode it, it differs per machine.
ls "${CLAUDEBOOST_HOME}/clean-rag/knowledge/CATEGORY/<topic>/" 2>/dev/null | wc -l
```

Also check for source headers in existing files:
```bash
grep -l "<!-- Source:" "${CLAUDEBOOST_HOME}/clean-rag/knowledge/CATEGORY/<topic>/"*.md 2>/dev/null | wc -l
```

Assign priority:
- **Priority 1** (needs full research): topic directory doesn't exist or has 0 files
- **Priority 2** (needs supplementing): has files but none with `<!-- Source:` headers (training data, needs real sources added)
- **Priority 3** (already good): has files WITH source headers. Skip unless `--force` is specified.

Sort topics by priority (1 first, then 2, then 3).

Print the coverage report:
```
Topic Coverage Report for: CATEGORY
  Priority 1 (no files):     N topics
  Priority 2 (no sources):   N topics  
  Priority 3 (has sources):  N topics
  Total to research:         N topics (batch size: B)
```

---

## Step 4: Research Loop

Process topics in batches of `--batch-size` (default 3).

For each batch:

1. **Check clean-rag server health first:**
```bash
curl -s --connect-timeout 5 http://127.0.0.1:8613/status
```
If the server is down, run `/fix-rag` and wait for it before continuing.

2. **Spawn background agents** for each topic in the batch.

For each topic, spawn via the `/research-rag` pattern (the same background agent prompt from that skill), with `run_in_background=true`. Use Haiku model.

3. **Wait for all agents in the batch to complete** before starting the next batch. After each batch completes, print progress:

```
Batch N/M complete:
  Topics researched: [list]
  Files added this batch: N
  Next batch: [list of next topics]
```

4. **Between batches**, verify the server is still healthy and hasn't run out of memory. If `/status` shows issues, pause and run `/fix-rag`.

---

## Step 5: Final Verification

After all batches are done:

For each researched topic, run a verification search:
```bash
curl -s -X POST http://127.0.0.1:8613/search -H "Content-Type: application/json" -d '{"query":"<topic-name>","sources":["topic:<topic>"],"limit":3,"min_score":0.5}'
```

---

## Step 6: Final Report

Print the full summary:

```
Seed Complete: CATEGORY
  Topics researched:           N
  Total files added:           N
  Topics with scores >= 0.5:   N (good)
  Topics with scores < 0.5:    N (may need manual attention)
  Topics skipped (priority 3): N
  Errors:                      N

Topic Details:
  <topic-1>: N files, best score: 0.XX
  <topic-2>: N files, best score: 0.XX
  ...

Topics Needing Attention:
  <topic-X>: reason (no fetchable sources, all domains blocked, etc.)
```

---

## What's Next After /seed-clean-rag

| If... | Then run... |
|-------|------------|
| Some topics failed or scored low | `/research-rag <topic> <category> --sources <specific-urls>` with manual URL curation |
| You want to seed another category | `/seed-clean-rag <other-category>` |
| You want to verify the full knowledge base | `curl http://127.0.0.1:8613/status` to see all topics |
| A topic needs reorganization | `/research-rag <topic> <new-category>` (moves it) |
