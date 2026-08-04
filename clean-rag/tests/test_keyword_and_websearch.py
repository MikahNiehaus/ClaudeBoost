"""The BM25 keyword leg and the ddgs backed web search transport."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.search import _search_project_keyword, _tokenize  # noqa: E402


def _chunk(file, content, line=1):
    return {"file": file, "content": content, "line_start": line, "score": 0.5}


class TestTokenizer:
    def test_snake_case_splits_and_keeps_the_whole_identifier(self):
        t = _tokenize("_sweep_project")
        assert "_sweep_project" in t and "sweep" in t and "project" in t

    def test_camel_case_splits(self):
        t = _tokenize("sweepProject")
        assert "sweepproject" in t and "sweep" in t and "project" in t

    def test_snake_and_camel_meet_in_the_middle(self):
        """The point of splitting both ways: either spelling finds the other."""
        assert set(_tokenize("sweepProject")) & set(_tokenize("_sweep_project"))

    def test_acronyms_survive(self):
        t = _tokenize("HTTPServer")
        assert "http" in t and "server" in t

    def test_punctuation_and_empty(self):
        assert _tokenize("") == []
        assert _tokenize("!!! ??? ...") == []


class TestKeywordLeg:
    def test_the_exact_identifier_outranks_a_merely_similar_chunk(self):
        """The failure this exists for. Embeddings return things that read
        alike; only a token match knows which one has the literal name."""
        candidates = [
            _chunk("other.py", "def sweep_the_floor():\n    pass\n"),
            _chunk("real.py", "def _sweep_project(pid, entry):\n    return 1\n"),
        ]
        ranked = _search_project_keyword("_sweep_project", candidates, limit=5)
        assert ranked and ranked[0]["file"] == "real.py"

    def test_no_candidates_is_empty_not_an_error(self):
        assert _search_project_keyword("anything", [], limit=5) == []

    def test_an_empty_query_is_inert(self):
        assert _search_project_keyword("", [_chunk("a.py", "x")], limit=5) == []
        assert _search_project_keyword("!!!", [_chunk("a.py", "x")], limit=5) == []

    def test_zero_scoring_chunks_are_dropped(self):
        """A chunk sharing no token with the query is not a keyword hit, and
        including it at rank N would give it fusion weight it did not earn."""
        ranked = _search_project_keyword(
            "zzzznomatch", [_chunk("a.py", "def unrelated(): pass")], limit=5
        )
        assert ranked == []

    def test_duplicates_across_input_lists_are_collapsed(self):
        """The same chunk arrives from both the vector and graph lists. Ranking
        it twice would let one chunk vote twice in the fusion."""
        same = _chunk("a.py", "def target_function(): pass")
        ranked = _search_project_keyword("target_function", [same, dict(same)], limit=5)
        assert len(ranked) == 1

    def test_respects_the_limit(self):
        cands = [_chunk(f"f{i}.py", "def target(): pass") for i in range(20)]
        assert len(_search_project_keyword("target", cands, limit=3)) == 3

    def test_missing_rank_bm25_is_inert_not_fatal(self, monkeypatch):
        """Search must degrade to vector plus graph, not fail."""
        import builtins

        real = builtins.__import__

        def no_bm25(name, *a, **k):
            if name == "rank_bm25":
                raise ImportError("simulated")
            return real(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", no_bm25)
        assert _search_project_keyword("x", [_chunk("a.py", "x")], limit=5) == []


class TestWebSearchTransport:
    def test_uses_ddgs_and_keeps_our_ranking_and_sanitizing(self, monkeypatch):
        import server.web_search as ws

        class FakeDDGS:
            def __init__(self, *a, **k):
                pass

            def text(self, query, **kwargs):
                return [
                    {"title": "farm", "href": "https://w3schools.com/x",
                     "body": "content farm"},
                    {"title": "gh", "href": "https://github.com/a/b",
                     "body": "real​source"},
                ]

        import ddgs as ddgs_mod
        monkeypatch.setattr(ddgs_mod, "DDGS", FakeDDGS)

        out = ws.web_search("anything", max_results=2)
        assert out["error"] is None
        assert out["results"], out
        # Source ranking still ours: GitHub above the content farm.
        assert "github.com" in out["results"][0]["url"]
        # Sanitizing still ours: the zero width space is gone.
        assert "​" not in out["results"][1]["snippet"]

    def test_an_empty_query_short_circuits(self):
        import server.web_search as ws

        assert ws.web_search("")["error"]
        assert ws.web_search("   ")["error"]

    def test_a_transport_failure_degrades_rather_than_raises(self, monkeypatch):
        import ddgs as ddgs_mod
        import server.web_search as ws

        class Boom:
            def __init__(self, *a, **k):
                pass

            def text(self, *a, **k):
                raise RuntimeError("ratelimited")

        monkeypatch.setattr(ddgs_mod, "DDGS", Boom)
        out = ws.web_search("x")
        assert out["results"] == []
        assert "ratelimited" in out["error"]

    def test_the_hand_rolled_scraper_is_gone(self):
        import server.web_search as ws

        for dead in ("_web_search_html", "_extract_redirect_target"):
            assert not hasattr(ws, dead), f"{dead} survived the swap"
        # Check the CODE, not the prose. The docstring names the removed
        # scraper on purpose so nobody reintroduces it.
        source = Path(ws.__file__).read_text(encoding="utf-8")
        code = "\n".join(
            line for line in source.splitlines()
            if not line.lstrip().startswith("#")
        )
        for dead in ("result__snippet", "html.duckduckgo.com", "api.duckduckgo.com"):
            assert f'"{dead}' not in code and f"'{dead}" not in code, dead
