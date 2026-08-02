"""Tests for the shared sweep unit.

Behavioral, not structural. The point of this module is that two drivers stop
drifting apart, so what matters is the ordering and grouping contract both rely
on, not how it happens to be spelled.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.reindex_unit import (  # noqa: E402
    Outcome,
    PlannedProject,
    model_groups,
    plan_sweep,
    read_registry,
)


def _registry(*entries):
    return {pid: e for pid, e in entries}


class TestPlanOrdering:
    def _plan(self, monkeypatch, tmp_path, projects):
        """projects: list of (name, model, files_indexed)."""
        reg = {}
        for name, model, n in projects:
            d = tmp_path / name
            d.mkdir(parents=True, exist_ok=True)
            reg[name] = {"project_path": str(d), "files_indexed": n}

        models = {str(tmp_path / name): model for name, model, _ in projects}
        monkeypatch.setattr(
            "server.reindex_unit.recorded_model", lambda p: models.get(str(Path(p)))
        )
        return plan_sweep(reg)

    def test_each_model_forms_one_contiguous_run(self, monkeypatch, tmp_path):
        """The whole reason the plan exists: never load a model twice."""
        plan = self._plan(monkeypatch, tmp_path, [
            ("a", "m1", 10), ("b", "m2", 10), ("c", "m1", 10), ("d", "m2", 10),
        ])
        seen_models = [p.model for p in plan]
        runs = [m for i, m in enumerate(seen_models) if i == 0 or seen_models[i - 1] != m]
        assert len(runs) == len(set(runs)), (
            f"a model group is split across the plan: {seen_models}"
        )

    def test_cheapest_group_runs_first(self, monkeypatch, tmp_path):
        """More projects searchable sooner, rather than vanishing into the
        biggest corpus first."""
        plan = self._plan(monkeypatch, tmp_path, [
            ("big1", "heavy", 5000), ("big2", "heavy", 5000), ("small", "light", 10),
        ])
        assert plan[0].model == "light"

    def test_smallest_first_within_a_group(self, monkeypatch, tmp_path):
        plan = self._plan(monkeypatch, tmp_path, [
            ("c", "m", 300), ("a", "m", 100), ("b", "m", 200),
        ])
        assert [p.size for p in plan] == [100, 200, 300]

    def test_missing_directory_is_dropped(self, monkeypatch, tmp_path):
        reg = {
            "gone": {"project_path": str(tmp_path / "does-not-exist"), "files_indexed": 5},
        }
        assert plan_sweep(reg) == []

    def test_missing_files_indexed_does_not_crash(self, monkeypatch, tmp_path):
        d = tmp_path / "fresh"
        d.mkdir()
        monkeypatch.setattr("server.reindex_unit.recorded_model", lambda p: "m")
        plan = plan_sweep({"fresh": {"project_path": str(d)}})
        assert len(plan) == 1
        assert plan[0].size == 0
        assert plan[0].size_is_estimate is True

    def test_non_dict_entries_are_ignored(self, tmp_path):
        assert plan_sweep({"junk": "not a dict"}) == []

    def test_empty_registry_is_empty_plan(self):
        assert plan_sweep({}) == []

    def test_ordering_is_deterministic(self, monkeypatch, tmp_path):
        """Same input, same order. A plan that reshuffles makes a resumable job
        redo work it already finished."""
        args = [("a", "m", 10), ("b", "m", 10), ("c", "m", 10)]
        first = [p.path for p in self._plan(monkeypatch, tmp_path, args)]
        second = [p.path for p in self._plan(monkeypatch, tmp_path, args)]
        assert first == second


class TestRebuildVsIncremental:
    def test_rebuild_groups_by_the_model_the_router_will_pick(self, monkeypatch, tmp_path):
        """A rebuild discards the index, so the recorded model is history.

        Grouping a rebuild by the recorded model put every project whose
        manifest predates provenance into one unknown bucket, which is the
        ungrouped thrash the plan exists to prevent.
        """
        d = tmp_path / "p"
        d.mkdir()
        reg = {"p": {"project_path": str(d), "files_indexed": 5}}

        monkeypatch.setattr("server.reindex_unit.recorded_model", lambda p: None)
        monkeypatch.setattr("server.reindex_unit.routed_model", lambda p: ("routed/model", 42))

        rebuild = plan_sweep(reg, for_rebuild=True)
        assert rebuild[0].model == "routed/model"
        assert rebuild[0].size == 42, "a rebuild should use the exact count from its own walk"
        assert rebuild[0].size_is_estimate is False

    def test_incremental_prefers_the_recorded_model(self, monkeypatch, tmp_path):
        """An incremental sweep adds vectors to an index that already exists, so
        it must use the model those vectors were built with."""
        d = tmp_path / "p"
        d.mkdir()
        reg = {"p": {"project_path": str(d), "files_indexed": 5}}

        monkeypatch.setattr("server.reindex_unit.recorded_model", lambda p: "recorded/model")
        monkeypatch.setattr(
            "server.reindex_unit.routed_model",
            lambda p: pytest.fail("incremental must not pay for a directory walk"),
        )
        plan = plan_sweep(reg)
        assert plan[0].model == "recorded/model"


class TestModelGroups:
    def test_groups_are_contiguous_runs(self):
        plan = [
            PlannedProject("1", "/a", "m1", 1),
            PlannedProject("2", "/b", "m1", 2),
            PlannedProject("3", "/c", "m2", 3),
        ]
        groups = model_groups(plan)
        assert [(m, len(v)) for m, v in groups] == [("m1", 2), ("m2", 1)]

    def test_unsorted_input_is_not_silently_merged(self):
        """groupby only groups CONSECUTIVE equal keys. On unsorted input this
        must produce separate runs rather than pretend they are one group."""
        plan = [
            PlannedProject("1", "/a", "m1", 1),
            PlannedProject("2", "/b", "m2", 2),
            PlannedProject("3", "/c", "m1", 3),
        ]
        assert [m for m, _ in model_groups(plan)] == ["m1", "m2", "m1"]

    def test_empty_plan(self):
        assert model_groups([]) == []


class TestOutcome:
    def test_outcomes_are_strings(self):
        """StrEnum, so it stays compatible with the string statuses used
        elsewhere in this package."""
        assert Outcome.COMPLETED == "completed"
        assert isinstance(Outcome.PAUSED, str)

    def test_pressure_and_error_are_distinct(self):
        """The batch driver retries one and not the other; one shared counter
        let a broken project burn the whole budget of a healthy waiting one."""
        assert Outcome.PAUSED != Outcome.ERRORED


class TestRegistryReader:
    def test_missing_file_is_empty(self, monkeypatch, tmp_path):
        monkeypatch.setattr("server.reindex_unit.STATE_DIR", tmp_path / "nope")
        assert read_registry() == {}

    def test_corrupt_json_is_empty_not_an_exception(self, monkeypatch, tmp_path):
        (tmp_path / "projects.json").write_text("{not json", encoding="utf-8")
        monkeypatch.setattr("server.reindex_unit.STATE_DIR", tmp_path)
        assert read_registry() == {}

    def test_reads_real_content(self, monkeypatch, tmp_path):
        (tmp_path / "projects.json").write_text(
            json.dumps({"x": {"project_path": "/tmp/x"}}), encoding="utf-8"
        )
        monkeypatch.setattr("server.reindex_unit.STATE_DIR", tmp_path)
        assert read_registry()["x"]["project_path"] == "/tmp/x"


class TestNoDrift:
    """The whole reason this module exists."""

    def test_auto_reindex_reuses_the_shared_helpers(self):
        from server import auto_reindex, reindex_unit

        assert auto_reindex._read_registry is reindex_unit.read_registry
        assert auto_reindex._release_project_resources is reindex_unit.release_project_resources

    def test_release_resolves_databases_dir_at_call_time(self, monkeypatch, tmp_path):
        """Binding DATABASES_DIR at import froze it, so eviction targeted a path
        nothing was cached under."""
        import server.config as cfg
        from server import reindex_unit

        seen = {}
        monkeypatch.setattr(cfg, "DATABASES_DIR", tmp_path / "relocated")
        monkeypatch.setattr(
            "server.store.ChromaStore.evict_cache",
            staticmethod(lambda p: seen.setdefault("path", p)),
        )
        reindex_unit.release_project_resources("somepid")
        assert "relocated" in seen.get("path", ""), (
            f"eviction used a stale DATABASES_DIR: {seen.get('path')!r}"
        )
