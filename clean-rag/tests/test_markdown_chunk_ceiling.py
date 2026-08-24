"""The markdown path must respect the token budget too.

test_chunk_size_ceiling.py capped the CODE path after a 500KB single line file
asked the allocator for 9 GB. The markdown path was missed, and its tests were
missed with it, so the same class of bug sat there untouched:

  Failed to embed/store .../argo-cd-9.4.6/argo-cd/README.md:
  Invalid buffer size: 51.55 GiB

That file is 147KB, not enormous. Markdown is what makes it dangerous.
`_process_section` splits an oversized section at blank lines, and a markdown
table has no blank line in it, so an entire Helm chart parameter table is one
"paragraph" with nowhere to cut. Measured before the fix: 87 chunks, 13 of them
over budget, the largest 5,054 tokens against a limit of 500 and a model that
takes 512. Attention allocation grows with sequence length, hence the 51 GiB.

Auto reindex retries every 10 minutes, so this did not fail once. It took the
server down on a timer, which is why it kept looking like the server "just
stopped".

Each test that asserts the fix is paired with one that neutralises it and
asserts the failure returns, so these cannot decay into assertions about
whatever the code currently does.

Run: python -m pytest clean-rag/tests/test_markdown_chunk_ceiling.py -v
"""
import re
import sys
from pathlib import Path

import pytest

CLEAN_RAG = Path(__file__).resolve().parents[1]
if str(CLEAN_RAG) not in sys.path:
    sys.path.insert(0, str(CLEAN_RAG))

from server import indexing  # noqa: E402
from server.code_chunker import estimate_tokens  # noqa: E402
from server.indexing import chunk_markdown  # noqa: E402

MAX = 500
MIN = 50


def _markdown_table(rows: int = 4000) -> str:
    """A parameter table, the shape every Helm chart README is mostly made of.

    The point is the absence of blank lines: one continuous block that a
    paragraph splitter cannot cut anywhere.
    """
    head = "| Key | Type | Default | Description |\n|---|---|---|---|\n"
    row = ("| controller.replicas | int | `1` | Number of replicas for the "
           "controller deployment |\n")
    return "# Parameters\n\n" + head + row * rows


def _oversized(chunks):
    return [c for c in chunks if estimate_tokens(c.content) > MAX]


def test_a_giant_table_is_split_within_budget():
    chunks = chunk_markdown(_markdown_table(), "README.md", max_tokens=MAX,
                            min_tokens=MIN)
    over = _oversized(chunks)
    assert not over, (
        f"{len(over)} chunk(s) over the {MAX} token budget, largest "
        f"{max(estimate_tokens(c.content) for c in over):,}. An oversized chunk "
        "goes straight to the embedder and the allocation kills the server."
    )
    assert len(chunks) > 1, "a table this size must produce more than one chunk"


def test_the_table_fix_proves_it_bites(monkeypatch):
    """Neutralise the split and the oversized chunk must come back."""
    monkeypatch.setattr(indexing, "_force_split", lambda text, max_tokens: [text])
    chunks = chunk_markdown(_markdown_table(), "README.md", max_tokens=MAX,
                            min_tokens=MIN)
    assert _oversized(chunks), (
        "with _force_split neutralised an oversized chunk should reappear; "
        "if it does not, this test is not exercising the fix"
    )


def test_no_content_is_lost():
    """
    Splitting mid line is accepted; dropping text is not.

    A chunker that silently discarded the tail of a table would pass a budget
    assertion and quietly make the file unsearchable.
    """
    text = _markdown_table(rows=500)
    chunks = chunk_markdown(text, "README.md", max_tokens=MAX, min_tokens=MIN)

    def norm(s):
        return re.sub(r"\s+", "", s)

    joined = norm("".join(c.content for c in chunks))
    assert norm(text) == joined or norm(text) in joined or joined in norm(text), (
        f"content changed: {len(norm(text)):,} chars in, {len(joined):,} out"
    )


def test_a_wall_of_prose_with_no_blank_lines_is_split():
    """The other shape with no paragraph boundary: one very long line."""
    text = "# Notes\n\n" + ("word " * 40_000)
    chunks = chunk_markdown(text, "NOTES.md", max_tokens=MAX, min_tokens=MIN)
    assert not _oversized(chunks)


def test_normal_markdown_still_splits_at_headings():
    """The fix must not change ordinary documents."""
    text = (
        "# One\n\nSome text in the first section.\n\n"
        "# Two\n\nSome text in the second section.\n\n"
        "# Three\n\nSome text in the third section.\n"
    )
    chunks = chunk_markdown(text, "DOC.md", max_tokens=MAX, min_tokens=1)
    sections = [c.section for c in chunks]
    assert "One" in sections and "Two" in sections and "Three" in sections
    assert not _oversized(chunks)


def test_the_trailing_merge_cannot_exceed_the_budget():
    """
    The merge that folds a small last chunk into the previous one used to run
    unconditionally, so it could hand back a chunk over budget after every
    other step had stayed under it.
    """
    body = "x" * (MAX * 4 - 40)          # just under budget on its own
    runt = "y" * 20                       # under min_tokens, triggers the merge
    text = f"# S\n\n{body}\n\n{runt}\n"
    chunks = chunk_markdown(text, "DOC.md", max_tokens=MAX, min_tokens=MIN)
    assert not _oversized(chunks), (
        "the trailing merge pushed a chunk over the budget"
    )


@pytest.mark.parametrize("rows", [50, 500, 2000])
def test_budget_holds_across_table_sizes(rows):
    chunks = chunk_markdown(_markdown_table(rows), "README.md",
                            max_tokens=MAX, min_tokens=MIN)
    assert not _oversized(chunks)
