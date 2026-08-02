"""Attack A (round 4 brief), bullet 1: does one gapped project in a
multi-source search suppress the web fallback for an UNRELATED, fully
indexed project in the same request?

It used to. ``coverage_gaps = graph_meta.get("stale_projects") or []`` is
computed once over the whole request, and ``_web_fallback`` withheld the
fallback whenever that list was non-empty -- with no check for whether the
gapped project was the one that produced the thin result.
``stale_projects`` is populated per project source inside ``search.search()``
(search.py ``_check_index_before_search``, called once per ``project:``
source), so a request naming two independent projects gets one combined
list, and the old check could not tell "the low-scoring source is the gapped
one" from "the low-scoring source is a totally different, fully-indexed
project that happens to share this one HTTP request with a gapped one".

The suppression is now scoped to the request's evidence: it fires only when
NO project source searched a complete index, because only then is there no
sound negative result to fall back from. These tests pin both sides of that
line -- a complete source in the request keeps its fallback, and a request
where every project source is gapped still suppresses.

This drives the real ``handle_search`` (not a pasted copy of its
condition), same harness as
test_incomplete_index_web_fallback_interaction.py.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, "C:/Development/ClaudeBoost/clean-rag")

import server.app as app_mod


class StubEmbedder:
    """Signed hashed bag-of-words embedder -- see
    test_incomplete_index_web_fallback_interaction.py for why a fixed-vector
    stub cannot reproduce a low score."""
    model_name = "stub-embedder"

    _DIM = 4096

    def _vec(self, text: str) -> list[float]:
        import hashlib
        import math

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
    def __init__(self, embedder):
        self._embedder = embedder

    def get(self, _model_name):
        return self._embedder


class _FakeRequest:
    def __init__(self, payload: dict):
        self._payload = payload

    async def json(self) -> dict:
        return self._payload


# Shares no tokens with either project's indexed vocabulary, so both projects
# score below DEFAULT_MIN_SCORE and the combined result set is empty -- the
# same "genuinely absent" shape test_complete_index_still_gets_the_web_fallback
# uses to prove the fallback fires for a complete project on its own.
_ABSENT_FROM_BOTH_CORPORA = "volcanic eruption seismograph tectonic plate boundary"


def _make_project(root: Path, n_files: int, seed: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for f in range(n_files):
        body = "\n".join(
            f'''
def {seed}_handler_{f}_{i}(payload, retries=3):
    """Process one payload and return a normalised record."""
    total = 0
    for index, item in enumerate(payload.get("items", [])):
        if item.get("skip"):
            continue
        total += int(item.get("amount", 0)) * (index + 1)
    if total > 1000 and retries > 0:
        return {seed}_handler_{f}_{i}({{"items": []}}, retries - 1)
    return {{"total": total, "count": len(payload.get("items", []))}}
'''
            for i in range(12)
        )
        (root / f"module_{f:02d}.py").write_text(body, encoding="utf-8")
    return root


@pytest.fixture
def rig(tmp_path, monkeypatch):
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
            project = _make_project(tmp_path / name, n_files=n_files, seed=name)
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
            *_, manifest_path = indexing._project_paths(str(project))
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            raw["__model_id__"] = model_id
            manifest_path.write_text(json.dumps(raw), encoding="utf-8")

        @staticmethod
        def search(projects: list[Path], query: str = _ABSENT_FROM_BOTH_CORPORA) -> dict:
            return Rig.search_sources([f"project:{p}" for p in projects], query)

        @staticmethod
        def search_sources(sources: list[str], query: str = _ABSENT_FROM_BOTH_CORPORA) -> dict:
            """Raw source specifiers, for the cases that are not `project:`."""
            response = app_mod.asyncio.run(
                app_mod.handle_search(
                    _FakeRequest({
                        "query": query,
                        "sources": sources,
                        "mode": "vector",
                        # DEFAULT_MIN_SCORE (0.5) is the real default and is
                        # inclusive (store.py:402 `score >= min_score`), so an
                        # exactly-orthogonal chunk (cos_sim==0, score==0.5)
                        # can pass it by chance depending on the exact
                        # per-function seed text. A hair above 0.5 keeps this
                        # test about the suppression logic, not about tuning
                        # a stub embedder's hash collisions.
                        "min_score": 0.55,
                    })
                )
            )
            return json.loads(response.body.decode("utf-8"))

    return Rig


def test_gapped_project_does_not_suppress_fallback_for_an_unrelated_complete_project(rig):
    """The finding, now the assertion: an unrelated gapped project in the same
    multi-source request must NOT kill the web fallback for a fully-indexed
    project whose own absent result is genuine, independently-established
    evidence.

    Control: test_control_complete_alone_gets_the_fallback below proves the
    SAME complete project, searched alone with the SAME query, gets the real
    web fallback. The only thing that changes here is the presence of a
    second, unrelated, gapped source in the request, and that must not change
    the answer.
    """
    complete_project, complete_result = rig.index("complete_service", n_files=8)
    assert complete_result["files_indexed"] == 8
    rig.set_recorded_model(complete_project, StubEmbedder.model_name)

    gapped_project, gapped_result = rig.index("unrelated_gapped_service", n_files=8, abort_after=1)
    assert gapped_result["files_indexed"] == 1, "test setup: abort must have fired after file 1"
    rig.set_recorded_model(gapped_project, StubEmbedder.model_name)

    body = rig.search([complete_project, gapped_project])

    # Precondition: this really is the "genuinely absent" shape, not a
    # coverage artifact of the complete project itself.
    assert body["results"] == [], f"setup expectation: no local hits, got {body['results']}"

    # The gap is still reported, unchanged: the fix scopes what the gap
    # suppresses, it does not stop reporting the gap.
    stale = body["stale_projects"]
    assert len(stale) == 1, stale
    assert stale[0]["project"] == str(gapped_project), (
        "the complete project must not appear in stale_projects; only the "
        "gapped one caused this entry"
    )

    # THE FIX: the complete project searched its whole tree and found nothing,
    # which is real evidence of absence, and the unrelated gapped source does
    # not retract it.
    assert rig.web_search_calls == [_ABSENT_FROM_BOTH_CORPORA], (
        "the web fallback was withheld from the whole request because an "
        "unrelated project happened to be gapped, even though a fully indexed "
        "project in the same request genuinely searched and found nothing"
    )
    assert body["fallback_triggered"] is True
    assert body["web_search_results"]
    assert "web_search_suppressed" not in body, (
        "suppression and results are mutually exclusive; the fallback ran"
    )


def test_control_complete_alone_gets_the_fallback(rig):
    """Same complete project, same query, searched ALONE: the fallback runs.
    This isolates that the suppression above was caused purely by the
    presence of the second, unrelated, gapped source in the request -- not
    by anything about the complete project's own coverage."""
    complete_project, complete_result = rig.index("complete_service", n_files=8)
    assert complete_result["files_indexed"] == 8
    rig.set_recorded_model(complete_project, StubEmbedder.model_name)

    body = rig.search([complete_project])

    assert body["results"] == []
    assert "stale_projects" not in body
    assert rig.web_search_calls == [_ABSENT_FROM_BOTH_CORPORA], (
        "control failed: the complete project alone should get the real "
        "web fallback, which is the baseline this test compares against"
    )
    assert body["fallback_triggered"] is True
    assert "web_search_suppressed" not in body


