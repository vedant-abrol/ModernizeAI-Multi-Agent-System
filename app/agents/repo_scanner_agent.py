from __future__ import annotations

from pathlib import Path
from typing import Any

from app.agents.common import append_error, mark_step
from app.scanner.repo_scanner import scan_repository
from app.vectorstore.retriever import EmbeddingIndexError, index_repository


def run_repo_scanner_agent(state: dict[str, Any]) -> dict[str, Any]:
    mark_step(state, "repo_scanner", "running")
    try:
        repo_path = Path(state["repo_path"])
        metadata = scan_repository(repo_path, state["analysis_id"])
        index_result = index_repository(repo_path, metadata)
        metadata["vector_index"] = index_result
        state["repo_metadata"] = metadata
        if index_result.get("errors"):
            append_error(state, "Vector index completed with errors: " + "; ".join(index_result["errors"][:5]))
        mark_step(state, "repo_scanner", "completed")
    except EmbeddingIndexError as exc:
        mark_step(state, "repo_scanner", "failed")
        append_error(state, f"Repo Scanner Agent failed: {exc}")
        state["repo_metadata"] = {}
        raise
    except Exception as exc:
        mark_step(state, "repo_scanner", "failed")
        append_error(state, f"Repo Scanner Agent failed: {exc}")
        state["repo_metadata"] = {}
    return state
