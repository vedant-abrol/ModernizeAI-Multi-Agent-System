from __future__ import annotations

import json
import traceback
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from threading import Thread
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agents.graph import status_payload_from_state, stream_analysis_graph
from app.config import settings
from app.ingestion.github_loader import load_public_github_repo
from app.ingestion.repo_sanitizer import find_repo_root
from app.ingestion.zip_loader import safe_extract_zip
from app.reports.report_store import get_status, save_analysis_result, set_status


router = APIRouter()
STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}


class GitHubAnalyzeRequest(BaseModel):
    repo_url: str


def _copy_steps(steps: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [dict(step) for step in steps or []]


def _json_line(payload: dict[str, Any]) -> str:
    return json.dumps(payload, default=str) + "\n"


def _progress_payload(
    analysis_id: str,
    status: str,
    steps: list[dict[str, Any]] | None,
    message: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "analysis_id": analysis_id,
        "event": "progress",
        "status": status,
        "steps": _copy_steps(steps),
    }
    if message:
        payload["message"] = message
    payload.update(extra)
    return payload


def _error_payload(analysis_id: str, exc: Exception) -> dict[str, Any]:
    message = getattr(exc, "detail", str(exc))
    set_status(analysis_id, "failed", error=str(message))
    status_payload = get_status(analysis_id)
    return {
        "analysis_id": analysis_id,
        "event": "error",
        "status": "failed",
        "steps": _copy_steps(status_payload.get("steps", [])),
        "agent_graph": status_payload.get("agent_graph", {}),
        "agent_decisions": status_payload.get("agent_decisions", []),
        "message": str(message),
    }


def _set_running_status_from_state(analysis_id: str, state: dict[str, Any]) -> None:
    status_payload = status_payload_from_state(state)
    set_status(
        analysis_id,
        "running",
        state.get("progress", []),
        agent_graph=status_payload["agent_graph"],
        agent_decisions=status_payload["agent_decisions"],
    )


def _progress_from_state(analysis_id: str, state: dict[str, Any], message: str | None = None, **extra: Any) -> dict[str, Any]:
    status_payload = status_payload_from_state(state)
    return _progress_payload(
        analysis_id,
        "running",
        state.get("progress", []),
        message,
        agent_graph=status_payload["agent_graph"],
        agent_decisions=status_payload["agent_decisions"],
        **extra,
    )


async def _save_upload(upload_file: UploadFile, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    with destination.open("wb") as handle:
        while chunk := await upload_file.read(1024 * 1024):
            size += len(chunk)
            if size > settings.max_upload_bytes:
                raise HTTPException(status_code=413, detail=f"Upload exceeds {settings.max_upload_mb} MB limit.")
            handle.write(chunk)


def _run_and_store(analysis_id: str, extracted_dir: Path) -> dict[str, Any]:
    repo_root = find_repo_root(extracted_dir)
    set_status(analysis_id, "running", [{"name": "ingestion", "status": "completed"}])
    state: dict[str, Any] | None = None
    try:
        for state in stream_analysis_graph(analysis_id, repo_root.as_posix()):
            _set_running_status_from_state(analysis_id, state)
    except Exception as exc:
        set_status(analysis_id, "failed", error=str(exc))
        raise
    if state is None:
        raise RuntimeError("Analysis graph did not produce a result.")
    save_analysis_result(analysis_id, dict(state))
    return {
        "analysis_id": analysis_id,
        "status": "completed",
        "report_url": f"/analysis/{analysis_id}/report",
    }


def _run_analysis_job(analysis_id: str, extracted_dir: Path) -> None:
    try:
        _run_and_store(analysis_id, extracted_dir)
    except Exception as exc:
        traceback.print_exc()
        set_status(analysis_id, "failed", error=str(exc))


def _start_analysis_job(analysis_id: str, extracted_dir: Path) -> None:
    Thread(target=_run_analysis_job, args=(analysis_id, extracted_dir), daemon=True).start()


def _run_and_stream(analysis_id: str, extracted_dir: Path) -> Iterator[str]:
    try:
        repo_root = find_repo_root(extracted_dir)
        setup_steps = [{"name": "ingestion", "status": "completed"}]
        set_status(analysis_id, "running", setup_steps)
        yield _json_line(_progress_payload(analysis_id, "running", setup_steps, "Repository prepared"))

        state: dict[str, Any] | None = None
        for state in stream_analysis_graph(analysis_id, repo_root.as_posix()):
            _set_running_status_from_state(analysis_id, state)
            yield _json_line(_progress_from_state(analysis_id, state))

        if state is None:
            raise RuntimeError("Analysis graph did not produce a result.")

        save_analysis_result(analysis_id, dict(state))
        yield _json_line(
            _progress_payload(
                analysis_id,
                "completed",
                state.get("progress", []),
                "Analysis completed",
                event="completed",
                agent_graph=state.get("agent_graph", {}),
                agent_decisions=state.get("agent_decisions", []),
                report_url=f"/analysis/{analysis_id}/report",
            )
        )
    except Exception as exc:
        yield _json_line(_error_payload(analysis_id, exc))


@router.post("/analyze/upload")
async def analyze_upload(file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip uploads are supported.")
    settings.ensure_directories()
    analysis_id = str(uuid.uuid4())
    upload_path = settings.upload_dir / f"{analysis_id}.zip"
    extracted_dir = settings.repo_dir / analysis_id
    set_status(analysis_id, "running", [{"name": "upload", "status": "running"}])
    try:
        await _save_upload(file, upload_path)
        set_status(analysis_id, "running", [{"name": "upload", "status": "completed"}])
        safe_extract_zip(upload_path, extracted_dir)
        return _run_and_store(analysis_id, extracted_dir)
    except HTTPException:
        set_status(analysis_id, "failed")
        raise
    except Exception as exc:
        set_status(analysis_id, "failed", error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/analyze/upload/stream")
async def analyze_upload_stream(file: UploadFile = File(...)) -> StreamingResponse:
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip uploads are supported.")
    settings.ensure_directories()
    analysis_id = str(uuid.uuid4())
    upload_path = settings.upload_dir / f"{analysis_id}.zip"
    extracted_dir = settings.repo_dir / analysis_id

    async def events() -> AsyncIterator[str]:
        upload_steps = [{"name": "upload", "status": "running"}]
        set_status(analysis_id, "running", upload_steps)
        yield _json_line(_progress_payload(analysis_id, "running", upload_steps, "Uploading repository"))
        try:
            await _save_upload(file, upload_path)
            upload_steps = [{"name": "upload", "status": "completed"}, {"name": "ingestion", "status": "running"}]
            set_status(analysis_id, "running", upload_steps)
            yield _json_line(_progress_payload(analysis_id, "running", upload_steps, "Extracting repository"))
            safe_extract_zip(upload_path, extracted_dir)
            for line in _run_and_stream(analysis_id, extracted_dir):
                yield line
        except Exception as exc:
            yield _json_line(_error_payload(analysis_id, exc))

    return StreamingResponse(events(), media_type="application/x-ndjson", headers=STREAM_HEADERS)


@router.post("/analyze/upload/start")
async def analyze_upload_start(file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip uploads are supported.")
    settings.ensure_directories()
    analysis_id = str(uuid.uuid4())
    upload_path = settings.upload_dir / f"{analysis_id}.zip"
    extracted_dir = settings.repo_dir / analysis_id
    set_status(analysis_id, "running", [{"name": "upload", "status": "running"}])
    try:
        await _save_upload(file, upload_path)
        set_status(
            analysis_id,
            "running",
            [{"name": "upload", "status": "completed"}, {"name": "ingestion", "status": "running"}],
        )
        safe_extract_zip(upload_path, extracted_dir)
        set_status(
            analysis_id,
            "running",
            [{"name": "upload", "status": "completed"}, {"name": "ingestion", "status": "completed"}],
        )
        _start_analysis_job(analysis_id, extracted_dir)
        return {
            "analysis_id": analysis_id,
            "status": "running",
            "report_url": f"/analysis/{analysis_id}/report",
        }
    except HTTPException:
        set_status(analysis_id, "failed")
        raise
    except Exception as exc:
        set_status(analysis_id, "failed", error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/analyze/github")
def analyze_github(request: GitHubAnalyzeRequest) -> dict[str, Any]:
    settings.ensure_directories()
    analysis_id = str(uuid.uuid4())
    zip_path = settings.upload_dir / f"{analysis_id}-github.zip"
    extracted_dir = settings.repo_dir / analysis_id
    set_status(analysis_id, "running", [{"name": "github_download", "status": "running"}])
    try:
        load_public_github_repo(request.repo_url, zip_path, extracted_dir)
        set_status(analysis_id, "running", [{"name": "github_download", "status": "completed"}])
        return _run_and_store(analysis_id, extracted_dir)
    except Exception as exc:
        set_status(analysis_id, "failed", error=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/analyze/github/stream")
def analyze_github_stream(request: GitHubAnalyzeRequest) -> StreamingResponse:
    settings.ensure_directories()
    analysis_id = str(uuid.uuid4())
    zip_path = settings.upload_dir / f"{analysis_id}-github.zip"
    extracted_dir = settings.repo_dir / analysis_id

    def events() -> Iterator[str]:
        download_steps = [{"name": "github_download", "status": "running"}]
        set_status(analysis_id, "running", download_steps)
        yield _json_line(_progress_payload(analysis_id, "running", download_steps, "Downloading public GitHub zipball"))
        try:
            load_public_github_repo(request.repo_url, zip_path, extracted_dir)
            download_steps = [
                {"name": "github_download", "status": "completed"},
                {"name": "ingestion", "status": "running"},
            ]
            set_status(analysis_id, "running", download_steps)
            yield _json_line(_progress_payload(analysis_id, "running", download_steps, "Preparing repository"))
            for line in _run_and_stream(analysis_id, extracted_dir):
                yield line
        except Exception as exc:
            yield _json_line(_error_payload(analysis_id, exc))

    return StreamingResponse(events(), media_type="application/x-ndjson", headers=STREAM_HEADERS)


def _run_github_analysis_job(analysis_id: str, repo_url: str, zip_path: Path, extracted_dir: Path) -> None:
    try:
        set_status(analysis_id, "running", [{"name": "github_download", "status": "running"}])
        load_public_github_repo(repo_url, zip_path, extracted_dir)
        set_status(
            analysis_id,
            "running",
            [
                {"name": "github_download", "status": "completed"},
                {"name": "ingestion", "status": "completed"},
            ],
        )
        _run_and_store(analysis_id, extracted_dir)
    except Exception as exc:
        traceback.print_exc()
        set_status(analysis_id, "failed", error=str(exc))


@router.post("/analyze/github/start")
def analyze_github_start(request: GitHubAnalyzeRequest) -> dict[str, Any]:
    settings.ensure_directories()
    analysis_id = str(uuid.uuid4())
    zip_path = settings.upload_dir / f"{analysis_id}-github.zip"
    extracted_dir = settings.repo_dir / analysis_id
    set_status(analysis_id, "running", [{"name": "github_download", "status": "pending"}])
    Thread(
        target=_run_github_analysis_job,
        args=(analysis_id, request.repo_url, zip_path, extracted_dir),
        daemon=True,
    ).start()
    return {
        "analysis_id": analysis_id,
        "status": "running",
        "report_url": f"/analysis/{analysis_id}/report",
    }


@router.get("/analysis/{analysis_id}/status")
def analysis_status(analysis_id: str) -> dict[str, Any]:
    return get_status(analysis_id)
