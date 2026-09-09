# The `docs:` ingestion pipeline (docs_store.py) has the same shape as the deleted topic KB

- **Kind:** architecture-change
- **Area:** server
- **Found by:** bad-cop (clean-rag/server, cli, graphrag, telemetry partition) on 2026-09-07
- **Why it was not fixed in place:** this is a question about whether a whole
  subsystem should exist, not a local defect. `clean-rag/CLAUDE.md:214`
  explicitly says "Do not rebuild the topic KB. If local docs seem necessary,
  the failure above will reproduce, because the problem was never corpus
  quality." Per the review brief for this pass: "if your findings point back
  toward local document storage, you are rediscovering a decision that was
  already made against real evidence... it goes in spec/ as a question, never
  as a fix." This is exactly that situation, so it is written down rather than
  touched.

## What is there now

`clean-rag/server/docs_store.py:1-12` describes itself directly against the
removed feature: "Persistent, topic scoped storage and ingestion for the docs
RAG feature. Mirrors databases/_projects/<hash>/ for project code:
databases/_docs/<topic>/ holds one Chroma collection plus a manifest... this is
meant to persist and be searched across sessions indefinitely."

The pipeline is complete and wired into the live server:

- `clean-rag/server/app.py:565-698` (`handle_docs_ingest`, `POST /docs-ingest`):
  takes a `topic`, a list of `sources` (URL, heading pattern, citation prefix,
  jurisdiction), fetches each one (`docs_fetch.py`), chunks it by heading
  (`docs_chunker.py`), extracts a citation (`docs_citation.py`), embeds it with
  a general prose model, and stores it.
- `clean-rag/server/docs_store.py:65-174` (`ingest_source`): persists chunks
  into `databases/_docs/<topic>/chroma/`, keyed by content hash for incremental
  re-ingest, exactly mirroring `server/indexing.py`'s manifest philosophy for
  project code (own docstring, lines 9-11).
- `clean-rag/server/docs_store.py:193-222` (`search_topic`): plain cosine
  vector search over the topic's collection, called from `server/search.py:465-471`
  whenever a request names a `docs:<topic>` source.
- `clean-rag/server/app.py:701-716` (`handle_docs_status`, `GET/POST /docs-status`):
  reports what has been ingested per topic.
- A general purpose prose embedder is loaded specifically to serve this path:
  `clean-rag/server/app.py:1309-1315`, `_doc_embedder = SentenceTransformerEmbedding()`,
  loaded lazily "on first docs: search or ingest."

None of `/docs-ingest`, `/docs-status`, or the `docs:` source specifier appear
in `clean-rag/CLAUDE.md`'s endpoint table (`clean-rag/CLAUDE.md:181-189`, 7
routes) or in its `search` documentation (`clean-rag/CLAUDE.md:95-117`, which
describes only `project:` sources). The only place `docs:` is documented at all
is inside `server/search.py`'s own docstring (`search.py:379-384`). A reader of
`clean-rag/CLAUDE.md` alone would conclude, incorrectly, that the only durable
retrieval surface left is the project index, and would not know this pipeline
exists, let alone that it is the same shape as the thing the file's closing
section tells them not to rebuild.

## Why it is a problem

`clean-rag/CLAUDE.md:195-214` measured, specifically, why a mechanical
retrieval query over a persisted document store is unsafe: cosine similarity
always returns a confident nearest neighbour, `min_score: 0.5` caught none of
the four measured failures, and "the problem was never corpus quality" -- it
was that "a mechanical query has no judgment behind it."

