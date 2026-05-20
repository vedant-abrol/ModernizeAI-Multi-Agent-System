from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv() -> None:
    try:
        from dotenv import find_dotenv, load_dotenv
    except Exception:
        return
    dotenv_path = find_dotenv(usecwd=True) or find_dotenv()
    load_dotenv(dotenv_path=dotenv_path or None, override=True)


_load_dotenv()


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    aws_region: str = field(default_factory=lambda: os.getenv("AWS_REGION", "us-east-1"))
    bedrock_chat_model_id: str = field(
        default_factory=lambda: os.getenv("BEDROCK_CHAT_MODEL_ID", "us.anthropic.claude-opus-4-6-v1")
    )
    bedrock_embed_model_id: str = field(
        default_factory=lambda: os.getenv("BEDROCK_EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0")
    )
    chroma_path: Path = field(default_factory=lambda: Path(os.getenv("CHROMA_PATH", "./data/chroma")))
    upload_dir: Path = field(default_factory=lambda: Path(os.getenv("UPLOAD_DIR", "./data/uploads")))
    repo_dir: Path = field(default_factory=lambda: Path(os.getenv("REPO_DIR", "./data/repos")))
    report_dir: Path = field(default_factory=lambda: Path(os.getenv("REPORT_DIR", "./data/reports")))
    max_upload_mb: int = field(default_factory=lambda: int(os.getenv("MAX_UPLOAD_MB", "50")))
    max_file_chars: int = field(default_factory=lambda: int(os.getenv("MAX_FILE_CHARS", "200000")))
    max_chunk_chars: int = field(default_factory=lambda: int(os.getenv("MAX_CHUNK_CHARS", "4000")))
    chunk_overlap_chars: int = field(default_factory=lambda: int(os.getenv("CHUNK_OVERLAP_CHARS", "400")))
    max_retrieval_results: int = field(default_factory=lambda: int(os.getenv("MAX_RETRIEVAL_RESULTS", "8")))
    app_env: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    api_base_url: str = field(default_factory=lambda: os.getenv("API_BASE_URL", "http://localhost:8000"))
    github_token: str | None = field(default_factory=lambda: os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN"))
    use_bedrock_agents: bool = field(default_factory=lambda: _bool_env("MODERNIZEAI_USE_BEDROCK_AGENTS", False))
    require_bedrock_agents: bool = field(
        default_factory=lambda: _bool_env("MODERNIZEAI_REQUIRE_BEDROCK_AGENTS", False)
    )
    use_bedrock_embeddings: bool = field(default_factory=lambda: _bool_env("MODERNIZEAI_USE_BEDROCK_EMBEDDINGS", False))
    allow_local_embedding_fallback: bool = field(
        default_factory=lambda: _bool_env("MODERNIZEAI_ALLOW_LOCAL_EMBEDDINGS", True)
    )

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    def ensure_directories(self) -> None:
        for path in [self.chroma_path, self.upload_dir, self.repo_dir, self.report_dir]:
            path.mkdir(parents=True, exist_ok=True)


settings = Settings()
