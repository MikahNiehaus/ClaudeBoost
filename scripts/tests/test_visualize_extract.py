"""
Tests for scripts/visualize-extract.py — ClaudeBoost self-map extractor.

Tests the module functions directly via import, plus CLI invocation.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from helpers import run_script

# We import the functions directly by loading the module
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "visualize_extract", SCRIPTS_DIR / "visualize-extract.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

extract_agents = _mod.extract_agents
build_agent_columns = _mod.build_agent_columns
count_layer_cards = _mod.count_layer_cards
build_graph = _mod.build_graph


class TestExtractAgents:
    def test_empty_agents_dir(self, tmp_path):
        result = extract_agents(tmp_path)
        assert result == []

    def test_no_agents_dir(self, tmp_path):
        result = extract_agents(tmp_path / "nonexistent")
        assert result == []

    def test_skips_underscore_files(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "_orchestrator.xml").write_text("<agent-definition name='_o'/>", encoding="utf-8")
        result = extract_agents(tmp_path)
        assert len(result) == 0

    def test_parses_valid_agent(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        xml = '<agent-definition name="test-agent"><role>Tester</role><goal>Write tests</goal></agent-definition>'
        (agents_dir / "test-agent.xml").write_text(xml, encoding="utf-8")
        result = extract_agents(tmp_path)
        assert len(result) == 1
        assert result[0]["id"] == "test-agent"
        assert result[0]["title"] == "test-agent"
        assert "Tester" in result[0]["subtitle"]

    def test_opus_agent_gets_badge(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        xml = '<agent-definition name="architect-agent"><role>Architect</role><goal>Design</goal></agent-definition>'
        (agents_dir / "architect-agent.xml").write_text(xml, encoding="utf-8")
        result = extract_agents(tmp_path)
        assert result[0].get("badge") == "Opus"

    def test_skips_invalid_xml(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "broken.xml").write_text("NOT XML <<<<", encoding="utf-8")
        result = extract_agents(tmp_path)
        assert len(result) == 0

    def test_agent_without_role_or_goal(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        xml = '<agent-definition name="bare-agent"></agent-definition>'
        (agents_dir / "bare-agent.xml").write_text(xml, encoding="utf-8")
        result = extract_agents(tmp_path)
        assert len(result) == 1
        assert result[0]["id"] == "bare-agent"


class TestBuildAgentColumns:
    def _make_card(self, name, badge=None):
        c = {"id": name, "title": name, "subtitle": "", "detail": ""}
        if badge:
            c["badge"] = badge
        return c

    def test_empty_input(self):
        result = build_agent_columns([])
        assert len(result) == 1
        assert result[0]["label"] == "Agents"

    def test_opus_agents_in_first_column(self):
        cards = [self._make_card("architect-agent"), self._make_card("test-agent")]
        result = build_agent_columns(cards)
        opus_col = next((c for c in result if "Opus" in c["label"]), None)
        assert opus_col is not None
        assert any(c["id"] == "architect-agent" for c in opus_col["cards"])

    def test_quality_agents_in_quality_column(self):
        cards = [self._make_card("security-agent"), self._make_card("test-agent")]
        result = build_agent_columns(cards)
        quality_col = next((c for c in result if "Quality" in c["label"]), None)
        assert quality_col is not None


class TestCountLayerCards:
    def test_cards_layer(self):
        layer = {"cards": [{"id": "a"}, {"id": "b"}]}
        assert _mod.count_layer_cards(layer) == 2

    def test_columns_layer(self):
        layer = {"columns": [
            {"cards": [{"id": "a"}, {"id": "b"}]},
            {"cards": [{"id": "c"}]},
        ]}
        assert _mod.count_layer_cards(layer) == 3

    def test_exchanges_layer(self):
        layer = {"exchanges": [{"left": {}, "right": {}}]}
        assert _mod.count_layer_cards(layer) == 2

    def test_decisions_layer(self):
        layer = {"decisions": [{"question": {}, "outcomes": [{"id": "a"}, {"id": "b"}]}]}
        assert _mod.count_layer_cards(layer) == 3

    def test_unknown_layer(self):
        layer = {"other": "stuff"}
        assert _mod.count_layer_cards(layer) == 0


class TestBuildGraph:
    def test_returns_dict_with_required_keys(self, tmp_path):
        graph = build_graph(tmp_path)
        assert "project" in graph
        assert "layers" in graph
        assert "side_rails" in graph
        assert "title" in graph

    def test_has_correct_layer_count(self, tmp_path):
        graph = build_graph(tmp_path)
        assert len(graph["layers"]) == 6

    def test_with_agents_dir(self, tmp_path):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        xml = '<agent-definition name="my-agent"><role>Worker</role><goal>Work</goal></agent-definition>'
        (agents_dir / "my-agent.xml").write_text(xml, encoding="utf-8")
        graph = build_graph(tmp_path)
        # Should include the agent in the agents layer
        agents_layer = next((l for l in graph["layers"] if l["id"] == "agents"), None)
        assert agents_layer is not None


class TestVisualizeCLI:
    def test_runs_and_creates_output(self, tmp_path):
        result = run_script("visualize-extract.py", args=[str(tmp_path), str(tmp_path / "graph.json")])
        assert result.returncode == 0
        assert (tmp_path / "graph.json").exists()

    def test_output_is_valid_json(self, tmp_path):
        run_script("visualize-extract.py", args=[str(tmp_path), str(tmp_path / "graph.json")])
        data = json.loads((tmp_path / "graph.json").read_text(encoding="utf-8"))
        assert "layers" in data
        assert "project" in data

    def test_prints_summary_to_stdout(self, tmp_path):
        result = run_script("visualize-extract.py", args=[str(tmp_path), str(tmp_path / "out.json")])
        output = result.stdout.decode("utf-8", errors="replace")
        assert "nodes" in output or "Extracted" in output
