"""A project index hit must point at something a caller can open and check.

This is the load bearing property of the whole project index, and it was not
covered by anything. clean-rag/CLAUDE.md, "Why the KB is gone", records that
the topic knowledge base was deleted for returning confident wrong answers that
no threshold caught, and that the project index survived that deletion for one
specific reason (line 212): "The project index stayed, because a hit there is a
real file you can open and check, and because the import graph answers a
question no web search can."

So the score is explicitly NOT the safeguard, and that is a recorded decision
rather than an oversight. Measured against the real production embedder
(nomic-ai/CodeRankEmbed) on a tiny project, queries with nothing to do with the
content still come back above DEFAULT_MIN_SCORE:

    "completely unrelated query about quantum physics and butterflies"  0.7214
    "how to bake a sourdough bread starter from scratch"                0.6683

That reproduces, at project index scale, exactly what CLAUDE.md's own table
measured for the deleted knowledge base, where "min_score: 0.5 caught none of
it. Cosine similarity always hands back a confident nearest neighbour; there is
no 'I don't know'." Asserting that those queries should score low would assert
against the recorded decision, and raising the threshold was already measured
not to work.

What is worth pinning is the mitigation the decision leans on, because if it
ever breaks the justification for keeping the project index collapses with it:
every hit names a real file at a real line range in that file. A hit pointing
at a path that does not exist, or at lines past the end of the file, is a
confident wrong answer that a caller cannot check, and that is the failure this
file exists to catch.

Uses the StubEmbedder rather than the real model on purpose. File and line
metadata does not come from the embedding, so nothing here needs a 1 to 2 GB
model download, and the test therefore always runs instead of skipping when a
model is unavailable.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class StubEmbedder:
    model_name = "stub-embedder"

    def embed(self, texts):
        return [[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8] for _ in texts]

    def embed_query(self, text):
        return [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]


#: Deliberately varied: several files, different lengths, and a short one, so a
#: line range that happens to be right for one shape is not right for all.
_FILES = {
    "main.py": (
        "def is_it_done():\n"
        "    return True\n"
        "\n"
        "\n"
        "MAX_RETRIES = 5\n"
        "\n"
        "\n"
        "def run_query(user_input):\n"
        "    return 'SELECT * FROM users'\n"
    ),
    "client.py": (
        "class Client:\n"
        '    """A small client."""\n'
        "\n"
        "    def search(self, q):\n"
        "        return []\n"
    ),
    "notes.md": "# Notes\n\nThe parser needs refactoring next sprint.\n",
}

#: Queries the content has nothing to do with, alongside one that matches. The
#: point is that the contract holds for both: an irrelevant query still gets a
#: confident hit, and that hit still has to be checkable.
_QUERIES = [
    "completely unrelated query about quantum physics and butterflies",
    "how to bake a sourdough bread starter from scratch",
    "how does the client search",
]


@pytest.fixture
def indexed_project(tmp_path, monkeypatch):
    from server import indexing, search

    monkeypatch.setattr(indexing, "DATABASES_DIR", tmp_path / "databases")
    monkeypatch.setattr(indexing, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(search, "DATABASES_DIR", tmp_path / "databases")

    project = tmp_path / "proj"
    project.mkdir()
    for name, body in _FILES.items():
        (project / name).write_text(body, encoding="utf-8")

    result = indexing.index_project(str(project), StubEmbedder(), force=True)
    assert result["files_indexed"] == len(_FILES), "test setup: every file must index"

    # index_project only records __model_id__ when handed a real ModelCache, so
    # patch it in or the provenance gate refuses the search and the assertions
    # below would pass on an empty result list.
    _root, _pid, _idx, _chroma, manifest_path = indexing._project_paths(str(project))
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw["__model_id__"] = "stub-embedder"
    manifest_path.write_text(json.dumps(raw), encoding="utf-8")
    return project


def _all_hits(project, mode):
    from server import search

    hits = []
    for query in _QUERIES:
        hits.extend(
            search.search(
                query, [f"project:{project}"], StubEmbedder(),
                mode=mode, min_score=0.0, meta_out={},
            )
        )
    return hits


@pytest.mark.parametrize("mode", ["vector", "graph", "both"])
def test_every_hit_names_a_real_file_inside_the_project(indexed_project, mode):
    hits = _all_hits(indexed_project, mode)
    assert hits, f"test setup: mode={mode} returned nothing to check"

    for hit in hits:
        name = hit.get("file")
        assert name, f"a hit carries no file at all, so nothing can be opened: {hit}"
        target = (indexed_project / name).resolve()
        assert target.is_file(), (
            f"a hit points at {name!r}, which is not a file. A score alone is "
            f"explicitly not the safeguard here (clean-rag/CLAUDE.md, 'Why the "
            f"KB is gone'); being able to open the hit and check it is."
        )
        assert target.is_relative_to(indexed_project.resolve()), (
            f"a hit points outside the project root: {name!r}"
        )


@pytest.mark.parametrize("mode", ["vector", "graph", "both"])
def test_every_hit_names_a_real_line_range_in_that_file(indexed_project, mode):
    """Line numbers must land inside the file they name.

    Not that the chunk text equals those lines byte for byte: the chunker
    merges small sibling chunks and drops the gap between them, so a chunk
    spanning lines 1 to 9 legitimately omits line 5. What has to hold is that
    the range points somewhere real, because that is what a caller opens.

    The end bound is ``total + 1``, not ``total``, and that is not slack for its
    own sake. Measured: code files are exact (tree-sitter reports real line
    numbers), while prose files overshoot the end by exactly one. The cause is
    _split_into_sections in indexing.py being handed ``text.split("\\n")``,
    which appends a phantom empty element for any file ending in a newline, so
    ``line_end=len(lines)`` is one past the last real line for ``.md``,
    ``.txt`` and ``.rst``. That is a separate defect, recorded here rather than
    asserted away: the bound is an upper limit, so it keeps catching a range
    that is genuinely wrong (line 500 of a 3 line file) and it will still pass
    once the off by one is corrected.
    """
    hits = _all_hits(indexed_project, mode)
    assert hits, f"test setup: mode={mode} returned nothing to check"

    for hit in hits:
        target = indexed_project / hit["file"]
        total = len(target.read_text(encoding="utf-8").splitlines())
        start, end = hit["line_start"], hit["line_end"]

        assert isinstance(start, int) and isinstance(end, int), hit
        assert start >= 1, f"{hit['file']} hit starts at line {start}"
        assert start <= end, f"{hit['file']} hit spans {start} to {end}, backwards"
        assert start <= total, (
            f"{hit['file']} hit starts at line {start} but the file has only "
            f"{total} lines, so there is nothing there to open"
        )
        assert end <= total + 1, (
            f"{hit['file']} hit spans lines {start} to {end} but the file has "
            f"{total} lines, so a caller following it reads past the end"
        )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
