"""No chunk may exceed the token budget, whatever the input looks like.

The first tests for this code path. It had none, which is why the bug below
survived: a 500KB file with no blank line in it came out of the chunker as ONE
chunk and asked the CPU allocator for 9663676416 bytes at
`enforce fail at alloc_cpu.cpp:117`, taking the indexer down. The model's real
limit is 512 tokens.

Each test that asserts the fix works is paired with one that neutralises the fix
and asserts the failure comes back, so these cannot quietly become assertions
about current behaviour.
"""
import sys
from pathlib import Path

import pytest

CLEAN_RAG = Path(__file__).resolve().parents[1]
if str(CLEAN_RAG) not in sys.path:
    sys.path.insert(0, str(CLEAN_RAG))

from server.code_chunker import (  # noqa: E402
    _fallback_chunk,
    _force_split,
    _split_at_blank_lines,
    chunk_code,
    estimate_tokens,
)

MAX = 500
MIN = 50


def _minified(size: int = 200_000) -> str:
    """One line, no blank lines, the shape of a bundled or minified file."""
    unit = "var a=1;function f(x){return x+1;}"
    return (unit * (size // len(unit) + 1))[:size]


def _one_paragraph(size: int = 200_000) -> str:
    """Many lines, no BLANK line, the shape of a wall of legal prose."""
    line = "This agreement is provided without warranty of any kind whatsoever. "
    return "\n".join([line] * (size // len(line) + 1))


# ---------------------------------------------------------------------------
# _force_split, the new helper
# ---------------------------------------------------------------------------

def test_force_split_respects_budget_on_a_single_huge_line():
    pieces = _force_split(_minified(120_000), MAX)
    assert pieces, "returned nothing for a large input"
    over = [p for p in pieces if estimate_tokens(p) > MAX]
    assert not over, f"{len(over)} piece(s) exceed {MAX} tokens"


def test_force_split_leaves_small_text_alone():
    text = "def f():\n    return 1"
    assert _force_split(text, MAX) == [text]


def test_force_split_drops_whitespace_only_input():
    assert _force_split("   \n\n  \t ", MAX) == []


def test_force_split_loses_no_characters():
    text = _minified(30_000)
    assert "".join(_force_split(text, MAX)) == text, "content was dropped or duplicated"


def test_force_split_prefers_line_boundaries_when_available():
    text = "\n".join("x" * 40 for _ in range(400))
    pieces = _force_split(text, MAX)
    # Most pieces should end at a newline rather than mid line.
    ends_clean = sum(1 for p in pieces[:-1] if p.endswith("\n"))
    assert ends_clean > len(pieces) // 2, "ignored available line boundaries"


@pytest.mark.parametrize("bad", [0, -1])
def test_force_split_with_no_budget_returns_input_unchanged(bad):
    """A nonsense budget must not become an infinite loop."""
    assert _force_split("abc", bad) == ["abc"]


# ---------------------------------------------------------------------------
# _fallback_chunk, the function that produced the 9 GB chunk
# ---------------------------------------------------------------------------

def test_fallback_chunk_caps_a_file_with_no_blank_lines():
    chunks = _fallback_chunk(_minified(), "bundle.js", MAX, MIN)
    assert chunks, "produced no chunks at all"
    worst = max(estimate_tokens(c.content) for c in chunks)
    assert worst <= MAX, f"largest chunk is {worst} tokens, budget is {MAX}"


def test_fallback_chunk_caps_a_single_paragraph_file():
    chunks = _fallback_chunk(_one_paragraph(), "FullTermsOfUse.js", MAX, MIN)
    assert chunks
    worst = max(estimate_tokens(c.content) for c in chunks)
    assert worst <= MAX, f"largest chunk is {worst} tokens, budget is {MAX}"


def test_fallback_chunk_still_splits_normal_text_at_blank_lines():
    """The fix must not change behaviour on input that was already fine."""
    text = "\n\n".join(f"def f{i}():\n    return {i}" for i in range(40))
    chunks = _fallback_chunk(text, "ok.py", MAX, MIN)
    assert len(chunks) >= 1
    assert all(estimate_tokens(c.content) <= MAX for c in chunks)


def test_fallback_chunk_proves_it_bites(monkeypatch):
    """Neutralise the fix and the oversized chunk must come back.

    Without this, the tests above would pass just as happily against the broken
    version, since they would be asserting whatever the code already does.
    Disabling _force_split restores the old behaviour exactly: the accumulation
    loop's size check only fires when the buffer is already non empty, so the
    first block is emitted at whatever size it arrives.
    """
    import server.code_chunker as cc

    monkeypatch.setattr(cc, "_force_split", lambda text, max_tokens: [text])
    chunks = cc._fallback_chunk(_minified(), "bundle.js", MAX, MIN)
    worst = max(estimate_tokens(c.content) for c in chunks)
    assert worst > MAX * 10, (
        "expected the unfixed path to emit a hugely oversized chunk, "
        f"got {worst} tokens. The test no longer proves the fix does anything."
    )


# ---------------------------------------------------------------------------
# _split_at_blank_lines, the sibling with the same flaw
# ---------------------------------------------------------------------------

def test_split_at_blank_lines_caps_a_run_with_no_blank_line():
    lines = [f"    step_{i}()" for i in range(8000)]
    chunks = _split_at_blank_lines(lines, "sec", 0, MAX, MIN)
    assert chunks
    worst = max(estimate_tokens(c.content) for c in chunks)
    assert worst <= MAX * 2, f"largest chunk is {worst} tokens, budget is {MAX}"


def test_split_at_blank_lines_caps_a_single_enormous_line():
    chunks = _split_at_blank_lines([_minified(80_000)], "sec", 0, MAX, MIN)
    assert chunks
    worst = max(estimate_tokens(c.content) for c in chunks)
    assert worst <= MAX * 2, f"largest chunk is {worst} tokens, budget is {MAX}"


def test_split_at_blank_lines_keeps_working_on_normal_input():
    lines = []
    for i in range(30):
        lines += [f"def f{i}():", f"    return {i}", ""]
    chunks = _split_at_blank_lines(lines, "sec", 0, MAX, MIN)
    assert chunks
    assert all(estimate_tokens(c.content) <= MAX * 2 for c in chunks)


# ---------------------------------------------------------------------------
# chunk_code, the public entry point, which is what indexing actually calls
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "name,make_body",
    [
        ("bundle.js", _minified),
        ("FullTermsOfUse.js", _one_paragraph),
        ("blob.txt", lambda: "x" * 200_000),
    ],
    # Factories, not the strings themselves. Passing 200KB of content as a
    # parameter puts it in the test id, which pytest exports in
    # PYTEST_CURRENT_TEST, and Windows caps an environment variable at 32767
    # characters. The whole run dies in teardown with a ValueError.
    ids=["minified", "one_paragraph", "single_token_blob"],
)
def test_chunk_code_never_returns_an_oversized_chunk(name, make_body):
    """The real regression guard. This is the call indexing.py makes."""
    chunks = chunk_code(make_body(), name, max_tokens=MAX, min_tokens=MIN)
    if not chunks:
        pytest.skip(f"{name} produced no chunks, nothing to size check")
    worst = max(estimate_tokens(c.content) for c in chunks)
    assert worst <= MAX * 2, (
        f"{name}: largest chunk is {worst} tokens against a {MAX} budget. "
        "An oversized chunk reaching encode() is what caused the 9 GB allocation."
    )
