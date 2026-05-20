from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.agents.common import confidence_from_counts, mark_step, optional_bedrock_json
from app.agents.rag import collect_rag_evidence
from app.llm.prompts import ARCHITECTURE_SYSTEM_PROMPT


def _files(items: list[dict[str, Any]]) -> list[str]:
    return [item.get("file", "") for item in items if item.get("file")]


def _layer_for_file(file_path: str) -> str:
    lowered = file_path.lower()
    if "/controller/" in lowered:
        return "Controller/API"
    if "/service/" in lowered:
        return "Service"
    if "/repository/" in lowered or "/dao/" in lowered:
        return "Repository/DAO"
    if "/entity/" in lowered or "/model/" in lowered:
        return "Entity/Domain Model"
    return "Source"


def _coupling_analysis(metadata: dict[str, Any]) -> list[dict[str, str]]:
    analysis: list[dict[str, str]] = []
    couplings = sorted(
        metadata.get("component_couplings", []),
        key=lambda item: (
            0 if "/service/" in item.get("source_file", "").lower() else 1,
            item.get("source", ""),
            item.get("target", ""),
        ),
    )
    for coupling in couplings[:20]:
        source_file = coupling.get("source_file", "")
        target_file = coupling.get("target_file", "")
        source_layer = _layer_for_file(source_file)
        target_layer = _layer_for_file(target_file)
        impact = "Normal layered dependency."
        if source_layer == "Service" and target_layer in {"Service", "Repository/DAO"}:
            impact = "Business logic changes here can affect persistence or downstream workflows."
        if source_layer == "Controller/API" and target_layer != "Service":
            impact = "Controller reaches outside the service layer; review API-layer responsibility."
        analysis.append(
            {
                "source": coupling.get("source"),
                "target": coupling.get("target"),
                "relationship": coupling.get("relationship"),
                "evidence": f"{source_file}: {coupling.get('evidence', '')}",
                "impact": impact,
            }
        )
    return analysis


def _blast_radius(metadata: dict[str, Any]) -> list[dict[str, str]]:
    by_source: dict[str, list[dict[str, str]]] = defaultdict(list)
    for coupling in metadata.get("component_couplings", []):
        if coupling.get("source"):
            by_source[coupling["source"]].append(coupling)

    radius: list[dict[str, str]] = []
    for source, couplings in sorted(by_source.items()):
        distinct_targets = sorted({item.get("target", "") for item in couplings if item.get("target")})
        source_file = couplings[0].get("source_file", "")
        if "/service/" in source_file.lower() and len(distinct_targets) >= 3:
            radius.append(
                {
                    "component": source,
                    "risk": "High",
                    "reason": (
                        f"{source} depends on {', '.join(distinct_targets)}. "
                        "Changes to this service can ripple across multiple domains or persistence paths."
                    ),
                    "evidence": f"{source_file}: {couplings[0].get('evidence', '')}",
                }
            )

    for config_file in metadata.get("config_files", []):
        evidence = config_file.get("evidence", "")
        if "management." in evidence or "payment.provider" in evidence:
            radius.append(
                {
                    "component": config_file.get("file", "configuration"),
                    "risk": "Medium",
                    "reason": "Runtime configuration influences operational exposure and external integrations.",
                    "evidence": evidence,
                }
            )
    return radius


def _fallback_architecture(metadata: dict[str, Any]) -> dict[str, Any]:
    layers: list[dict[str, Any]] = []
    if metadata.get("controllers"):
        layers.append(
            {
                "name": "Controller/API",
                "files": _files(metadata["controllers"]),
                "responsibility": "Defines HTTP entry points and request mappings.",
            }
        )
    if metadata.get("services"):
        layers.append(
            {
                "name": "Service",
                "files": _files(metadata["services"]),
                "responsibility": "Holds business logic and application workflows.",
            }
        )
    if metadata.get("repositories"):
        layers.append(
            {
                "name": "Repository/DAO",
                "files": _files(metadata["repositories"]),
                "responsibility": "Handles persistence and database access.",
            }
        )
    if metadata.get("config_files"):
        layers.append(
            {
                "name": "Configuration",
                "files": _files(metadata["config_files"]),
                "responsibility": "Defines runtime configuration, framework settings, and integrations.",
            }
        )

    coupling_analysis = _coupling_analysis(metadata)
    blast_radius = _blast_radius(metadata)
    hotspot_text = ""
    if blast_radius:
        hotspot_text = f" {blast_radius[0].get('component')} is the clearest blast-radius hotspot."

    if metadata.get("controllers") and metadata.get("services") and metadata.get("repositories"):
        style = "layered_monolith"
        summary = (
            f"The repository is a {metadata.get('framework', 'unknown')} layered monolith with "
            "controller, service, repository, and configuration evidence."
            f"{hotspot_text}"
        )
    elif metadata.get("controllers") or metadata.get("services"):
        style = "modular_monolith"
        summary = "The repository has application modules, but full layer evidence is incomplete."
    else:
        style = "unknown"
        summary = "Not enough evidence found to classify the architecture."

    evidence = []
    for key in ("controllers", "services", "repositories", "config_files"):
        for item in metadata.get(key, [])[:6]:
            evidence.append({"file": item.get("file"), "evidence": item.get("evidence")})
    for coupling in metadata.get("component_couplings", [])[:8]:
        evidence.append(
            {
                "file": coupling.get("source_file"),
                "evidence": f"{coupling.get('source')} -> {coupling.get('target')}: {coupling.get('evidence')}",
            }
        )

    return {
        "architecture_summary": summary,
        "detected_style": style,
        "layers": layers,
        "api_inventory": metadata.get("api_inventory", []),
        "data_access": metadata.get("repositories", []) + metadata.get("entities", []),
        "external_integrations": metadata.get("detected_external_services", []),
        "coupling_analysis": coupling_analysis,
        "blast_radius": blast_radius,
        "architecture_concerns": [
            item.get("reason", "")
            for item in blast_radius
            if item.get("reason")
        ],
        "confidence": confidence_from_counts(len(layers), len(metadata.get("api_inventory", []))),
        "evidence": evidence,
    }


def run_architecture_agent(state: dict[str, Any]) -> dict[str, Any]:
    mark_step(state, "architecture_agent", "running")
    metadata = state.get("repo_metadata") or {}
    fallback = _fallback_architecture(metadata)
    retrieved_evidence = collect_rag_evidence(
        state,
        "architecture_agent",
        [
            "Spring controller service repository architecture routes",
            "configuration datasource external integration application properties",
            "service dependencies repository entity coupling",
        ],
    )
    report = optional_bedrock_json(
        ARCHITECTURE_SYSTEM_PROMPT,
        {
            "repo_metadata": metadata,
            "retrieved_evidence": retrieved_evidence,
            "fallback_schema": fallback,
        },
        fallback,
    )
    report["retrieved_evidence"] = retrieved_evidence
    state["architecture_report"] = report
    mark_step(state, "architecture_agent", "completed")
    return state
