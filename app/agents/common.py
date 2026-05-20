from __future__ import annotations

import json
from typing import Any

from app.config import settings
from app.llm.bedrock_client import BedrockChatClient


def mark_step(state: dict[str, Any], name: str, status: str) -> None:
    progress = state.setdefault("progress", [])
    for step in progress:
        if step.get("name") == name:
            step["status"] = status
            return
    progress.append({"name": name, "status": status})


def append_error(state: dict[str, Any], message: str) -> None:
    state.setdefault("errors", []).append(message)


def _with_llm_runtime(
    payload: dict[str, Any],
    status: str,
    reason: str | None = None,
) -> dict[str, Any]:
    result = dict(payload)
    result["llm_provider"] = "Amazon Bedrock" if status == "bedrock" else "deterministic"
    result["llm_model_id"] = settings.bedrock_chat_model_id
    result["llm_status"] = status
    if reason:
        result["llm_fallback_reason"] = reason
    return result


def _required_item_keys(items: list[Any]) -> set[str]:
    for item in items:
        if isinstance(item, dict) and item:
            return set(item.keys())
    return set()


def _has_item_shape(item: Any, required_keys: set[str]) -> bool:
    if not isinstance(item, dict):
        return False
    for key in required_keys:
        if key not in item:
            return False
        value = item.get(key)
        if value is None:
            return False
        if isinstance(value, str) and not value.strip():
            return False
    return True


def _repair_evidence_list(result_value: Any, fallback_value: list[Any]) -> list[Any]:
    if not isinstance(result_value, list):
        return fallback_value
    if not fallback_value:
        return result_value
    if not result_value:
        return fallback_value

    required_keys = _required_item_keys(fallback_value)
    if not required_keys:
        return result_value

    repaired_items = [item for item in result_value if _has_item_shape(item, required_keys)]
    if len(repaired_items) < len(fallback_value):
        return fallback_value
    return repaired_items


def _repair_shape(result: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    repaired = dict(result)
    for key, fallback_value in fallback.items():
        result_value = repaired.get(key)
        if isinstance(fallback_value, list):
            repaired[key] = _repair_evidence_list(result_value, fallback_value)
        elif isinstance(fallback_value, dict) and not isinstance(result_value, dict):
            repaired[key] = fallback_value
        elif isinstance(fallback_value, str) and not isinstance(result_value, str):
            repaired[key] = fallback_value
    return repaired


def optional_bedrock_json(
    system_prompt: str,
    payload: dict[str, Any],
    fallback: dict[str, Any],
    max_tokens: int = 3000,
) -> dict[str, Any]:
    if not settings.use_bedrock_agents:
        reason = "MODERNIZEAI_USE_BEDROCK_AGENTS is false."
        if settings.require_bedrock_agents:
            raise RuntimeError(reason)
        return _with_llm_runtime(fallback, "disabled", reason)
    expected_keys = set(fallback.keys())
    try:
        prompt = (
            "Return strict JSON matching the requested schema. "
            f"The top-level object must include these exact keys: {sorted(expected_keys)}. "
            "The fallback_schema in the evidence payload contains deterministic scanner facts. "
            "You do not need to reproduce long evidence arrays from fallback_schema; the server will merge deterministic evidence arrays after your response. "
            "If you do include evidence-backed items, preserve required fields such as file, evidence, title, severity, recommendation, files, and action. "
            "If the evidence is insufficient, keep the same keys and use empty arrays or concise caveats. "
            "Keep each text field under 240 characters. "
            "Keep arrays focused and concise. "
            "Do not include Markdown fences, comments, or explanatory text outside the JSON object. "
            "Use only this evidence payload:\n"
            + json.dumps(payload, indent=2, default=str)[:30000]
        )
        result = BedrockChatClient().generate_json(system_prompt, prompt, max_tokens=max_tokens)
        if not isinstance(result, dict):
            raise ValueError("Bedrock returned non-object JSON.")

        missing_keys = expected_keys - set(result.keys())
        if missing_keys:
            raise ValueError(f"Bedrock JSON missing required keys: {sorted(missing_keys)}")

        result = _repair_shape(result, fallback)

        for key, fallback_value in fallback.items():
            result_value = result.get(key)
            if isinstance(fallback_value, list) and fallback_value and not result_value:
                raise ValueError(f"Bedrock JSON returned empty value for evidence-backed list: {key}")
            if isinstance(fallback_value, dict) and fallback_value and not isinstance(result_value, dict):
                raise ValueError(f"Bedrock JSON returned invalid object for key: {key}")
            if isinstance(fallback_value, str) and fallback_value and not isinstance(result_value, str):
                raise ValueError(f"Bedrock JSON returned invalid string for key: {key}")

        return _with_llm_runtime(result, "bedrock")
    except Exception as exc:
        fallback = dict(fallback)
        return _with_llm_runtime(fallback, "fallback", str(exc))


def confidence_from_counts(*counts: int) -> str:
    total = sum(counts)
    if total >= 5:
        return "High"
    if total >= 2:
        return "Medium"
    return "Low"
