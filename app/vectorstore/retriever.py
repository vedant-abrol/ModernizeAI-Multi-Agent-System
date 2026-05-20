from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import settings
from app.guardrails.secret_redactor import redact_secrets
from app.ingestion.file_classifier import classify_file, language_for_path
from app.vectorstore.chroma_client import get_chroma_collection
from app.vectorstore.chunker import chunk_text
from app.vectorstore.embeddings import deterministic_embedding


class EmbeddingIndexError(RuntimeError):
    """Raised when strict Bedrock embedding mode cannot index repository chunks."""


def _strict_embedding_mode() -> bool:
    return settings.use_bedrock_embeddings and not settings.allow_local_embedding_fallback


def index_repository(repo_root: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    collection = get_chroma_collection()
    added = 0
    errors: list[str] = []
    for rel_path in metadata.get("indexed_file_paths", []):
        path = repo_root / rel_path
        if not path.exists() or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")[: settings.max_file_chars]
            text = redact_secrets(text)
            file_type = classify_file(Path(rel_path), text)
            chunks = chunk_text(text, settings.max_chunk_chars, settings.chunk_overlap_chars)
            documents = [chunk.text for chunk in chunks if chunk.text.strip()]
            metadatas = [
                {
                    "analysis_id": metadata["analysis_id"],
                    "file_path": rel_path,
                    "file_type": file_type,
                    "language": language_for_path(path),
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                }
                for chunk in chunks
                if chunk.text.strip()
            ]
            ids = [
                f"{metadata['analysis_id']}::{rel_path}::chunk_{chunk.chunk_index}"
                for chunk in chunks
                if chunk.text.strip()
            ]
            if documents:
                try:
                    collection.add(documents=documents, metadatas=metadatas, ids=ids)
                except Exception as exc:
                    if _strict_embedding_mode():
                        raise EmbeddingIndexError(f"{rel_path}: Bedrock/Chroma embedding failed: {exc}") from exc
                    vectors = [deterministic_embedding(doc) for doc in documents]
                    collection.add(documents=documents, metadatas=metadatas, ids=ids, embeddings=vectors)
                added += len(documents)
        except EmbeddingIndexError:
            raise
        except Exception as exc:
            errors.append(f"{rel_path}: {exc}")
    return {"chunks_indexed": added, "errors": errors}


def retrieve_for_agent(analysis_id: str, query: str, n_results: int | None = None) -> dict[str, Any]:
    collection = get_chroma_collection()
    return collection.query(
        query_texts=[query],
        n_results=n_results or settings.max_retrieval_results,
        where={"analysis_id": analysis_id},
    )
