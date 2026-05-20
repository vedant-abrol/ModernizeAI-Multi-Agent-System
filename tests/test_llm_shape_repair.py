from __future__ import annotations

from app.agents import common
from app.agents.common import _repair_shape, optional_bedrock_json
from app.config import settings


def test_repair_shape_preserves_evidence_backed_security_items() -> None:
    fallback = {
        "findings": [
            {
                "severity": "High",
                "title": "Potential hardcoded secret",
                "file": "application.properties",
                "evidence": "spring.datasource.password=<REDACTED>",
                "recommendation": "Move to a managed secrets store.",
            }
        ]
    }
    result = {
        "findings": [
            {
                "severity": "High",
                "category": "Credential risk",
                "description": "Hardcoded credential was detected.",
                "evidence": "password exists",
            }
        ]
    }

    repaired = _repair_shape(result, fallback)

    assert repaired["findings"] == fallback["findings"]


def test_repair_shape_rejects_api_inventory_without_file_evidence() -> None:
    fallback = {
        "api_inventory": [
            {
                "method": "GET",
                "path": "/orders",
                "file": "OrderController.java",
                "evidence": '@GetMapping("/orders")',
                "line": "12",
            }
        ]
    }
    result = {"api_inventory": [{"method": "GET", "path": "/orders"}]}

    repaired = _repair_shape(result, fallback)

    assert repaired["api_inventory"] == fallback["api_inventory"]


def test_optional_bedrock_json_falls_back_on_malformed_model_json(monkeypatch) -> None:
    class BrokenClient:
        def generate_json(self, system_prompt: str, user_prompt: str, max_tokens: int = 3000):
            raise ValueError("Expecting ',' delimiter: line 459 column 8")

    monkeypatch.setattr(common, "BedrockChatClient", BrokenClient)
    original_use = settings.use_bedrock_agents
    original_require = settings.require_bedrock_agents
    object.__setattr__(settings, "use_bedrock_agents", True)
    object.__setattr__(settings, "require_bedrock_agents", True)
    try:
        result = optional_bedrock_json(
            "Return JSON only.",
            {"fallback_schema": {"summary": "deterministic"}},
            {"summary": "deterministic"},
        )
    finally:
        object.__setattr__(settings, "use_bedrock_agents", original_use)
        object.__setattr__(settings, "require_bedrock_agents", original_require)

    assert result["summary"] == "deterministic"
    assert result["llm_status"] == "fallback"
    assert "Expecting" in result["llm_fallback_reason"]
