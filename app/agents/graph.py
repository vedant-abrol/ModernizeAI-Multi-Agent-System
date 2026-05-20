from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Callable

from app.agents.agent_graph import (
    NODE_PROGRESS_KEYS,
    add_graph_edge,
    agent_status_payload,
    build_initial_agent_graph,
    mark_agent_completed,
    set_node_status,
)
from app.agents.architecture_agent import run_architecture_agent
from app.agents.common import append_error, mark_step
from app.agents.critic_agent import run_critic_agent
from app.agents.dependency_agent import run_dependency_agent
from app.agents.modernization_agent import run_modernization_agent
from app.agents.report_agent import run_report_agent
from app.agents.repo_scanner_agent import run_repo_scanner_agent
from app.agents.security_agent import run_security_agent
from app.agents.state import ModernizeState
from app.agents.supervisor_agent import run_supervisor_agent
from app.agents.test_strategy_agent import run_test_strategy_agent


NODE_RUNNERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "repo_scanner": run_repo_scanner_agent,
    "supervisor": run_supervisor_agent,
    "architecture": run_architecture_agent,
    "dependency": run_dependency_agent,
    "security": run_security_agent,
    "test_strategy": run_test_strategy_agent,
    "modernization": run_modernization_agent,
    "critic": run_critic_agent,
    "report": run_report_agent,
}

SPECIALIST_ROUTES = {
    "architecture",
    "dependency",
    "security",
    "test_strategy",
    "modernization",
    "critic",
}


class DynamicGraph:
    def invoke(self, state: ModernizeState) -> ModernizeState:
        current: dict[str, Any] = dict(state)
        current = _execute_node(current, "repo_scanner")
        while current.get("next_agent") != "report":
            current = _execute_node(current, "supervisor")
            next_agent = current.get("next_agent", "report")
            if next_agent == "report":
                break
            current = _execute_node(current, str(next_agent))
        return _execute_node(current, "report")


def _initial_state(analysis_id: str, repo_path: str) -> ModernizeState:
    return {
        "analysis_id": analysis_id,
        "repo_path": repo_path,
        "repo_metadata": {},
        "architecture_report": None,
        "dependency_report": None,
        "security_report": None,
        "test_report": None,
        "modernization_plan": None,
        "critic_findings": None,
        "final_report_markdown": None,
        "rag_evidence": {},
        "progress": [],
        "errors": [],
        "next_agent": "repo_scanner",
        "iteration_count": 0,
        "max_iterations": 10,
        "completed_agents": [],
        "skipped_agents": [],
        "agent_run_counts": {},
        "agent_decisions": [],
        "agent_messages": [],
        "agent_graph": build_initial_agent_graph(),
        "critic_approved": False,
        "critic_feedback": [],
        "evidence_gaps": [],
        "last_agent": "ingestion",
    }


def _prepare_node(state: dict[str, Any], node_name: str) -> None:
    progress_key = NODE_PROGRESS_KEYS[node_name]
    mark_step(state, progress_key, "running")
    set_node_status(state, node_name, "running")


def _mark_node_failed(state: dict[str, Any], node_name: str, exc: Exception) -> None:
    progress_key = NODE_PROGRESS_KEYS[node_name]
    mark_step(state, progress_key, "failed")
    set_node_status(state, node_name, "failed")
    append_error(state, f"{node_name} failed: {exc}")


def _record_return_edge(state: dict[str, Any], node_name: str) -> None:
    if node_name == "report":
        return
    if node_name == "repo_scanner":
        add_graph_edge(state, "repo_scanner", "supervisor", "facts indexed", 0)
        return
    if node_name in SPECIALIST_ROUTES:
        add_graph_edge(
            state,
            node_name,
            "supervisor",
            "results returned",
            int(state.get("iteration_count", 0)),
        )


def _execute_node(state: dict[str, Any], node_name: str) -> dict[str, Any]:
    if node_name not in NODE_RUNNERS:
        raise RuntimeError(f"Unknown agent route: {node_name}")
    _prepare_node(state, node_name)
    if node_name == "report":
        mark_agent_completed(state, node_name)
    current = NODE_RUNNERS[node_name](state)
    if node_name != "report":
        mark_agent_completed(current, node_name)
    _record_return_edge(current, node_name)
    current["last_agent"] = node_name
    return current


def build_graph():
    try:
        from langgraph.graph import END, StateGraph

        graph = StateGraph(ModernizeState)
        for name in NODE_RUNNERS:
            graph.add_node(name, lambda state, node_name=name: _execute_node(dict(state), node_name))
        graph.set_entry_point("repo_scanner")
        graph.add_edge("repo_scanner", "supervisor")
        graph.add_conditional_edges(
            "supervisor",
            lambda state: state.get("next_agent", "report"),
            {
                "architecture": "architecture",
                "dependency": "dependency",
                "security": "security",
                "test_strategy": "test_strategy",
                "modernization": "modernization",
                "critic": "critic",
                "report": "report",
            },
        )
        for name in SPECIALIST_ROUTES:
            graph.add_edge(name, "supervisor")
        graph.add_edge("report", END)
        return graph.compile()
    except Exception:
        return DynamicGraph()


def run_analysis_graph(analysis_id: str, repo_path: str) -> ModernizeState:
    graph = build_graph()
    return graph.invoke(_initial_state(analysis_id, repo_path))


def stream_analysis_graph(analysis_id: str, repo_path: str) -> Iterator[ModernizeState]:
    current: dict[str, Any] = dict(_initial_state(analysis_id, repo_path))

    route = "repo_scanner"
    while True:
        _prepare_node(current, route)
        yield current
        try:
            if route == "report":
                mark_agent_completed(current, route)
            current = NODE_RUNNERS[route](current)
            if route != "report":
                mark_agent_completed(current, route)
            _record_return_edge(current, route)
            current["last_agent"] = route
        except Exception as exc:
            _mark_node_failed(current, route, exc)
            yield current
            raise
        yield current

        if route == "report":
            break

        if route == "supervisor":
            route = str(current.get("next_agent", "report"))
        else:
            route = "supervisor"


def status_payload_from_state(state: dict[str, Any]) -> dict[str, Any]:
    return agent_status_payload(state)
