"""Does a thin result set caused by a broken index get answered with the web?

Attack B from bad-cop's round 3 brief: an incomplete but served index
(served=True in stale_projects) returns fewer hits than the project really has,
and app.py's web search fallback used to fire on that thinness with no
reference to graph_meta at all. The response then carried unrelated web content
next to a stale_projects entry that said, in the field nobody reads, "a missing
hit does not mean the code is absent".

bad-cop's original version of this file evaluated a copy of app.py's trigger
condition, pasted into the test. That version passes whether app.py is fixed or
not, because the copy cannot change when the original does. These tests drive
the real handle_search and assert the response body it actually returns.

The setup harness (a real 8 file project indexed with an abort after file 1) is
bad-cop's and is kept verbatim, because it is what makes the incompleteness
real rather than mocked.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server.app as app_mod


class StubEmbedder:
    """A deterministic, content sensitive stand-in for the real embedder.

    A fixed vector for every input (the pattern the other tests in this file
    use) makes cosine similarity 1.0 regardless of query content, which can
    never produce the low top_score half of app.py's fallback condition. This
    hashes each whitespace token into one of 32 buckets, sums, and normalises,
    so unrelated text lands far apart and near-identical text lands close,
    without needing the real (slow, large) sentence-transformers model.
    """
    model_name = "stub-embedder"

    _DIM = 4096

    def _vec(self, text: str) -> list[float]:
        import hashlib
        import math

        # Signed hashing (a bucket AND a +1/-1 sign per token), not a plain
        # word count. Unsigned counts can never go negative, which floors
        # cosine similarity for genuinely unrelated text at 0 (score 0.5 under
        # the (1+sim)/2 convention) instead of letting it scatter around 0
        # the way a real transformer embedding's unrelated-text similarity
        # actually does. That floor was hiding the low score half of app.py's
        # fallback condition entirely.
        v = [0.0] * self._DIM
        for tok in text.lower().split():
            h = int(hashlib.sha256(tok.encode("utf-8")).hexdigest(), 16)
            bucket = h % self._DIM
            sign = 1.0 if (h // self._DIM) % 2 == 0 else -1.0
            v[bucket] += sign
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


class _OneModelCache:
    """Stands in for ModelCache: handle_search only ever calls .get()."""

    def __init__(self, embedder):
        self._embedder = embedder

    def get(self, _model_name):
        return self._embedder


class _FakeRequest:
    def __init__(self, payload: dict):
        self._payload = payload

    async def json(self) -> dict:
        return self._payload


# Vocabulary that shares no tokens at all with the indexed source (which is all
# "def handler_N_i(payload, retries=3): ... items ... amount ..."). With the
# hashed bag-of-words stub embedder this scores every indexed chunk below
# DEFAULT_MIN_SCORE (0.5), which is the real default handle_search applies, so
# the result set comes back empty. That is the same shape a genuine "the code
# is not there" query produces: the whole point is that the fallback decision
# cannot tell the two apart on thinness alone.
_ABSENT_FROM_THE_CORPUS = "volcanic eruption seismograph tectonic plate boundary"


def _make_project(root: Path, n_files: int) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for f in range(n_files):
        body = "\n".join(
            f'''
def handler_{f}_{i}(payload, retries=3):
    """Process one payload and return a normalised record."""
    total = 0
    for index, item in enumerate(payload.get("items", [])):
        if item.get("skip"):
            continue
        total += int(item.get("amount", 0)) * (index + 1)
    if total > 1000 and retries > 0:
        return handler_{f}_{i}({{"items": []}}, retries - 1)
    return {{"total": total, "count": len(payload.get("items", []))}}
'''
            for i in range(12)
        )
        (root / f"module_{f:02d}.py").write_text(body, encoding="utf-8")
    return root


@pytest.fixture
def rig(tmp_path, monkeypatch):
    """A real indexed project plus a handle_search wired to it, not to disk."""
    from server import indexing, search as search_mod, web_search as web_search_mod

    monkeypatch.setattr(indexing, "DATABASES_DIR", tmp_path / "databases")
    monkeypatch.setattr(indexing, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(search_mod, "DATABASES_DIR", tmp_path / "databases")
    monkeypatch.setattr(app_mod, "_SEARCH_LOG_PATH", tmp_path / "search-log.jsonl")
    monkeypatch.setattr(app_mod, "_model_cache", _OneModelCache(StubEmbedder()))
    monkeypatch.setattr(app_mod, "WEB_SEARCH_ENABLED", True)

    calls: list[str] = []

    def spy_web_search(query, **_kwargs):
        calls.append(query)
        return {"results": [{"title": "unrelated web page", "url": "https://example.test/x"}]}

    monkeypatch.setattr(web_search_mod, "web_search", spy_web_search)

    class Rig:
        web_search_calls = calls

        @staticmethod
        def index(name: str, n_files: int = 8, abort_after: int | None = None):
            project = _make_project(tmp_path / name, n_files=n_files)
            seen = {"n": 0}

            def should_abort():
                seen["n"] += 1
                if abort_after is None or seen["n"] <= abort_after:
                    return None
                return "CPU 95% (limit 80%)"

            result = indexing.index_project(
                str(project), StubEmbedder(), force=True, should_abort=should_abort
            )
            return project, result

        @staticmethod
        def set_recorded_model(project: Path, model_id: str) -> None:
            """Rewrite the manifest's provenance stamp.

            index_project records the model id from the embedder it was handed;
            setting it explicitly is how a test picks "matches the query
            embedder" or "does not" without needing two real models.
            """
            *_, manifest_path = indexing._project_paths(str(project))
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            raw["__model_id__"] = model_id
            manifest_path.write_text(json.dumps(raw), encoding="utf-8")

        @staticmethod
        def search(project: Path) -> dict:
            response = app_mod.asyncio.run(
                app_mod.handle_search(
                    _FakeRequest({
                        "query": _ABSENT_FROM_THE_CORPUS,
                        "sources": [f"project:{project}"],
                        "mode": "vector",
                    })
                )
            )
            return json.loads(response.body.decode("utf-8"))

    return Rig


def test_incomplete_index_does_not_get_answered_with_web_content(rig):
    """The finding: a coverage gap must not be served as "not in this codebase".

    8 files, abort after 1: the most extreme, but entirely realistic,
    incompleteness (a server killed seconds into a sweep). The query asks for
    vocabulary none of the surviving chunks match, so the result set is empty
    for a reason that is entirely about coverage.
    """
    project, result = rig.index("partial", n_files=8, abort_after=1)
    assert result["files_indexed"] == 1, "test setup: abort must have fired after file 1"
    rig.set_recorded_model(project, StubEmbedder.model_name)

    body = rig.search(project)

    # Precondition, not the finding: the result set really is thin, so this is
    # a case the old unconditional trigger would have web searched. Without
    # this the rest of the test could pass on a path that was never at risk.
    assert body["results"] == [], f"setup expectation: expected no local hits, got {body['results']}"

    stale = body["stale_projects"]
    assert stale[0]["served"] is True, stale

    assert rig.web_search_calls == [], (
        "the web search ran for a query whose empty result set is explained by "
        "an unfinished index; the code may be in one of the 7 files the run "
        "never reached"
    )
    assert body["fallback_triggered"] is False
    assert "web_search_results" not in body, (
        "a caller that surfaces web_search_results would present internet "
        "content as the answer to a question the local index was never asked "
        "in full"
    )
    assert body["web_search_suppressed"]["reason"] == "index_coverage_unverified"
    assert body["web_search_suppressed"]["projects"] == [str(project)]


def test_refused_index_does_not_get_answered_with_web_content(rig):
    """Same family, the other half: a project skipped for a provenance
    mismatch contributes zero results, which is even less evidence of absence
    than a partial index. served=False must suppress the fallback too."""
    project, _ = rig.index("mismatched", n_files=2)
    rig.set_recorded_model(project, "a-completely-different-model")

    body = rig.search(project)

    assert body["results"] == []
    assert body["stale_projects"][0]["served"] is False
    assert rig.web_search_calls == []
    assert body["fallback_triggered"] is False
    assert body["web_search_suppressed"]["reason"] == "index_coverage_unverified"


def test_complete_index_still_gets_the_web_fallback(rig):
    """The other side of the fix, and the one that stops it being a quiet
    feature removal: when the index really did cover the whole project, an
    empty result set IS evidence the code is not here, and the fallback is the
    right answer."""
    project, result = rig.index("complete", n_files=8)
    assert result["files_indexed"] == 8, "test setup: nothing should have aborted"
    rig.set_recorded_model(project, StubEmbedder.model_name)

    body = rig.search(project)

    assert body["results"] == [], "setup expectation: the query still matches nothing"
    assert "stale_projects" not in body, (
        f"a fully indexed project was flagged: {body.get('stale_projects')}"
    )
    assert rig.web_search_calls == [_ABSENT_FROM_THE_CORPUS]
    assert body["fallback_triggered"] is True
    assert body["web_search_results"]
    assert "web_search_suppressed" not in body


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
