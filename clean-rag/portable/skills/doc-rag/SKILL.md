---
name: doc-rag
description: Gather official documents (statutes, regulations, any authoritative source) on any topic, chunk them at real citation boundaries, and build a persistent, searchable corpus inside clean-rag. Topic agnostic -- the schema is generic, your topic is whatever source list you write. Use to ingest a new topic's sources or to search an already ingested one.
---

# /doc-rag

Downloads official documents for a topic (a source list you supply), chunks
them at real citation boundaries (never mid section), and stores them in a
persistent, topic isolated collection inside clean-rag, searchable afterward
the same way project code already is.

This is generic over topic, not scoped to any one subject: pointing this at
building codes, tax regulations, medical or legal topics, or anything else
is just a new source list file with the same shape, no code changes. Your
source lists live in `clean-rag/docs_sources/*.json`, which is gitignored
(only the schema template is tracked) so whatever topic you're actually
researching never ends up in a commit.

## Why this is safe to persist (read before adding a new topic)

`clean-rag/CLAUDE.md`'s "Why the KB is gone" section is the binding
constraint here: a static, scraped, mixed topic vector index was removed
because it returned confidently wrong answers with no threshold able to
catch it. This feature is not that, on purpose, in three ways:

1. **Topic isolated.** Search always names one `docs:<topic>` source, the
   same discipline `project:<path>` already uses. There is no `all_topics`
   and there will not be one.
2. **Citation required.** Every stored chunk carries a real, checkable
   citation (jurisdiction, section, source URL). A chunk the ingest pipeline
   can't attach a citation to is dropped, not stored anyway. A wrong or weak
   match is falsifiable by the user in seconds, the same property that keeps
   a project's own indexed code trustworthy.
3. **Structure aware chunking.** Chunks split at a real heading/citation
   boundary (a source list entry's own `heading_pattern`), never at an
   arbitrary token window, so a citation is never split across two chunks.

Adding a new topic without a `heading_pattern` that actually matches real
section boundaries in that source, or without a real `citation_prefix`,
reintroduces the exact failure this design avoids. Don't skip it.

## Write a source list

Copy `clean-rag/docs_sources/example.template.json` to
`clean-rag/docs_sources/<your-topic>.json` (that name is gitignored, only
the template is tracked) and fill in real values. Each source entry:

| Field | Meaning |
|---|---|
| `source_id` | Stable id for this source (a URL is fine). Re-ingesting the same `source_id` updates it in place rather than duplicating it. |
| `type` | `"ecfr"` (federal, via eCFR's real REST API, no scraping) or `"html"` (anything else, fetched and converted to text). |
| `heading_pattern` | Regex matching a citation heading line, e.g. `"^Sec\\.\\s*\\d+\\.\\d+\\."` for a state statute chapter. Use `"(?!)"` (never matches) when the fetch is already scoped to exactly one section, so the chunker correctly treats the whole thing as one chunk instead of hunting for a heading that isn't there. |
| `citation_prefix` | The jurisdiction/code prefix, e.g. `"45 CFR 160.103"` or a state code chapter name. |
| `jurisdiction` | e.g. `"Federal"` or a state name. |
| `url` | Required for `type: "html"`. Verify it actually returns real static text before shipping it: a client rendered JS-only site returns a shell no plain fetch can read, and the ingest pipeline will reject it with a clear error rather than silently store nav-menu garbage under a fake looking citation, but it's still worth checking yourself first. |
| `title`, `date`, `section` | Required for `type: "ecfr"` (`section` optional; omit to fetch a whole title, which is usually too large -- scope to a real section instead). |

## Ingest a topic

```
POST http://127.0.0.1:8613/docs-ingest
{
  "topic": "<your-topic>",
  "sources": [ ...your source list's sources array... ],
  "force": false
}
```

Ingestion is incremental: a source whose content hash hasn't changed since
the last ingest is skipped, unless `force: true`. GraphRAG style dynamic
model loading applies here too: the docs embedder loads lazily on first
ingest or search and stays resident the same way the project code embedder
already does, no separate action needed.

## Check what's ingested

```
GET http://127.0.0.1:8613/docs-status?topic=<your-topic>
```

Returns each source's chunk count and last ingest time, plus the topic's
total chunk count.

## Search a topic

```
POST http://127.0.0.1:8613/search
{
  "query": "your question",
  "sources": ["docs:<your-topic>"],
  "mode": "vector"
}
```

Each result carries `citation`, `jurisdiction`, `source_url`, and
`retrieved_at`. Lead with the citation when reporting a result back to the
user, not just the passage: that citation is what makes the answer
verifiable instead of a similarity guess. A low score result is a lead to
verify against the actual source, never a conclusion on its own, same
discipline `research-rag`'s score threshold rule already uses.

## Add a new topic

Write a new source list JSON with the same shape as
`clean-rag/docs_sources/example.template.json`, pick real `heading_pattern`s
by actually looking at how the source's sections are formatted (don't guess
a regex you haven't checked against the real fetched text), then POST it to
`/docs-ingest` with a new `topic` name. Nothing else changes.
