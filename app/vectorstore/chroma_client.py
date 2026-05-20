from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from app.config import settings
from app.vectorstore.embeddings import BedrockTitanEmbeddingFunction, deterministic_embedding


@dataclass
class InMemoryCollection:
    name: str
    documents: list[str] = field(default_factory=list)
    metadatas: list[dict[str, Any]] = field(default_factory=list)
    ids: list[str] = field(default_factory=list)
    embeddings: list[list[float]] = field(default_factory=list)

    def add(
        self,
        documents: Iterable[str],
        metadatas: Iterable[dict[str, Any]],
        ids: Iterable[str],
        embeddings: Iterable[list[float]] | None = None,
    ) -> None:
        docs = list(documents)
        metas = list(metadatas)
        doc_ids = list(ids)
        vectors = list(embeddings) if embeddings is not None else [deterministic_embedding(doc) for doc in docs]
        for doc, meta, doc_id, vector in zip(docs, metas, doc_ids, vectors):
            if doc_id in self.ids:
                index = self.ids.index(doc_id)
                self.documents[index] = doc
                self.metadatas[index] = meta
                self.embeddings[index] = vector
            else:
                self.documents.append(doc)
                self.metadatas.append(meta)
                self.ids.append(doc_id)
                self.embeddings.append(vector)

    def query(self, query_texts: list[str], n_results: int = 8, where: dict[str, Any] | None = None) -> dict[str, Any]:
        where = where or {}
        all_docs: list[list[str]] = []
        all_metas: list[list[dict[str, Any]]] = []
        all_ids: list[list[str]] = []
        all_distances: list[list[float]] = []
        for query in query_texts:
            query_vector = deterministic_embedding(query)
            scored: list[tuple[float, int]] = []
            for index, (meta, vector) in enumerate(zip(self.metadatas, self.embeddings)):
                if any(meta.get(key) != value for key, value in where.items()):
                    continue
                scored.append((_cosine_distance(query_vector, vector), index))
            scored.sort(key=lambda item: item[0])
            chosen = scored[:n_results]
            all_docs.append([self.documents[index] for _, index in chosen])
            all_metas.append([self.metadatas[index] for _, index in chosen])
            all_ids.append([self.ids[index] for _, index in chosen])
            all_distances.append([distance for distance, _ in chosen])
        return {"documents": all_docs, "metadatas": all_metas, "ids": all_ids, "distances": all_distances}


_IN_MEMORY_COLLECTIONS: dict[str, InMemoryCollection] = {}


def _cosine_distance(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 1.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a)) or 1.0
    norm_b = math.sqrt(sum(y * y for y in b)) or 1.0
    return 1.0 - (dot / (norm_a * norm_b))


def _collection_name() -> str:
    if not settings.use_bedrock_embeddings:
        return "repo_chunks_local"
    suffix = re.sub(r"[^A-Za-z0-9_-]+", "_", settings.bedrock_embed_model_id).strip("_")
    suffix = suffix[:38].strip("_") or "bedrock"
    return f"repo_chunks_bedrock_{suffix}"


def get_chroma_collection():
    name = _collection_name()
    try:
        import chromadb

        client = chromadb.PersistentClient(path=settings.chroma_path.as_posix())
        return client.get_or_create_collection(
            name=name, embedding_function=BedrockTitanEmbeddingFunction()
        )
    except Exception:
        if name not in _IN_MEMORY_COLLECTIONS:
            _IN_MEMORY_COLLECTIONS[name] = InMemoryCollection(name=name)
        return _IN_MEMORY_COLLECTIONS[name]
