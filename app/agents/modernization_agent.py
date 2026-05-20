from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from app.agents.common import mark_step, optional_bedrock_json
from app.agents.rag import collect_rag_evidence
from app.llm.prompts import MODERNIZATION_SYSTEM_PROMPT


def _domain_name(class_name: str) -> str:
    cleaned = re.sub(r"(Controller|Service|Repository|Entity)$", "", class_name)
    return cleaned or class_name


def _layer_name(file_path: str) -> str:
    lowered = file_path.lower()
    if "/controller/" in lowered:
        return "controller"
    if "/service/" in lowered:
        return "service"
    if "/repository/" in lowered or "/dao/" in lowered:
        return "repository"
    if "/entity/" in lowered or "/model/" in lowered:
        return "entity"
    return "source"


def _domain_evidence(metadata: dict[str, Any], files: set[str]) -> list[str]:
    evidence: list[str] = []
    for key in ("controllers", "services", "repositories", "entities"):
        for item in metadata.get(key, []):
            if item.get("file") in files and item.get("evidence"):
                evidence.append(f"{item.get('file')}: {item.get('evidence')}")
    return evidence[:5]


def _outside_domain_couplings(metadata: dict[str, Any], domain: str, files: set[str]) -> list[str]:
    outside: list[str] = []
    for coupling in metadata.get("component_couplings", []):
        if coupling.get("source_file") not in files:
            continue
        target = coupling.get("target", "")
        if target and _domain_name(target).lower() != domain.lower():
            outside.append(
                f"{coupling.get('source')} depends on {target} via {coupling.get('evidence')}"
            )
    return outside[:4]


