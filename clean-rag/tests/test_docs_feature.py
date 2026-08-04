"""Regression tests for the docs RAG feature's chunk/strip/sanity fixes.

Guards bugs found by adversarial review against real eCFR data:
  1. an oversized section split on blank-line gaps only, so single-newline
     eCFR paragraphs never split and one chunk silently overflowed the embedder;
  2. raw eCFR XML markup reached the embedder and the stored content;
  3. a JS-shell page with no real heading passed the ingest content check;
  4. ingest_source zipped kept-chunk metadata against the *unfiltered* raw
     chunk list, so one dropped no-citation chunk misaligned every later
     chunk's content with the wrong citation and truncated the tail.

Deterministic: no network. A word-count stand-in for the real subword
tokenizer keeps the token-limit property checkable without loading a model.
"""

from server.docs_chunker import chunk_by_heading, heading_pattern_matches
from server.docs_fetch import ecfr_xml_to_text

# eCFR-shaped: <P> paragraphs on single-newline-separated lines, a
# hierarchy_metadata JSON blob on the DIV, and a <CITA> Federal Register footer.
ECFR_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<DIV8 N="160.103" TYPE="SECTION" '
    'hierarchy_metadata="{&quot;citation&quot;:&quot;45 CFR 160.103&quot;}">\n'
    "<HEAD>§ 160.103 Definitions.</HEAD>\n"
    "<P>Except as otherwise provided, the following definitions apply.</P>\n"
    "<P><I>Act</I> means the Social Security Act.</P>\n"
    "<P>Protected health information means individually identifiable "
    "health information transmitted or maintained in any form.</P>\n"
    "<CITA TYPE=\"N\">[65 FR 82798, Dec. 28, 2000]</CITA>\n"
    "</DIV8>\n"
)


def _wc(text):
    return len(text.split())


def test_ecfr_strip_removes_markup_keeps_prose():
    clean = ecfr_xml_to_text(ECFR_XML)
    for junk in ("<?xml", "<DIV8", "<HEAD>", "<P>", "<I>", "<CITA",
                 "hierarchy_metadata", "&quot;", "82798"):
        assert junk not in clean, junk
    assert "160.103 Definitions" in clean
    assert "Protected health information means" in clean
    assert "Social Security Act" in clean


def test_ecfr_strip_gives_single_newline_paragraphs():
    clean = ecfr_xml_to_text(ECFR_XML)
    # each <P>/<HEAD> becomes its own line; no blank-line gaps
    assert "\n\n" not in clean
    assert len(clean.splitlines()) == 4


def test_oversized_single_newline_section_splits_under_limit():
    # 30 single-newline paragraphs, each ~10 words; markdown-only "\n\n+"
    # splitting would have found nothing to split on and made ONE chunk.
    paras = ["word " * 10 for _ in range(30)]
    text = "\n".join(p.strip() for p in paras)
    chunks = chunk_by_heading(
        text, heading_pattern="(?!)", max_tokens=40, min_tokens=1,
        token_counter=_wc,
    )
    assert len(chunks) > 1
    assert all(_wc(c.content) <= 40 for c in chunks)


def test_single_oversized_paragraph_is_split_finer():
    # one paragraph, no newlines, far over the limit -> must still be broken up
    big = "alpha beta gamma delta epsilon zeta eta theta iota kappa. " * 20
    chunks = chunk_by_heading(
        big, heading_pattern="(?!)", max_tokens=30, min_tokens=1,
        token_counter=_wc,
    )
    assert len(chunks) > 1
    assert all(_wc(c.content) <= 30 for c in chunks)


def test_runt_tail_merge_never_exceeds_limit():
    text = "\n".join(["word " * 20] * 3 + ["tiny"])
    chunks = chunk_by_heading(
        text, heading_pattern="(?!)", max_tokens=25, min_tokens=5,
        token_counter=_wc,
    )
    assert all(_wc(c.content) <= 25 for c in chunks)


def test_heading_match_rejects_nav_junk():
    junk = ("Texas Constitution and Statutes Home page\n"
            "Agriculture Code\nchevron_right\nBusiness & Commerce Code")
    assert not heading_pattern_matches(junk, r"^Sec\.\s*\d+\.\d+")


def test_heading_match_accepts_real_statute():
    real = "Sec. 392.001. DEFINITIONS.\nIn this chapter:\n(1) term means ..."
    assert heading_pattern_matches(real, r"^Sec\.\s*\d+\.\d+")


def test_sentinel_pattern_never_matches():
    assert not heading_pattern_matches("anything at all\nSec. 1.1", "(?!)")



def test_ingest_stores_each_kept_chunk_with_its_own_content(tmp_path, monkeypatch):
    # bad-cop's repro shape: a droppable no-citation "Preamble" chunk followed
    # by two real headed sections. A citation_prefix of a single space makes the
    # Preamble's citation empty (dropped) while both Sec. headings keep theirs.
    # The buggy zip(metas, embeddings, raw_chunks) paired each kept meta with the
    # WRONG raw chunk's content and truncated the tail; every kept chunk must
    # instead be stored with its OWN content under its OWN citation.
    from server import docs_store
    from server.store import ChromaStore

    # Section bodies are padded past min_tokens (50) so chunk_by_heading's
    # runt-tail merge doesn't collapse them into one chunk -- two kept chunks
    # after a drop is exactly what exercises the misaligned zip.
    filler = ("statutory text " * 30).strip()
    text = (
        "PREAMBLEONLY preamble text with no heading here.\n"
        "Sec. 1.1. FIRST SECTION.\n"
        f"FIRSTONLY content of the first section. {filler}\n"
        "Sec. 1.2. SECOND SECTION.\n"
        f"SECONDONLY content of the second section. {filler}\n"
    )

    topic_dir = tmp_path / "topic"
    monkeypatch.setattr(docs_store, "_topic_dir", lambda topic: topic_dir)

    class FakeEmbedder:
        max_tokens = 1000

        def count_tokens(self, s):
            return len(s.split())

        def embed(self, texts):
            return [[0.1, 0.2, 0.3] for _ in texts]

    stats = docs_store.ingest_source(
        topic="unit-test-topic",
        source_id="src-1",
        text=text,
        heading_pattern=r"^Sec\.\s*\d+\.\d+",
        citation_prefix=" ",
        source_url="http://example.test/doc",
        jurisdiction="Testland",
        doc_embedder=FakeEmbedder(),
        force=True,
    )

    assert stats["chunks_created"] == 2
    assert stats["chunks_dropped_no_citation"] == 1

    store = ChromaStore(persist_dir=str(topic_dir / "chroma"))
    stored = store.get_by_source("docs", "src-1", limit=10)
    by_citation = {r.metadata["citation"]: r.content for r in stored}

    assert set(by_citation) == {"Sec. 1.1. FIRST SECTION.", "Sec. 1.2. SECOND SECTION."}
    first = by_citation["Sec. 1.1. FIRST SECTION."]
    second = by_citation["Sec. 1.2. SECOND SECTION."]
    # each citation carries ITS OWN section content, never a neighbor's or the preamble's
    assert "FIRSTONLY" in first and "SECONDONLY" not in first
    assert "SECONDONLY" in second and "FIRSTONLY" not in second
    # the dropped preamble text must appear in NO stored chunk
    assert all("PREAMBLEONLY" not in content for content in by_citation.values())
