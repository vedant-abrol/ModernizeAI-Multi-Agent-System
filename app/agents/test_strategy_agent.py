from __future__ import annotations

from typing import Any

from app.agents.common import mark_step, optional_bedrock_json
from app.agents.rag import collect_rag_evidence
from app.llm.prompts import TEST_SYSTEM_PROMPT
from app.scanner.repo_scanner import matching_test_exists


def _fallback_test_strategy(metadata: dict[str, Any]) -> dict[str, Any]:
    existing_tests = metadata.get("test_files", [])
    missing: list[dict[str, str]] = []
    recommended: list[dict[str, str]] = []

    for controller in metadata.get("controllers", []):
        name = controller.get("name", "Controller")
        if not matching_test_exists(name, existing_tests):
            endpoints = controller.get("endpoints", [])
            endpoint_text = ", ".join(f"{item.get('method')} {item.get('path')}" for item in endpoints) or "detected routes"
            missing.append({"target": name, "type": "controller", "file": controller.get("file", "")})
            recommended.append(
                {
                    "type": "Controller test",
                    "target": name,
                    "suggestion": f"Add API tests for {endpoint_text}, including validation and error cases.",
                    "evidence": f"{controller.get('file')} exists but no matching {name}Test was found.",
                }
            )

    for service in metadata.get("services", []):
        name = service.get("name", "Service")
        if not matching_test_exists(name, existing_tests):
            missing.append({"target": name, "type": "service", "file": service.get("file", "")})
            recommended.append(
                {
                    "type": "Unit test",
                    "target": name,
                    "suggestion": "Add unit tests for business rules, failure paths, and dependency boundaries.",
                    "evidence": f"{service.get('file')} exists but no matching {name}Test was found.",
                }
            )

    migration_tests = [
        "Create golden-path API regression tests before dependency upgrades.",
        "Add configuration smoke tests for environment-specific settings.",
        "Add database migration rollback and compatibility checks where persistence files exist.",
    ]
    return {
        "test_summary": (
            f"Found {len(existing_tests)} existing test files and {len(missing)} likely missing test areas. "
            "No coverage percentage is claimed because no coverage report was provided."
        ),
        "existing_tests": existing_tests,
        "missing_test_areas": missing,
        "recommended_tests": recommended,
        "migration_regression_tests": migration_tests,
        "confidence": "High" if metadata.get("controllers") or metadata.get("services") else "Low",
    }


def run_test_strategy_agent(state: dict[str, Any]) -> dict[str, Any]:
    mark_step(state, "test_strategy_agent", "running")
    metadata = state.get("repo_metadata") or {}
    fallback = _fallback_test_strategy(metadata)
    retrieved_evidence = collect_rag_evidence(
        state,
        "test_strategy_agent",
        [
            "unit test integration test controller service test",
            "RestController RequestMapping GetMapping service business logic",
            "migration regression database configuration tests",
        ],
    )
    state["test_report"] = optional_bedrock_json(
        TEST_SYSTEM_PROMPT,
        {
            "repo_metadata": metadata,
            "retrieved_evidence": retrieved_evidence,
            "test_strategy": fallback,
        },
        fallback,
    )
    state["test_report"]["retrieved_evidence"] = retrieved_evidence
    mark_step(state, "test_strategy_agent", "completed")
    return state
