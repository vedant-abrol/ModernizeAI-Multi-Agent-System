from __future__ import annotations

from typing import Any, Iterable

from app.agents.common import append_error
from app.config import settings
from app.guardrails.secret_redactor import redact_secrets
from app.vectorstore.retriever import retrieve_for_agent


MAX_SNIPPET_CHARS = 900


def _strict_embedding_mode() -> bool:
    return settings.use_bedrock_embeddings and not settings.allow_local_embedding_fallback


def _groups(value: Any) -> list[list[Any]]:
    if not isinstance(value, list):
        return []
    if not value:
        return []
    if all(isinstance(item, list) for item in value):
        return value
    return [value]


def _value_at(groups: list[list[Any]], group_index: int, item_index: int, default: Any = None) -> Any:
    try:
        return groups[group_index][item_index]
    except (IndexError, TypeError):
        return default


def _snippet(text: Any) -> str:
    redacted = redact_secrets(str(text or ""))
    lines = [line.rstrip() for line in redacted.splitlines() if line.strip()]
    value = "\n".join(lines).strip()
    if len(value) > MAX_SNIPPET_CHARS:
        return value[: MAX_SNIPPET_CHARS - 3].rstrip() + "..."
    return value


def _flatten_retrieval(query: str, result: dict[str, Any]) -> list[dict[str, Any]]:
    documents = _groups(result.get("documents"))
    metadatas = _groups(result.get("metadatas"))
    ids = _groups(result.get("ids"))
    distances = _groups(result.get("distances"))

    items: list[dict[str, Any]] = []
    for group_index, docs in enumerate(documents):
        for item_index, document in enumerate(docs):
            metadata = _value_at(metadatas, group_index, item_index, {}) or {}
            doc_id = _value_at(ids, group_index, item_index)
            distance = _value_at(distances, group_index, item_index)
            snippet = _snippet(document)
            if not snippet:
                continue
            items.append(
                {
                    "query": query,
                    "id": doc_id
                    or (
                        f"{metadata.get('file_path', 'unknown')}:"
                        f"{metadata.get('start_line', '')}:"
                        f"{metadata.get('end_line', '')}"
                    ),
                    "file_path": metadata.get("file_path", "unknown"),
                    "start_line": metadata.get("start_line"),
                    "end_line": metadata.get("end_line"),
                    "file_type": metadata.get("file_type", "unknown"),
                    "language": metadata.get("language", "unknown"),
                    "snippet": snippet,
                    "distance": distance if isinstance(distance, (int, float)) else None,
                }
            )
    return items


def collect_rag_evidence(
    state: dict[str, Any],
    agent_name: str,
    queries: Iterable[str],
    n_results: int = 4,
    max_items: int = 8,
) -> list[dict[str, Any]]:
    analysis_id = state.get("analysis_id")
    if not analysis_id:
        return []

    evidence: list[dict[str, Any]] = []
    seen: set[str] = set()
    for query in queries:
        try:
            result = retrieve_for_agent(str(analysis_id), query, n_results=n_results)
        except Exception as exc:
            if _strict_embedding_mode():
                raise
            append_error(state, f"Chroma retrieval unavailable for {agent_name}: {exc}")
            continue

        for item in _flatten_retrieval(query, result):
            key = str(item.get("id") or "")
            if key in seen:
                continue
            seen.add(key)
            evidence.append(item)
            if len(evidence) >= max_items:
                break
        if len(evidence) >= max_items:
            break

    state.setdefault("rag_evidence", {})[agent_name] = evidence
    return evidence
