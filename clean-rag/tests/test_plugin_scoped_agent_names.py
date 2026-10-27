"""A plugin agent arrives as "claudeboost:bad-cop"; hooks must store the bare name."""

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HOOKS = REPO / "clean-rag" / "hooks"


def _load(name: str, path: Path):
    sys.path.insert(0, str(HOOKS))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def verifier_record():
    return _load("_scoped_verifier_record", HOOKS / "verifier-record.py")


@pytest.fixture(scope="module")
def research_record():
    return _load("_scoped_research_record", HOOKS / "research-record.py")


@pytest.mark.parametrize("raw, bare", [
    ("claudeboost:bad-cop", "bad-cop"),
    ("claudeboost:good-cop", "good-cop"),
    ("bad-cop", "bad-cop"),
    ("", ""),
])
def test_verifier_record_strips_the_plugin_prefix_from_a_task_payload(verifier_record, raw, bare):
    payload = {"tool_name": "Agent", "tool_input": {"subagent_type": raw}}
    assert verifier_record._agent_type(payload) == bare


def test_verifier_record_strips_the_prefix_on_a_subagent_stop_payload(verifier_record):
    payload = {"agent_type": "claudeboost:bad-cop", "agent_id": "x"}
    name = verifier_record._agent_type(payload)
    assert name == "bad-cop"
    assert name in verifier_record.VERIFIER_AGENTS


def test_a_scoped_good_cop_is_a_verifier(verifier_record):
    payload = {"tool_input": {"subagent_type": "claudeboost:good-cop"}}
    assert verifier_record._agent_type(payload) in verifier_record.VERIFIER_AGENTS


@pytest.mark.parametrize("raw, bare", [
    ("claudeboost:swiper", "swiper"),
    ("claudeboost:researcher", "researcher"),
    ("swiper", "swiper"),
    ("", ""),
])
def test_research_record_strips_the_plugin_prefix(research_record, raw, bare):
    payload = {"tool_name": "Agent", "tool_input": {"subagent_type": raw}}
    assert research_record._agent_type(payload) == bare


def test_a_scoped_research_agent_counts_for_the_gate(research_record):
    payload = {"tool_input": {"subagent_type": "claudeboost:swiper"}}
    assert research_record._agent_type(payload) in research_record.RESEARCH_AGENTS


def test_a_scoped_non_research_agent_still_does_not_count(research_record):
    payload = {"tool_input": {"subagent_type": "claudeboost:research-agent"}}
    assert research_record._agent_type(payload) not in research_record.RESEARCH_AGENTS
