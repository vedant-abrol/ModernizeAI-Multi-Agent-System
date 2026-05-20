from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.agents.common import mark_step, optional_bedrock_json
from app.agents.rag import collect_rag_evidence
from app.guardrails.secret_redactor import contains_secret, redact_secrets
from app.llm.prompts import SECURITY_SYSTEM_PROMPT


def _finding(severity: str, title: str, file: str, evidence: str, recommendation: str) -> dict[str, str]:
    return {
        "severity": severity,
        "title": title,
        "file": file,
        "evidence": redact_secrets(evidence.strip())[:300],
        "recommendation": recommendation,
    }


def _is_plaintext_http_risk(stripped: str) -> bool:
    if not re.search(r"http://(?!localhost|127\.0\.0\.1)", stripped, flags=re.I):
        return False
    lowered = stripped.lower()
    documentation_or_schema = [
        "xmlns",
        "schemalocation",
        "maven.apache.org",
        "www.w3.org",
        "apache.org/pom",
    ]
    return not any(token in lowered for token in documentation_or_schema)


def _scan_file(rel_path: str, text: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        if not stripped:
            continue
        if contains_secret(stripped):
            findings.append(
                _finding(
                    "High",
                    "Potential hardcoded secret or credential",
                    rel_path,
                    stripped,
                    "Move this value to a managed secrets store, parameter store, or environment variables.",
                )
            )
        if "management.endpoints.web.exposure.include=*" in lowered:
            findings.append(
                _finding(
                    "High",
                    "Potentially exposed Spring Boot actuator endpoints",
                    rel_path,
                    stripped,
                    "Expose only required actuator endpoints and protect them with authentication/network controls.",
                )
            )
        if "allowedorigins(\"*\")" in lowered or "allowed-origins: *" in lowered or "cors" in lowered and "*" in stripped:
            findings.append(
                _finding(
                    "Medium",
                    "Potential wildcard CORS configuration",
                    rel_path,
                    stripped,
                    "Restrict CORS origins to known client domains.",
                )
            )
        if "csrf" in lowered and ("disable" in lowered or "false" in lowered):
            findings.append(
                _finding(
                    "Medium",
                    "Potential disabled CSRF protection",
                    rel_path,
                    stripped,
                    "Verify whether CSRF protection is required for browser-facing routes before disabling it.",
                )
            )
        if _is_plaintext_http_risk(stripped):
            findings.append(
                _finding(
                    "Medium",
                    "Potential plaintext HTTP integration",
                    rel_path,
                    stripped,
                    "Use HTTPS for external service calls and verify certificate handling.",
                )
            )
        if re.search(r"debug\s*[:=]\s*true", stripped, flags=re.I):
            findings.append(
                _finding(
                    "Low",
                    "Debug mode appears enabled",
                    rel_path,
                    stripped,
                    "Disable debug mode in production configuration.",
                )
            )
        if re.search(r"select\s+.*\"\s*\+", stripped, flags=re.I) or re.search(r"\+\s*\".*where", stripped, flags=re.I):
            findings.append(
                _finding(
                    "Medium",
                    "Potential SQL string concatenation",
                    rel_path,
                    stripped,
                    "Use parameterized queries or repository abstractions for user input.",
                )
            )
    return findings


def _fallback_security(metadata: dict[str, Any]) -> dict[str, Any]:
    repo_root = Path(metadata.get("repo_root", "."))
    findings: list[dict[str, str]] = []
    for rel_path in metadata.get("indexed_file_paths", []):
        path = repo_root / rel_path
        if not path.exists() or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        findings.extend(_scan_file(rel_path, text))

    unique: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in findings:
        key = (item["title"], item["file"], item["evidence"])
        if key not in seen:
            seen.add(key)
            unique.append(item)

    mitigations = [
        "Keep static-analysis findings advisory until a human review confirms impact.",
        "Externalize secrets before migration and rotate any real credentials found in legacy config.",
        "Add security regression tests around authentication, authorization, and configuration.",
    ]
    return {
        "risk_summary": (
            f"Found {len(unique)} potential security/configuration findings using static pattern scans. "
            "Pattern matches are potential issues, not confirmed exploits."
        ),
        "findings": unique,
        "recommended_mitigations": mitigations,
        "confidence": "High" if unique else "Medium",
    }


def run_security_agent(state: dict[str, Any]) -> dict[str, Any]:
    mark_step(state, "security_agent", "running")
    metadata = state.get("repo_metadata") or {}
    fallback = _fallback_security(metadata)
    retrieved_evidence = collect_rag_evidence(
        state,
        "security_agent",
        [
            "security config csrf cors allowed origins authentication authorization",
            "password secret token api key datasource properties credentials",
            "management actuator exposure http external integration debug",
        ],
    )
    state["security_report"] = optional_bedrock_json(
        SECURITY_SYSTEM_PROMPT,
        {
            "repo_metadata": metadata,
            "retrieved_evidence": retrieved_evidence,
            "security_scan": fallback,
        },
        fallback,
    )
    state["security_report"]["retrieved_evidence"] = retrieved_evidence
    mark_step(state, "security_agent", "completed")
    return state
