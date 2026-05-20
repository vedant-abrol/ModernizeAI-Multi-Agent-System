from __future__ import annotations

from typing import Any

from app.config import settings
from app.llm.bedrock_client import BedrockChatClient


class FakeBedrockRuntime:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.kwargs = kwargs
        return {"output": {"message": {"content": [{"text": '{"ok": true}'}]}}}


def test_opus_47_omits_unsupported_sampling_parameters() -> None:
    original_model_id = settings.bedrock_chat_model_id
    object.__setattr__(settings, "bedrock_chat_model_id", "us.anthropic.claude-opus-4-7")
    try:
        client = BedrockChatClient()
        fake_runtime = FakeBedrockRuntime()
        client._client = fake_runtime

        result = client.generate_json("Return JSON only.", "Return {\"ok\": true}.", max_tokens=128)
    finally:
        object.__setattr__(settings, "bedrock_chat_model_id", original_model_id)

    assert result == {"ok": True}
    assert fake_runtime.kwargs["modelId"] == "us.anthropic.claude-opus-4-7"
    assert fake_runtime.kwargs["inferenceConfig"] == {"maxTokens": 128}


def test_opus_46_keeps_temperature() -> None:
    original_model_id = settings.bedrock_chat_model_id
    object.__setattr__(settings, "bedrock_chat_model_id", "us.anthropic.claude-opus-4-6-v1")
    try:
        client = BedrockChatClient()
        fake_runtime = FakeBedrockRuntime()
        client._client = fake_runtime

        client.generate_json("Return JSON only.", "Return {\"ok\": true}.", max_tokens=256)
    finally:
        object.__setattr__(settings, "bedrock_chat_model_id", original_model_id)

    assert fake_runtime.kwargs["modelId"] == "us.anthropic.claude-opus-4-6-v1"
    assert fake_runtime.kwargs["inferenceConfig"] == {"maxTokens": 256, "temperature": 0.1}
