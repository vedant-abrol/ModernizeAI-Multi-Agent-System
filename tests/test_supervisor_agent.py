from __future__ import annotations

from typing import Any

import pytest

from app.agents.agent_graph import build_initial_agent_graph
from app.agents import supervisor_agent
from app.agents.supervisor_agent import run_supervisor_agent


def _state(**overrides: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "repo_metadata": {
            "indexed_file_paths": ["src/main/java/App.java"],
            "config_files": [],
            "dependency_files": [],
            "dependency_details": [],
            "build_tools": [],
            "controllers": [],
            "services": [],
            "test_files": [],
            "warnings": [],
        },
        "progress": [],
        "errors": [],
        "iteration_count": 0,
        "max_iterations": 10,
        "completed_agents": [],
        "skipped_agents": [],
        "agent_run_counts": {},
        "agent_decisions": [],
        "agent_messages": [],
        "agent_graph": build_initial_agent_graph(),
        "critic_findings": {},
    }
    state.update(overrides)
    return state


@pytest.fixture(autouse=True)
def deterministic_supervisor(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_optional_bedrock_json(
        system_prompt: str,
        payload: dict[str, Any],
        fallback: dict[str, Any],
        max_tokens: int = 1500,
    ) -> dict[str, Any]:
        result = dict(fallback)
        result["llm_status"] = "disabled"
        result["llm_provider"] = "deterministic"
        return result

    monkeypatch.setattr(supervisor_agent, "optional_bedrock_json", fake_optional_bedrock_json)


def test_supervisor_prioritizes_security_when_risk_signals_exist() -> None:
    state = _state(
        repo_metadata={
            "indexed_file_paths": ["src/main/resources/application.properties"],
            "config_files": [{"file": "src/main/resources/application.properties"}],
            "dependency_files": [],
            "dependency_details": [],
            "build_tools": [],
            "controllers": [],
            "services": [],
            "test_files": [],
            "warnings": [],
        }
    )

    result = run_supervisor_agent(state)

    assert result["next_agent"] == "security"
    assert result["agent_decisions"][0]["graph_label"] == "risk signals detected"
    assert result["agent_graph"]["edges"][-1]["target"] == "security"


def test_supervisor_skips_dependency_when_no_dependency_evidence_exists() -> None:
    result = run_supervisor_agent(_state())

    assert result["next_agent"] == "architecture"
    assert "dependency" in result["skipped_agents"]
    dependency_node = next(node for node in result["agent_graph"]["nodes"] if node["id"] == "dependency")
    assert dependency_node["status"] == "skipped"


def test_supervisor_routes_critic_rejection_back_to_modernization_once() -> None:
    state = _state(
        agent_run_counts={"modernization": 1, "critic": 1},
        completed_agents=["modernization", "critic"],
        critic_findings={
            "blocked_claims": [
                {
                    "claim": "Payment Service Candidate",
                    "reason": "Suggested boundary has no data ownership evidence.",
                    "action": "Remove from microservice boundary list.",
                }
            ]
        },
    )

    result = run_supervisor_agent(state)

    assert result["next_agent"] == "modernization"
    assert result["critic_approved"] is False
    assert result["agent_decisions"][0]["graph_label"] == "critic requested follow-up"


def test_supervisor_max_iterations_routes_to_report() -> None:
    result = run_supervisor_agent(_state(iteration_count=10, max_iterations=10))

    assert result["next_agent"] == "report"
    assert result["agent_decisions"][0]["graph_label"] == "max iterations reached"


def test_supervisor_enforces_max_iterations_over_llm_choice(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_optional_bedrock_json(
        system_prompt: str,
        payload: dict[str, Any],
        fallback: dict[str, Any],
        max_tokens: int = 1500,
    ) -> dict[str, Any]:
        return {
            "next_agent": "dependency",
            "rationale": "Run dependency analysis again.",
            "graph_label": "dependency evidence found",
            "evidence_gaps": [],
            "skipped_agents": [],
            "llm_status": "bedrock",
            "llm_provider": "Amazon Bedrock",
        }

    monkeypatch.setattr(supervisor_agent, "optional_bedrock_json", fake_optional_bedrock_json)

    result = run_supervisor_agent(_state(iteration_count=9, max_iterations=10))

    assert result["next_agent"] == "report"
    assert result["agent_decisions"][0]["graph_label"] == "max iterations reached"
    assert result["agent_decisions"][0]["llm_status"] == "policy_enforced"


def test_supervisor_rejects_unrequested_llm_specialist_rerun(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_optional_bedrock_json(
        system_prompt: str,
        payload: dict[str, Any],
        fallback: dict[str, Any],
        max_tokens: int = 1500,
    ) -> dict[str, Any]:
        return {
            "next_agent": "dependency",
            "rationale": "Dependency files still need review.",
            "graph_label": "dependency evidence found",
            "evidence_gaps": [],
            "skipped_agents": [],
            "llm_status": "bedrock",
            "llm_provider": "Amazon Bedrock",
        }

    monkeypatch.setattr(supervisor_agent, "optional_bedrock_json", fake_optional_bedrock_json)
    state = _state(
        repo_metadata={
            "indexed_file_paths": ["src/main/java/App.java"],
            "config_files": [],
            "dependency_files": [{"file": "pom.xml"}],
            "dependency_details": [{"file": "pom.xml"}],
            "build_tools": ["maven"],
            "controllers": [],
            "services": [],
            "test_files": [],
            "warnings": [],
        },
        completed_agents=["dependency"],
        agent_run_counts={"dependency": 1},
    )

    result = run_supervisor_agent(state)

    assert result["next_agent"] == "architecture"
    assert result["agent_decisions"][0]["graph_label"] == "structure evidence found"
    assert result["agent_decisions"][0]["llm_status"] == "policy_enforced"


def test_supervisor_rejects_premature_llm_report(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_optional_bedrock_json(
        system_prompt: str,
        payload: dict[str, Any],
        fallback: dict[str, Any],
        max_tokens: int = 1500,
    ) -> dict[str, Any]:
        return {
            "next_agent": "report",
            "rationale": "Generate the report now.",
            "graph_label": "ready to report",
            "evidence_gaps": [],
            "skipped_agents": [],
            "llm_status": "bedrock",
            "llm_provider": "Amazon Bedrock",
        }

    monkeypatch.setattr(supervisor_agent, "optional_bedrock_json", fake_optional_bedrock_json)

    result = run_supervisor_agent(_state())

    assert result["next_agent"] == "architecture"
    assert result["agent_decisions"][0]["graph_label"] == "structure evidence found"
    assert result["agent_decisions"][0]["llm_status"] == "policy_enforced"
