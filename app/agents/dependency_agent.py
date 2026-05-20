from __future__ import annotations

import re
from typing import Any

from app.agents.common import mark_step, optional_bedrock_json
from app.agents.rag import collect_rag_evidence
from app.llm.prompts import DEPENDENCY_SYSTEM_PROMPT


def _version_tuple(version: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", version or "")
    return tuple(int(number) for number in numbers[:3])


def _dependency_name(dep: dict[str, Any]) -> str:
    if dep.get("name"):
        return dep["name"]
    return ":".join(part for part in [dep.get("groupId"), dep.get("artifactId")] if part)


def _fallback_dependency(metadata: dict[str, Any]) -> dict[str, Any]:
    details = metadata.get("dependency_details", [])
    build_tool = (metadata.get("build_tools") or ["unknown"])[0] if metadata.get("build_tools") else "unknown"
    key_dependencies: list[dict[str, Any]] = []
    risks: list[dict[str, str]] = []
    recommendations: list[dict[str, str]] = []

    for info in details:
        file_path = info.get("file", "")
        spring_boot_version = info.get("spring_boot_version", "")
        if spring_boot_version:
            key_dependencies.append(
                {
                    "name": "Spring Boot",
                    "version": spring_boot_version,
                    "file": file_path,
                    "evidence": f"spring-boot-starter-parent {spring_boot_version}",
                }
            )
            if _version_tuple(spring_boot_version) and _version_tuple(spring_boot_version) < (2, 7):
                risks.append(
                    {
                        "severity": "Medium",
                        "title": "Potential legacy Spring Boot baseline",
                        "file": file_path,
                        "evidence": f"Spring Boot version {spring_boot_version}",
                        "recommendation": "Plan a staged upgrade path and verify framework compatibility before cloud migration.",
                    }
                )
        for dep in info.get("dependencies", [])[:20]:
            name = _dependency_name(dep)
            if name:
                key_dependencies.append(
                    {
                        "name": name,
                        "version": dep.get("version", ""),
                        "scope": dep.get("scope") or dep.get("configuration", ""),
                        "file": file_path,
                        "evidence": f"{name} {dep.get('version', '')}".strip(),
                    }
                )
            lowered = name.lower()
            if "mysql-connector-java" in lowered and dep.get("version"):
                risks.append(
                    {
                        "severity": "Low",
                        "title": "Potential database driver upgrade work",
                        "file": file_path,
                        "evidence": f"{name} {dep.get('version')}",
                        "recommendation": "Review JDBC driver compatibility during the Java and Spring upgrade plan.",
                    }
                )

    if metadata.get("framework") == "Node/Express" and not any("package-lock" in item.get("file", "") for item in metadata.get("dependency_files", [])):
        risks.append(
            {
                "severity": "Low",
                "title": "No npm lockfile evidence found",
                "file": "package.json",
                "evidence": "package.json found without package-lock.json in indexed files",
                "recommendation": "Commit a lockfile for reproducible dependency resolution.",
            }
        )

    if build_tool != "unknown":
        recommendations.append(
            {
                "title": "Create dependency upgrade matrix",
                "recommendation": "Inventory framework, runtime, database, and test library versions before migration.",
            }
        )

    return {
        "dependency_summary": (
            "Dependency analysis is based on declared dependency files only. "
            "No vulnerability scanner was run, so findings are potential modernization risks, not confirmed CVEs."
        ),
        "build_tool": build_tool,
        "key_dependencies": key_dependencies[:30],
        "potential_risks": risks,
        "upgrade_recommendations": recommendations,
        "confidence": "High" if details else "Low",
    }


def run_dependency_agent(state: dict[str, Any]) -> dict[str, Any]:
    mark_step(state, "dependency_risk_agent", "running")
    metadata = state.get("repo_metadata") or {}
    fallback = _fallback_dependency(metadata)
    retrieved_evidence = collect_rag_evidence(
        state,
        "dependency_risk_agent",
        [
            "pom.xml build.gradle package.json dependency versions",
            "Spring Boot parent artifact dependency management",
            "npm lockfile package lock dependencies",
        ],
    )
    state["dependency_report"] = optional_bedrock_json(
        DEPENDENCY_SYSTEM_PROMPT,
        {
            "repo_metadata": metadata,
            "retrieved_evidence": retrieved_evidence,
            "fallback_schema": fallback,
        },
        fallback,
    )
    state["dependency_report"]["retrieved_evidence"] = retrieved_evidence
    mark_step(state, "dependency_risk_agent", "completed")
    return state
