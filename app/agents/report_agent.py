from __future__ import annotations

from typing import Any

from app.agents.common import mark_step
from app.reports.markdown_report import generate_markdown_report


def run_report_agent(state: dict[str, Any]) -> dict[str, Any]:
    mark_step(state, "report_agent", "running")
    state["final_report_markdown"] = generate_markdown_report(state)
    mark_step(state, "report_agent", "completed")
    return state

