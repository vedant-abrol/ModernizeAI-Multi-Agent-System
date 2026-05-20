from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if ROOT.as_posix() not in sys.path:
    sys.path.insert(0, ROOT.as_posix())

from app.llm.bedrock_client import BedrockChatClient


def main() -> None:
    client = BedrockChatClient()
    result = client.generate_json(
        "Return JSON only.",
        'Return exactly this JSON shape with a true value: {"bedrock_check": true}',
        max_tokens=128,
    )
    print(json.dumps({"model_id": client.model_id, "result": result}, indent=2))


if __name__ == "__main__":
    main()
