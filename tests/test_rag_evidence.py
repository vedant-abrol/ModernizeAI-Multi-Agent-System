from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.config import settings
from app.agents.rag import collect_rag_evidence
from app.vectorstore import retriever
from app.vectorstore.retriever import EmbeddingIndexError, index_repository, retrieve_for_agent


def test_collect_rag_evidence_redacts_dedupes_and_stores(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_retrieve(analysis_id: str, query: str, n_results: int | None = None) -> dict[str, Any]:
        return {
            "documents": [["spring.datasource.password=demo-password", "duplicate ignored"]],
            "metadatas": [
                [
                    {
                        "file_path": "src/main/resources/application.properties",
                        "file_type": "config",
                        "language": "properties",
                        "start_line": 4,
                        "end_line": 8,
                    },
                    {
                        "file_path": "src/main/resources/application.properties",
                        "file_type": "config",
                        "language": "properties",
                        "start_line": 4,
                        "end_line": 8,
                    },
                ]
            ],
            "ids": [["analysis-1::application.properties::chunk_0", "analysis-1::application.properties::chunk_0"]],
            "distances": [[0.12, 0.13]],
        }

    monkeypatch.setattr("app.agents.rag.retrieve_for_agent", fake_retrieve)
    state: dict[str, Any] = {"analysis_id": "analysis-1", "errors": []}

    evidence = collect_rag_evidence(state, "security_agent", ["password"], n_results=2)

    assert len(evidence) == 1
    assert evidence[0]["file_path"] == "src/main/resources/application.properties"
    assert evidence[0]["start_line"] == 4
    assert evidence[0]["snippet"] == "spring.datasource.password=<REDACTED>"
    assert "demo-password" not in evidence[0]["snippet"]
    assert state["rag_evidence"]["security_agent"] == evidence


def test_collect_rag_evidence_handles_empty_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.agents.rag.retrieve_for_agent",
        lambda analysis_id, query, n_results=None: {"documents": [[]], "metadatas": [[]], "ids": [[]], "distances": [[]]},
    )
    state: dict[str, Any] = {"analysis_id": "analysis-1", "errors": []}

    assert collect_rag_evidence(state, "architecture_agent", ["missing"]) == []
    assert state["rag_evidence"]["architecture_agent"] == []


@pytest.mark.parametrize(
    ("module_name", "runner_name", "report_key"),
    [
        ("app.agents.architecture_agent", "run_architecture_agent", "architecture_report"),
        ("app.agents.dependency_agent", "run_dependency_agent", "dependency_report"),
        ("app.agents.security_agent", "run_security_agent", "security_report"),
        ("app.agents.test_strategy_agent", "run_test_strategy_agent", "test_report"),
        ("app.agents.modernization_agent", "run_modernization_agent", "modernization_plan"),
        ("app.agents.critic_agent", "run_critic_agent", "critic_findings"),
    ],
)
def test_agent_payloads_include_retrieved_evidence(
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
    runner_name: str,
    report_key: str,
) -> None:
    module = importlib.import_module(module_name)
    rag_item = {
        "query": "service evidence",
        "file_path": "src/main/java/Demo.java",
        "start_line": 1,
        "end_line": 2,
        "file_type": "source",
        "language": "Java",
        "snippet": "class Demo {}",
        "distance": 0.2,
    }
    captured: dict[str, Any] = {}

    monkeypatch.setattr(module, "collect_rag_evidence", lambda *args, **kwargs: [rag_item])

    def fake_optional_bedrock_json(
        system_prompt: str,
        payload: dict[str, Any],
        fallback: dict[str, Any],
        max_tokens: int = 6000,
    ) -> dict[str, Any]:
        captured["payload"] = payload
        return dict(fallback)

    monkeypatch.setattr(module, "optional_bedrock_json", fake_optional_bedrock_json)
    state: dict[str, Any] = {
        "analysis_id": "analysis-1",
        "repo_path": ".",
        "repo_metadata": {
            "analysis_id": "analysis-1",
            "repo_root": ".",
            "indexed_file_paths": [],
            "controllers": [],
            "services": [],
            "repositories": [],
            "entities": [],
            "config_files": [],
            "dependency_files": [],
            "test_files": [],
        },
        "architecture_report": {},
        "dependency_report": {},
        "security_report": {},
        "test_report": {},
        "modernization_plan": {},
        "critic_findings": {},
        "progress": [],
        "errors": [],
    }

    getattr(module, runner_name)(state)

    assert captured["payload"]["retrieved_evidence"] == [rag_item]
    assert state[report_key]["retrieved_evidence"] == [rag_item]


def test_index_repository_and_retrieve_for_agent_returns_analysis_scoped_chunks(tmp_path: Path) -> None:
    old_chroma_path = settings.chroma_path
    old_use_bedrock = settings.use_bedrock_embeddings
    old_allow_local = settings.allow_local_embedding_fallback
    object.__setattr__(settings, "chroma_path", tmp_path / "chroma")
    object.__setattr__(settings, "use_bedrock_embeddings", False)
    object.__setattr__(settings, "allow_local_embedding_fallback", True)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "OrderService.java").write_text("@Service class OrderService { void checkout() {} }", encoding="utf-8")
    metadata = {
        "analysis_id": "rag-integration",
        "indexed_file_paths": ["OrderService.java"],
    }

    try:
        result = index_repository(repo, metadata)
        retrieved = retrieve_for_agent("rag-integration", "checkout service", n_results=2)

        assert result["chunks_indexed"] >= 1
        assert retrieved["documents"][0]
        assert retrieved["metadatas"][0][0]["analysis_id"] == "rag-integration"
        assert retrieved["metadatas"][0][0]["file_path"] == "OrderService.java"
    finally:
        object.__setattr__(settings, "chroma_path", old_chroma_path)
        object.__setattr__(settings, "use_bedrock_embeddings", old_use_bedrock)
        object.__setattr__(settings, "allow_local_embedding_fallback", old_allow_local)


def test_index_repository_respects_strict_embedding_mode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.java").write_text("class App {}", encoding="utf-8")

    class FailingCollection:
        def add(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("embedding unavailable")

    monkeypatch.setattr(retriever, "get_chroma_collection", lambda: FailingCollection())
    monkeypatch.setattr(
        retriever,
        "settings",
        SimpleNamespace(
            max_file_chars=200000,
            max_chunk_chars=4000,
            chunk_overlap_chars=400,
            use_bedrock_embeddings=True,
            allow_local_embedding_fallback=False,
        ),
    )

    with pytest.raises(EmbeddingIndexError):
        index_repository(repo, {"analysis_id": "strict", "indexed_file_paths": ["app.java"]})


def test_index_repository_local_fallback_when_allowed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.java").write_text("class App {}", encoding="utf-8")
    calls: list[dict[str, Any]] = []

    class FallbackCollection:
        def add(self, *args: Any, **kwargs: Any) -> None:
            calls.append(kwargs)
            if "embeddings" not in kwargs:
                raise RuntimeError("embedding unavailable")

    monkeypatch.setattr(retriever, "get_chroma_collection", lambda: FallbackCollection())
    monkeypatch.setattr(
        retriever,
        "settings",
        SimpleNamespace(
            max_file_chars=200000,
            max_chunk_chars=4000,
            chunk_overlap_chars=400,
            use_bedrock_embeddings=True,
            allow_local_embedding_fallback=True,
        ),
    )

    result = index_repository(repo, {"analysis_id": "fallback", "indexed_file_paths": ["app.java"]})

    assert result["chunks_indexed"] == 1
    assert calls[-1]["embeddings"]
