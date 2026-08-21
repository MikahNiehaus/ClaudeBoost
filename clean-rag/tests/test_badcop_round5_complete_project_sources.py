"""bad-cop round 5 adversarial re-check of `_complete_project_sources` and the
`_web_fallback` condition change in server/app.py.

Attack surface from the brief:
  A. path matching between `sources` and `stale_projects[].project` (case,
     trailing slash, forward/back slash, relative vs absolute, dedup with one
     gapped duplicate, malformed/edge inputs).
  B. the condition itself (three required behaviours) plus the docs + gapped
     project mixed case, which the existing suite does not cover.

These call `_complete_project_sources` directly (unit level, matches the
function's own contract) and, for the mixed docs+gapped case, drive the real
`handle_search` the same way test_mixed_source_over_suppression.py does.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server.app as app_mod
from server.app import _complete_project_sources


# --- A: path matching / dedup / malformed inputs -----------------------

def test_exact_match_is_complete():
    gaps = []
    assert _complete_project_sources(["project:C:/prj/foo"], gaps) == ["C:/prj/foo"]


def test_exact_match_gapped_is_excluded():
    gaps = [{"project": "C:/prj/foo", "reason": "x", "served": False}]
    assert _complete_project_sources(["project:C:/prj/foo"], gaps) == []


def test_case_difference_does_not_launder_a_gap_to_complete():
    """Windows paths are case-insensitive on disk but the gap is recorded as
    the exact `source[8:]` string. If a caller's `sources` casing differs
    from what search.search recorded (e.g. a different call built the path
    with different casing), a case-sensitive compare here means the gapped
    project silently counts as complete -- exactly the round 3 bug, just
    reintroduced through a normalisation mismatch instead of the old
    unconditional check."""
    gaps = [{"project": "C:/prj/Foo", "reason": "x", "served": False}]
    result = _complete_project_sources(["project:C:/prj/foo"], gaps)
    # If this is ["C:/prj/foo"], the gapped project (recorded as Foo) is
    # being counted as a *different*, complete project -- not laundering in
    # this exact scenario (different literal strings = different projects by
    # design), but it proves the match is a literal string compare with zero
    # tolerance, which is what the next tests stress on purpose.
    assert result == ["C:/prj/foo"], (
        "documents actual behaviour: case is NOT normalised, so a caller "
        "that varies casing between the search call and its own bookkeeping "
        "gets a different answer than one that doesn't"
    )


def test_trailing_slash_mismatch_is_not_normalised():
    """A gap recorded without a trailing slash must not be matched by a
    source with one, or vice versa -- proving there is no accidental
    normalisation that could also erase a real mismatch the other, dangerous
    direction (gapped counted as complete)."""
    gaps = [{"project": "C:/prj/foo", "reason": "x", "served": False}]
    result = _complete_project_sources(["project:C:/prj/foo/"], gaps)
    assert result == ["C:/prj/foo/"], (
        "a trailing-slash source is NOT recognised as the same gapped "
        "project -- it is counted complete. This is only safe because "
        "search.py's own source[8:] slice is exact too, so the SAME source "
        "string that produced the gap is what must be passed to "
        "_complete_project_sources; if any call site normalises sources "
        "between the two (e.g. adding a trailing slash) the gap silently "
        "stops applying."
    )


def test_duplicate_source_once_gapped_is_not_counted_complete():
    """The same project listed twice in sources, one 'copy' effectively
    gapped: dedup must not let the un-gapped mention win."""
    gaps = [{"project": "C:/prj/foo", "reason": "x", "served": False}]
    result = _complete_project_sources(
        ["project:C:/prj/foo", "project:C:/prj/foo"], gaps
    )
    assert result == [], (
        "duplicate source entries for a gapped project must both be excluded"
    )


def test_bare_project_prefix_is_dropped_not_counted_complete():
    gaps = []
    assert _complete_project_sources(["project:"], gaps) == []


def test_bare_project_prefix_with_whitespace_is_dropped():
    gaps = []
    assert _complete_project_sources(["project:   "], gaps) == []


def test_non_string_source_is_dropped():
    gaps = []
    assert _complete_project_sources([123, None, {"a": 1}, ["project:x"]], gaps) == []


def test_stale_entry_missing_project_key_does_not_crash_and_does_not_match():
    gaps = [{"reason": "x", "served": False}]  # no "project" key at all
    result = _complete_project_sources(["project:C:/prj/foo"], gaps)
    assert result == ["C:/prj/foo"], (
        "a gap entry with no 'project' key must not accidentally match a "
        "real source path (gap.get('project') is None, source path is never "
        "None, so no false match) -- confirmed by actual behaviour"
    )


def test_bare_project_source_recorded_as_gap_with_empty_string_does_not_leak():
    """good-cop's empirical claim: a bare 'project:' source is itself
    recorded as a gap with project=''. Confirm the empty-string gap entry
    does not somehow get treated as a 'complete' empty-string project."""
    gaps = [{"project": "", "reason": "x", "served": False}]
    result = _complete_project_sources(["project:"], gaps)
    assert result == [], "bare project: must never appear as a complete source"


def test_relative_vs_absolute_path_are_different_strings():
    """A source built with a relative path and a gap recorded with the
    resolved absolute path (or vice versa) do not match -- proving there is
    no path resolution here at all. This is the safe direction (a real gap
    stays a gap under a different string), but it also means a caller that
    is inconsistent between what it puts in `sources` and what search.py
    ultimately records get an under-count of complete projects, never an
    over-count "the gap is laundered away" -- checked directly."""
    gaps = [{"project": "/abs/prj/foo", "reason": "x", "served": False}]
    result = _complete_project_sources(["project:../prj/foo"], gaps)
    assert result == ["../prj/foo"], (
        "relative and absolute strings never collide, so this can only ever "
        "under-count complete sources (safe direction), never wrongly launder "
        "a gap into a complete project"
    )


def test_coverage_gaps_entries_are_dicts_get_call_on_non_dict_raises():
    """coverage_gaps not shaped as list[dict] -- confirms the function's
    actual behaviour on a malformed gap entry (a plain string instead of a
    dict), since callers only ever pass what search.py produces (always
    dicts), but the type hint promises dict and nothing enforces it."""
    with pytest.raises(AttributeError):
        _complete_project_sources(["project:C:/prj/foo"], ["not-a-dict"])


def test_empty_sources_and_empty_gaps():
    assert _complete_project_sources([], []) == []


def test_multiple_distinct_complete_projects_all_kept():
    gaps = []
    result = _complete_project_sources(
        ["project:C:/a", "project:C:/b", "project:C:/a"], gaps
    )
    assert sorted(result) == ["C:/a", "C:/b"]


# --- B: the mixed docs: + gapped project: case, via the real handler ---

class StubEmbedder:
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


_ABSENT = "volcanic eruption seismograph tectonic plate boundary"


def _make_project(root: Path, n_files: int, seed: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for f in range(n_files):
        body = "\n".join(
            f'''
def {seed}_handler_{f}_{i}(payload, retries=3):
    total = 0
    for index, item in enumerate(payload.get("items", [])):
        if item.get("skip"):
            continue
        total += int(item.get("amount", 0)) * (index + 1)
    return {{"total": total}}
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
    monkeypatch.setattr(app_mod, "_doc_embedder", None)  # no docs: source used for real search

    calls: list[str] = []

    def spy_web_search(query, **_kwargs):
        calls.append(query)
        return {"results": [{"title": "unrelated", "url": "https://example.test/x"}]}

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
        def search_sources(sources: list[str], query: str = _ABSENT) -> dict:
            response = app_mod.asyncio.run(
                app_mod.handle_search(
                    _FakeRequest({
                        "query": query,
                        "sources": sources,
                        "mode": "vector",
                        "min_score": 0.55,
                    })
                )
            )
            return json.loads(response.body.decode("utf-8"))

    return Rig


def test_docs_plus_gapped_project_mix_suppresses_fallback(rig):
    """The brief's explicit open question: docs: + one gapped project:, no
    complete project source at all. coverage_gaps is non-empty (the gapped
    project), complete_projects is empty (docs: never appears in
    stale_projects and the only project: source is gapped) -> condition is
    True -> suppressed.

    This documents that a docs: source's own genuine "found nothing" gets
    swept into the same suppression as the gapped project:, even though the
    docs: source may have searched in full and found nothing on its own
    account. That is a real narrowing of the fallback beyond what the
    docstring in _web_fallback claims ("ONE source that genuinely searched
    and found nothing" is enough) -- docs: sources are never counted as that
    one source because _complete_project_sources only ever looks at
    `project:` prefixed entries, so a docs-source's real completeness is
    invisible to the condition.
    """
    gapped_project, gapped_result = rig.index("mixed_gapped", n_files=8, abort_after=1)
    assert gapped_result["files_indexed"] == 1
    rig.set_recorded_model(gapped_project, StubEmbedder.model_name)

    body = rig.search_sources(["docs:python", f"project:{gapped_project}"])

    assert body["results"] == []
    assert len(body["stale_projects"]) == 1
    assert body["stale_projects"][0]["project"] == str(gapped_project)
    assert rig.web_search_calls == [], (
        "the docs: source's own completeness is invisible to "
        "_complete_project_sources (it only inspects project: sources), so "
        "a docs+gapped-project mix suppresses the fallback exactly like an "
        "all-gapped project-only request -- even though the docs: source may "
        "have genuinely searched its own topic in full"
    )
    assert body["fallback_triggered"] is False
    assert body["web_search_suppressed"]["reason"] == "index_coverage_unverified"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