`docs_store.py`'s `search_topic` (`docs_store.py:193-222`) is exactly that
mechanical query: plain `store.search("docs", query_embedding, limit, min_score)`,
no reasoning step, called with the same `DEFAULT_MIN_SCORE` (0.5,
`config.py:81`) the CLAUDE.md table already showed does not work. This
review's own measurement for the project index (see the sibling finding on
`search.py`'s vector search, and `test_confident_wrong_answers.py`) reproduces
the identical failure shape one layer over: unrelated queries score above 0.5
against a tiny corpus, because there is always a nearest neighbour and no
retrieval-only mechanism can express "none of these are actually relevant."
Nothing about `docs_store.py`'s design differs from the deleted KB on this
specific axis -- it is topic scoped and citation tagged, which is a real
difference in provenance quality, but citation tagging does not change how
`search_topic` ranks a bad match, and a wrong-but-confident citation is
arguably worse than a wrong-but-uncited one, since the citation reads as
authoritative.

The narrower, immediate problem is the documentation gap: a maintainer reading
`clean-rag/CLAUDE.md` end to end, including its explicit "Do not rebuild the
topic KB" closing section, has no way to know from that document that a
topic-scoped persistent ingestion pipeline already exists and is live. That is
how the exact rebuild the file warns against would happen a second time, by
someone who read the warning and reasonably believed it described the current
state of the code.

## What to do instead

This needs a human decision, not a diff, because the two honest resolutions
pull in opposite directions and neither is a local change:

1. **If `docs_store.py` is intentional and meant to stay** (e.g. because its
   narrower scope -- explicit, curated, citation-required legal/regulatory
   sources rather than open-ended scraped topics -- is judged to avoid the
   measured failure in practice): update `clean-rag/CLAUDE.md` to document it
   as a real, current feature, with its own measured evidence for why the
   citation requirement and topic scoping avoid the KB's failure mode (or an
   honest note that it has not been measured yet). Add `/docs-ingest` and
   `/docs-status` to the endpoint table. This is a documentation-only change
   and does not belong in this spec file's bar -- if the decision comes back
   "keep it," the actual doc fix is small enough to do directly.
2. **If `docs_store.py` is drift that reintroduced the removed pattern without
   anyone deciding to**: remove it, the same way the original KB was removed
   (`server/docs_store.py`, `server/docs_chunker.py`, `server/docs_fetch.py`,
   `server/docs_citation.py`, the `/docs-ingest`/`/docs-status` routes in
   `app.py`, and the `docs:` branch in `search.py:465-471`), and fold its one
   genuinely load bearing idea -- citation-required, source-attributed
   ingestion -- into a design that keeps a reasoning step in front of
   retrieval, matching the resolution CLAUDE.md already reached for the
   project index ("retrieval moved to the only thing that can write a decent
   query: a reasoning agent," CLAUDE.md:212).

Either resolution spans more than five files and touches a public interface
(`/docs-ingest`, `/docs-status`, the `docs:` source specifier), which is why
this is written down rather than acted on.

## What it would break

- Anything already relying on ingested `docs:` topics (none observed in this
  partition's own tests or code; `git ls-files` shows no caller outside
  `server/` itself constructing a `docs:` source, but a hook or skill outside
  this review's partition may).
- `server/search.py:465-471`'s `docs:` branch, `handle_docs_ingest` and
  `handle_docs_status` in `app.py`, and the `_doc_embedder` warmup path in
  `create_app()` (`app.py:1309-1315`) would all need to go if option 2 is
  chosen.
- `clean-rag/tests/` was not searched exhaustively for docs_store-specific
  tests in this pass; check `git ls-files clean-rag/tests | grep -i docs`
  before removing anything.

## Open questions

- Was `docs_store.py` built before or after the KB removal decision recorded
  in `clean-rag/CLAUDE.md`? If after, this may be a deliberate, considered
  exception (narrower scope, explicit sourcing) rather than drift, and the
  missing piece is purely documentation.
- Has anyone measured `search_topic`'s actual false-positive rate the way
  CLAUDE.md measured the old KB's? Without that measurement, neither "this is
  fine because it's narrower" nor "this has the same bug" is settled -- this
  spec file's own reasoning by analogy is not a substitute for the same kind of
  measurement CLAUDE.md used to justify the original removal.
- Is there a caller (a hook, a skill, a workflow outside this review's
  partition) that already depends on `/docs-ingest`? That changes which
  resolution above is realistic regardless of which one is judged correct on
  the merits.
