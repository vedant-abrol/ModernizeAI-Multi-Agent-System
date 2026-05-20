from __future__ import annotations

import re
from pathlib import Path


def extract_express_endpoints(path: Path, text: str) -> list[dict[str, str]]:
    endpoints: list[dict[str, str]] = []
    pattern = re.compile(r"(?:app|router)\.(get|post|put|patch|delete)\s*\(\s*['\"]([^'\"]+)['\"]", re.I)
    for match in pattern.finditer(text):
        line_no = text[: match.start()].count("\n") + 1
        endpoints.append(
            {
                "method": match.group(1).upper(),
                "path": match.group(2),
                "file": path.as_posix(),
                "evidence": match.group(0),
                "line": str(line_no),
            }
        )
    return endpoints

