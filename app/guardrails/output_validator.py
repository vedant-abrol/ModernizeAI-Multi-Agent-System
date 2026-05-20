from __future__ import annotations

import json
import re
from typing import Any, Dict


def parse_json_safely(text: str) -> Dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError("LLM did not return valid JSON") from None
        payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("LLM JSON output must be an object")
    return payload


def ensure_dict(payload: Any, fallback: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    return fallback or {"error": "Output was not a JSON object."}

