from __future__ import annotations

import re
from typing import Pattern


SECRET_PATTERNS: list[Pattern[str]] = [
    re.compile(r"(?i)(password\s*[=:]\s*)([^\n\r]+)"),
    re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)([^\n\r]+)"),
    re.compile(r"(?i)(secret\s*[=:]\s*)([^\n\r]+)"),
    re.compile(r"(?i)(token\s*[=:]\s*)([^\n\r]+)"),
    re.compile(r"(?i)(spring\.datasource\.password\s*=\s*)([^\n\r]+)"),
    re.compile(r"(?i)(jwt\.secret\s*=\s*)([^\n\r]+)"),
]

AWS_ACCESS_KEY_PATTERN = re.compile(r"AKIA[0-9A-Z]{16}")
PRIVATE_KEY_PATTERN = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)


def redact_secrets(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(lambda match: f"{match.group(1)}<REDACTED>", redacted)
    redacted = AWS_ACCESS_KEY_PATTERN.sub("<REDACTED_AWS_ACCESS_KEY>", redacted)
    redacted = PRIVATE_KEY_PATTERN.sub("<REDACTED_PRIVATE_KEY>", redacted)
    return redacted


def contains_secret(text: str) -> bool:
    if AWS_ACCESS_KEY_PATTERN.search(text) or PRIVATE_KEY_PATTERN.search(text):
        return True
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)

