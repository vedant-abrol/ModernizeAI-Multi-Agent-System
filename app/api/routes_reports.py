from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.reports.docx_report import DOCX_MIME_TYPE, markdown_to_docx_bytes
from app.reports.report_store import load_analysis_result, load_report_markdown


router = APIRouter()


@router.get("/analysis/{analysis_id}/report")
def get_report(analysis_id: str) -> dict[str, str]:
    try:
        return {"analysis_id": analysis_id, "report_markdown": load_report_markdown(analysis_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/analysis/{analysis_id}/report.docx")
def get_report_docx(analysis_id: str) -> Response:
    try:
        report_markdown = load_report_markdown(analysis_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return Response(
        content=markdown_to_docx_bytes(report_markdown),
        media_type=DOCX_MIME_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="modernizeai-report-{analysis_id}.docx"'
        },
    )


@router.get("/analysis/{analysis_id}/evidence")
def get_evidence(analysis_id: str) -> dict[str, Any]:
    try:
        state = load_analysis_result(analysis_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "analysis_id": analysis_id,
        "repo_metadata": state.get("repo_metadata", {}),
        "architecture_report": state.get("architecture_report", {}),
        "dependency_report": state.get("dependency_report", {}),
        "security_report": state.get("security_report", {}),
        "test_report": state.get("test_report", {}),
        "modernization_plan": state.get("modernization_plan", {}),
        "critic_findings": state.get("critic_findings", {}),
        "rag_evidence": state.get("rag_evidence", {}),
        "agent_graph": state.get("agent_graph", {}),
        "agent_decisions": state.get("agent_decisions", []),
        "agent_messages": state.get("agent_messages", []),
        "completed_agents": state.get("completed_agents", []),
        "skipped_agents": state.get("skipped_agents", []),
        "errors": state.get("errors", []),
    }