def test_all_sources_gapped_still_suppresses_the_fallback(rig):
    """The other edge of the scoping, and the one that stops the fix from
    being a quiet removal of the suppression: when EVERY project source in the
    request is gapped there is no sound negative result anywhere in it, so the
    fallback stays withheld exactly as it does for a single gapped project
    searched alone."""
    first, first_result = rig.index("gapped_one", n_files=8, abort_after=1)
    assert first_result["files_indexed"] == 1
    rig.set_recorded_model(first, StubEmbedder.model_name)

    second, second_result = rig.index("gapped_two", n_files=8, abort_after=1)
    assert second_result["files_indexed"] == 1
    rig.set_recorded_model(second, StubEmbedder.model_name)

    body = rig.search([first, second])

    assert body["results"] == []
    assert sorted(entry["project"] for entry in body["stale_projects"]) == sorted(
        [str(first), str(second)]
    )
    assert rig.web_search_calls == [], (
        "no project source in this request searched a complete index, so "
        "nothing established that the code is absent"
    )
    assert body["fallback_triggered"] is False
    assert "web_search_results" not in body
    assert body["web_search_suppressed"]["reason"] == "index_coverage_unverified"
    assert sorted(body["web_search_suppressed"]["projects"]) == sorted(
        [str(first), str(second)]
    )


def test_docs_only_search_is_unaffected(rig):
    """A request with no project source at all must not be read as "every
    project source was gapped". Only a recorded coverage gap suppresses; a
    docs: source records none, so the thin result still gets its fallback."""
    body = rig.search_sources(["docs:python"])

    assert body["results"] == []
    assert "stale_projects" not in body
    assert rig.web_search_calls == [_ABSENT_FROM_BOTH_CORPORA]
    assert body["fallback_triggered"] is True
    assert "web_search_suppressed" not in body


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
