from __future__ import annotations

from typing import Any, Dict

from botocore.config import Config

from app.config import settings
from app.guardrails.output_validator import parse_json_safely


class BedrockChatClient:
    def __init__(self) -> None:
        self.model_id = settings.bedrock_chat_model_id
        self._client = None

    def _bedrock_client(self):
        if self._client is None:
            import boto3

            self._client = boto3.client(
                "bedrock-runtime",
                region_name=settings.aws_region,
                config=Config(connect_timeout=10, read_timeout=300, retries={"max_attempts": 3}),
            )
        return self._client

    def _inference_config(self, max_tokens: int) -> Dict[str, Any]:
        config: Dict[str, Any] = {"maxTokens": max_tokens}
        if "claude-opus-4-7" not in self.model_id.lower():
            config["temperature"] = 0.1
        return config

    def generate_json(self, system_prompt: str, user_prompt: str, max_tokens: int = 3000) -> Dict[str, Any]:
        if not self.model_id:
            raise ValueError("BEDROCK_CHAT_MODEL_ID is not configured.")
        response = self._bedrock_client().converse(
            modelId=self.model_id,
            system=[{"text": system_prompt}],
            messages=[{"role": "user", "content": [{"text": user_prompt}]}],
            inferenceConfig=self._inference_config(max_tokens),
        )
        text = response["output"]["message"]["content"][0]["text"]
        return parse_json_safely(text)
