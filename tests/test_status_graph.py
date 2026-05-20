from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.reports.report_store import set_status


def test_status_endpoint_returns_live_agent_graph() -> None:
    agent_graph = {
        "nodes": [{"id": "supervisor", "label": "Supervisor", "status": "completed", "run_count": 1}],
        "edges": [{"source": "supervisor", "target": "security", "label": "risk signals detected", "iteration": 1}],
    }
    decisions = [{"iteration": 1, "next_agent": "security", "rationale": "Risk signals detected."}]
    set_status(
        "analysis-status-graph",
        "running",
        [{"name": "supervisor_agent", "status": "completed"}],
        agent_graph=agent_graph,
        agent_decisions=decisions,
    )

    response = TestClient(app).get("/analysis/analysis-status-graph/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["agent_graph"] == agent_graph
    assert payload["agent_decisions"] == decisions
