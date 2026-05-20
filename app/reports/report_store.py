from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import settings


_STATUS_STORE: dict[str, dict[str, Any]] = {}


def _copy_steps(steps: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [dict(step) for step in steps or []]


def set_status(
    analysis_id: str,
    status: str,
    steps: list[dict[str, Any]] | None = None,
    error: str | None = None,
    agent_graph: dict[str, Any] | None = None,
    agent_decisions: list[dict[str, Any]] | None = None,
) -> None:
    existing = _STATUS_STORE.get(analysis_id, {})
    payload = {
        "analysis_id": analysis_id,
        "status": status,
        "steps": _copy_steps(steps) if steps is not None else _copy_steps(existing.get("steps", [])),
    }
    if agent_graph is not None:
        payload["agent_graph"] = agent_graph
    elif existing.get("agent_graph") is not None:
        payload["agent_graph"] = existing["agent_graph"]
    if agent_decisions is not None:
        payload["agent_decisions"] = [dict(item) for item in agent_decisions]
    elif existing.get("agent_decisions") is not None:
        payload["agent_decisions"] = [dict(item) for item in existing["agent_decisions"]]
    existing_error = existing.get("error")
    if error or existing_error:
        payload["error"] = error or existing_error
    _STATUS_STORE[analysis_id] = payload


def get_status(analysis_id: str) -> dict[str, Any]:
    return _STATUS_STORE.get(analysis_id, {"analysis_id": analysis_id, "status": "unknown", "steps": []})


def save_analysis_result(analysis_id: str, state: dict[str, Any]) -> Path:
    settings.ensure_directories()
    path = settings.report_dir / f"{analysis_id}.json"
    path.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    set_status(
        analysis_id,
        "completed",
        state.get("progress", []),
        agent_graph=state.get("agent_graph"),
        agent_decisions=state.get("agent_decisions"),
    )
    return path


def load_analysis_result(analysis_id: str) -> dict[str, Any]:
    path = settings.report_dir / f"{analysis_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Analysis result not found: {analysis_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_report_markdown(analysis_id: str) -> str:
    state = load_analysis_result(analysis_id)
    if state.get("repo_metadata"):
        from app.reports.markdown_report import generate_markdown_report

        return generate_markdown_report(state)
    return state.get("final_report_markdown", "")
