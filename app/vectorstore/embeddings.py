from __future__ import annotations

import hashlib
import json
from typing import Iterable, List

from app.config import settings


def deterministic_embedding(text: str, dimensions: int = 384) -> list[float]:
    vector = [0.0] * dimensions
    tokens = text.lower().split()
    if not tokens:
        return vector
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        vector[index] += 1.0
    norm = sum(value * value for value in vector) ** 0.5 or 1.0
    return [value / norm for value in vector]


class BedrockTitanEmbeddingFunction:
    """Chroma-compatible embedding function using Titan, with a local fallback.

    The AWS path is used when credentials and network access are available. The
    deterministic fallback keeps tests and local sample demos usable before EC2
    IAM/Bedrock access has been configured.
    """

    def __init__(self) -> None:
        self.model_id = settings.bedrock_embed_model_id
        self._client = None

    def name(self) -> str:
        return "bedrock-titan-v2-with-local-fallback"

    def embed_documents(self, input: Iterable[str]) -> List[list[float]]:
        return self(input)

    def embed_query(self, input: Iterable[str]) -> List[list[float]]:
        return self(input)

    def _bedrock_client(self):
        if self._client is None:
            import boto3

            self._client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
        return self._client

    def __call__(self, input: Iterable[str]) -> List[list[float]]:
        vectors: list[list[float]] = []
        for text in input:
            if not settings.use_bedrock_embeddings:
                vectors.append(deterministic_embedding(text))
                continue
            try:
                body = json.dumps({"inputText": text})
                response = self._bedrock_client().invoke_model(modelId=self.model_id, body=body)
                payload = json.loads(response["body"].read())
                vectors.append(payload["embedding"])
            except Exception:
                if not settings.allow_local_embedding_fallback:
                    raise
                vectors.append(deterministic_embedding(text))
        return vectors