def _cloud_review_opportunities(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    opportunities: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in metadata.get("detected_cloud_services", []):
        provider = item.get("provider", "cloud provider")
        service = item.get("service", "service")
        file_path = item.get("file", "")
        evidence = item.get("evidence", "")
        key = (provider, service)
        if key in seen:
            continue
        seen.add(key)

        if provider == "AWS" and service == "S3":
            action = (
                "AWS S3 integration was detected and should be reviewed for credentials, "
                "network access, SDK compatibility, and data ownership before any deployment change."
            )
        else:
            action = (
                f"{provider} {service} evidence was detected; review whether it is an application "
                "integration, deployment dependency, or portability concern before choosing a target platform."
            )

        opportunities.append(
            {
                "priority": "Medium",
                "title": f"Review detected {provider} {service} integration",
                "rationale": (
                    "Cloud-provider evidence comes from the uploaded repository. "
                    "It is integration context, not an automatic migration target."
                ),
                "action": action,
                "files": [file_path] if file_path else [],
                "evidence": evidence,
            }
        )
    return opportunities


def _fallback_modernization(state: dict[str, Any]) -> dict[str, Any]:
    metadata = state.get("repo_metadata") or {}
    architecture = state.get("architecture_report") or {}
    security = state.get("security_report") or {}
    dependency = state.get("dependency_report") or {}
    tests = state.get("test_report") or {}

    containerization_plan: list[dict[str, str]] = []
    ci_cd_plan: list[dict[str, str]] = []
    cloud_migration_plan: list[dict[str, str]] = []
    refactoring_opportunities: list[dict[str, Any]] = []

    ci_files = [item.get("file", "") for item in metadata.get("ci_cd_files", [])]
    if not any(file_name.endswith("Dockerfile") or file_name == "Dockerfile" for file_name in ci_files):
        containerization_plan.append(
            {
                "title": "Add production Dockerfile",
                "task": "Create a runtime Dockerfile after tests and configuration have been stabilized.",
                "evidence": "No Dockerfile was found in indexed CI/CD files.",
            }
        )
    if not any(".github/workflows" in file_name or "Jenkinsfile" in file_name for file_name in ci_files):
        ci_cd_plan.append(
            {
                "title": "Add CI pipeline",
                "task": "Add CI checks for static analysis, unit tests, dependency review, image build, and deployment gates.",
                "evidence": "No .github/workflows directory or Jenkinsfile was found in indexed files.",
            }
        )
    if security.get("findings"):
        cloud_migration_plan.append(
            {
                "title": "Externalize risky configuration",
                "task": "Move secrets and environment-specific settings to a managed secrets/configuration store before deployment.",
                "evidence": security["findings"][0].get("evidence", "Security findings exist."),
            }
        )
    if metadata.get("detected_databases"):
        cloud_migration_plan.append(
            {
                "title": "Plan managed database migration",
                "task": f"Assess migration path for detected databases: {', '.join(metadata.get('detected_databases', []))}.",
                "evidence": f"Detected database technologies: {', '.join(metadata.get('detected_databases', []))}.",
            }
        )

    for opportunity in _cloud_review_opportunities(metadata):
        cloud_migration_plan.append(
            {
                "title": opportunity["title"],
                "task": opportunity["action"],
                "evidence": opportunity["evidence"],
            }
        )
        refactoring_opportunities.append(opportunity)

    for item in architecture.get("blast_radius", [])[:3]:
        component = item.get("component", "component")
        is_config = "/" in component and not component.endswith(".java")
        action = (
            "Move environment-specific values behind typed configuration, add startup validation, and separate operational exposure from application defaults."
            if is_config
            else "Introduce explicit ports/interfaces around side effects and add regression tests before moving boundaries."
        )
        refactoring_opportunities.append(
            {
                "priority": item.get("risk", "Medium"),
                "title": f"Reduce {component} blast radius",
                "rationale": item.get("reason", "Component has multiple internal dependencies."),
                "action": action,
                "files": [component],
                "evidence": item.get("evidence", ""),
            }
        )

    if security.get("findings"):
        security_evidence = "; ".join(
            finding.get("evidence", "") for finding in security.get("findings", [])[:3] if finding.get("evidence")
        )
        refactoring_opportunities.append(
            {
                "priority": "High",
                "title": "Externalize and lock down runtime configuration",
                "rationale": "Security findings show deploy-time configuration and exposure risks that should be removed before containerization.",
                "action": "Move secrets and external URLs to environment-backed configuration, restrict actuator exposure, and validate config in startup tests.",
                "files": sorted({finding.get("file", "") for finding in security.get("findings", []) if finding.get("file")}),
                "evidence": security_evidence,
            }
        )

    if dependency.get("potential_risks"):
        refactoring_opportunities.append(
            {
                "priority": "Medium",
                "title": "Stage framework and driver upgrades behind regression tests",
                "rationale": "Dependency risks indicate an older framework or driver baseline.",
                "action": "Create an upgrade matrix, pin target versions, and run API/database regression tests at each step.",
                "files": sorted({risk.get("file", "") for risk in dependency.get("potential_risks", []) if risk.get("file")}),
                "evidence": "; ".join(
                    risk.get("evidence", "") for risk in dependency.get("potential_risks", [])[:3] if risk.get("evidence")
                ),
            }
        )

    if tests.get("missing_test_areas"):
        refactoring_opportunities.append(
            {
                "priority": "High",
                "title": "Add a regression harness around untested controllers and services",
                "rationale": "Modernization work is risky while API and service behavior lack matching tests.",
                "action": "Add controller tests for detected routes and unit tests for service failure paths before refactoring.",
                "files": [item.get("file", "") for item in tests.get("missing_test_areas", []) if item.get("file")],
                "evidence": "; ".join(
                    item.get("evidence", "") for item in tests.get("recommended_tests", [])[:3] if item.get("evidence")
                ),
            }
        )

    for plan_item in containerization_plan + ci_cd_plan:
        refactoring_opportunities.append(
            {
                "priority": "Medium",
                "title": plan_item.get("title"),
                "rationale": "The repo lacks the delivery artifact or pipeline needed for repeatable cloud migration.",
                "action": plan_item.get("task"),
                "files": [],
                "evidence": plan_item.get("evidence"),
            }
        )

    grouped: dict[str, set[str]] = defaultdict(set)
    for key in ("controllers", "services", "repositories", "entities"):
        for item in metadata.get(key, []):
            grouped[_domain_name(item.get("name", ""))].add(item.get("file", ""))

    candidates: list[dict[str, Any]] = []
    for domain, files in sorted(grouped.items()):
        files = {file for file in files if file}
        if len(files) >= 2:
            layers = sorted({_layer_name(file) for file in files})
            has_persistence = "repository" in layers or "entity" in layers
            has_controller = "controller" in layers
            has_service = "service" in layers
            outside = _outside_domain_couplings(metadata, domain, files)
            confidence = "High" if has_controller and has_service and has_persistence else "Low"
            if outside and confidence == "High":
                confidence = "Medium"
            risks = [
                "Boundary is advisory only; validate data ownership, transactions, and runtime coupling before extraction."
            ]
            if not has_persistence:
                risks.append("No repository/entity evidence was found, so data ownership is not established.")
            if outside:
                risks.append("Existing cross-domain dependencies must be untangled before extraction.")
            candidates.append(
                {
                    "name": f"{domain} Service Candidate",
                    "confidence": confidence,
                    "files": sorted(files),
                    "reasoning": (
                        f"Files share the {domain} domain across layers: {', '.join(layers)}. "
                        "Treat as a candidate only after validating transactions and ownership."
                    ),
                    "evidence": _domain_evidence(metadata, files),
                    "risks": risks,
                    "coupling_notes": outside,
                }
            )

    roadmap = [
        {
            "phase": "Phase 1",
            "title": "Stabilize and baseline",
            "tasks": [
                "Run human review of security/configuration findings.",
                "Add missing controller and service tests identified by the Test Strategy Agent.",
                "Create a dependency upgrade matrix.",
            ],
        },
        {
            "phase": "Phase 2",
            "title": "Externalize configuration and containerize",
            "tasks": [
                "Move secrets to a managed secrets/configuration service selected by the client.",
                "Build a reproducible Docker image and run it on the selected cloud or container platform.",
                "Add health checks and structured logs.",
            ],
        },
        {
            "phase": "Phase 3",
            "title": "Modernize incrementally",
            "tasks": [
                "Upgrade framework/runtime dependencies in small, tested steps.",
                "Introduce CI/CD gates and deployment rollback procedures.",
                "Evaluate candidate service boundaries after telemetry and domain review.",
            ],
        },
    ]

    risks = [
        "Static analysis cannot prove runtime behavior, dependency exploitability, or actual test coverage.",
        "Microservice candidates require human architecture review before any extraction work.",
    ]
    if dependency.get("potential_risks"):
        risks.append("Framework and dependency upgrades may require source changes and regression testing.")
    assumptions = [
        "Uploaded code is treated as untrusted input and was not executed.",
        "Dependency risk findings are modernization risks unless a vulnerability scanner is integrated.",
        "Static analysis does not assume a cloud provider; choose the target platform from client standards, compliance, networking, and repository evidence.",
    ]

    return {
        "containerization_plan": containerization_plan,
        "cloud_migration_plan": cloud_migration_plan,
        "refactoring_opportunities": refactoring_opportunities,
        "microservice_candidates": candidates[:6],
        "ci_cd_plan": ci_cd_plan,
        "phased_roadmap": roadmap,
        "risks": risks,
        "assumptions": assumptions,
    }


def run_modernization_agent(state: dict[str, Any]) -> dict[str, Any]:
    mark_step(state, "modernization_planner_agent", "running")
    fallback = _fallback_modernization(state)
    retrieved_evidence = collect_rag_evidence(
        state,
        "modernization_planner_agent",
        [
            "service controller repository entity domain boundary",
            "external integration datasource smtp payment provider configuration",
            "Dockerfile docker compose github workflow Jenkinsfile deployment",
        ],
    )
    plan = optional_bedrock_json(
        MODERNIZATION_SYSTEM_PROMPT,
        {
            "repo_metadata": state.get("repo_metadata"),
            "retrieved_evidence": retrieved_evidence,
            "architecture_report": state.get("architecture_report"),
            "dependency_report": state.get("dependency_report"),
            "security_report": state.get("security_report"),
            "test_report": state.get("test_report"),
            "modernization_plan": fallback,
        },
        fallback,
    )
    plan["containerization_plan"] = fallback.get("containerization_plan", [])
    plan["cloud_migration_plan"] = fallback.get("cloud_migration_plan", [])
    plan["ci_cd_plan"] = fallback.get("ci_cd_plan", [])
    plan["phased_roadmap"] = fallback.get("phased_roadmap", [])
    plan["risks"] = fallback.get("risks", [])
    plan["assumptions"] = fallback.get("assumptions", [])
    plan["refactoring_opportunities"] = fallback.get("refactoring_opportunities", [])
    plan["microservice_candidates"] = fallback.get("microservice_candidates", [])
    plan["retrieved_evidence"] = retrieved_evidence
    state["modernization_plan"] = plan
    mark_step(state, "modernization_planner_agent", "completed")
    return state
