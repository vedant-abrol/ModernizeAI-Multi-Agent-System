from __future__ import annotations

from typing import Any


AGENT_NODE_DEFINITIONS: dict[str, dict[str, str]] = {
    "ingestion": {
        "label": "Ingestion",
        "role": "Repository archive or GitHub source is prepared for analysis.",
    },
    "repo_scanner": {
        "label": "Repo Scanner",
        "role": "Extracts framework, file, route, dependency, and evidence facts.",
    },
    "supervisor": {
        "label": "Supervisor",
        "role": "Chooses the next specialist based on evidence and critic feedback.",
    },
    "architecture": {
        "label": "Architecture",
        "role": "Maps layers, APIs, coupling, and blast-radius concerns.",
    },
    "dependency": {
        "label": "Dependency Risk",
        "role": "Reviews dependency and runtime modernization risk.",
    },
    "security": {
        "label": "Security",
        "role": "Finds evidence-backed security and configuration risks.",
    },
    "test_strategy": {
        "label": "Test Strategy",
        "role": "Identifies missing regression coverage and migration tests.",
    },
    "modernization": {
        "label": "Modernization",
        "role": "Builds a phased modernization and decomposition roadmap.",
    },
    "critic": {
        "label": "Critic",
        "role": "Blocks unsupported claims and requests follow-up work.",
    },
    "report": {
        "label": "Report",
        "role": "Assembles the final modernization report.",
    },
}

NODE_PROGRESS_KEYS: dict[str, str] = {
    "repo_scanner": "repo_scanner",
    "supervisor": "supervisor_agent",
    "architecture": "architecture_agent",
    "dependency": "dependency_risk_agent",
    "security": "security_agent",
    "test_strategy": "test_strategy_agent",
    "modernization": "modernization_planner_agent",
    "critic": "critic_agent",
    "report": "report_agent",
}

ROUTE_LABELS: dict[str, str] = {
    node_id: definition["label"] for node_id, definition in AGENT_NODE_DEFINITIONS.items()
}


def build_initial_agent_graph() -> dict[str, Any]:
    return {
        "nodes": [
            {
                "id": node_id,
                "label": definition["label"],
                "role": definition["role"],
                "status": "completed" if node_id == "ingestion" else "pending",
                "run_count": 0,
            }
            for node_id, definition in AGENT_NODE_DEFINITIONS.items()
        ],
        "edges": [
            {
                "source": "ingestion",
                "target": "repo_scanner",
                "label": "repository prepared",
                "iteration": 0,
            }
        ],
    }


def ensure_agent_graph(state: dict[str, Any]) -> dict[str, Any]:
    graph = state.get("agent_graph")
    if not isinstance(graph, dict):
        graph = build_initial_agent_graph()
        state["agent_graph"] = graph
        return graph

    nodes = graph.setdefault("nodes", [])
    known_ids = {node.get("id") for node in nodes if isinstance(node, dict)}
    for node_id, definition in AGENT_NODE_DEFINITIONS.items():
        if node_id in known_ids:
            continue
        nodes.append(
            {
                "id": node_id,
                "label": definition["label"],
                "role": definition["role"],
                "status": "pending",
                "run_count": 0,
            }
        )
    graph.setdefault("edges", [])
    return graph


def set_node_status(state: dict[str, Any], node_id: str, status: str) -> None:
    graph = ensure_agent_graph(state)
    for node in graph["nodes"]:
        if node.get("id") == node_id:
            node["status"] = status
            return


def add_graph_edge(state: dict[str, Any], source: str, target: str, label: str, iteration: int | None = None) -> None:
    graph = ensure_agent_graph(state)
    edge = {
        "source": source,
        "target": target,
        "label": label,
        "iteration": state.get("iteration_count", 0) if iteration is None else iteration,
    }
    if edge not in graph["edges"]:
        graph["edges"].append(edge)


def mark_agent_completed(state: dict[str, Any], node_id: str) -> None:
    graph = ensure_agent_graph(state)
    run_counts = state.setdefault("agent_run_counts", {})
    run_counts[node_id] = int(run_counts.get(node_id, 0)) + 1
    completed = state.setdefault("completed_agents", [])
    if node_id not in completed:
        completed.append(node_id)

    for node in graph["nodes"]:
        if node.get("id") == node_id:
            node["run_count"] = run_counts[node_id]
            node["status"] = "revisited" if run_counts[node_id] > 1 else "completed"
            return


def mark_agent_skipped(state: dict[str, Any], node_id: str, reason: str) -> None:
    graph = ensure_agent_graph(state)
    skipped = state.setdefault("skipped_agents", [])
    if node_id not in skipped:
        skipped.append(node_id)
    for node in graph["nodes"]:
        if node.get("id") == node_id and node.get("status") == "pending":
            node["status"] = "skipped"
            node["skip_reason"] = reason
            return


def agent_status_payload(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent_graph": ensure_agent_graph(state),
        "agent_decisions": list(state.get("agent_decisions", [])),
    }
