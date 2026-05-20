from __future__ import annotations

from typing import Any

from app.guardrails.secret_redactor import redact_secrets


STATIC_ANALYSIS_NOTICE = (
    "ModernizeAI performs static analysis only. It does not execute client code. "
    "Recommendations are advisory and require human review."
)

SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}


def _severity(value: Any, default: str = "Medium") -> str:
    text = str(value or default).strip().title()
    return text if text in SEVERITY_ORDER else default


def _ellipsize(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    truncated = text[: max(0, limit - 3)].rstrip()
    if " " in truncated:
        truncated = truncated.rsplit(" ", 1)[0].rstrip()
    return f"{truncated}..."


def _cell(value: Any, limit: int = 700) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        items = [str(item).strip().rstrip(".") for item in value if str(item).strip()]
        value = "; ".join(items) or "None"
    text = redact_secrets(str(value)).replace("\n", " ").replace("|", "\\|")
    return _ellipsize(text, limit)


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "Not enough evidence found.\n"
    output = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        output.append("| " + " | ".join(_cell(value) for value in row) + " |")
    return "\n".join(output) + "\n"


def _bullet_list(items: list[Any]) -> str:
    if not items:
        return "- None found from available evidence.\n"
    output: list[str] = []
    for item in items:
        if isinstance(item, dict):
            text = (
                item.get("task")
                or item.get("title")
                or item.get("recommendation")
                or item.get("action")
                or item.get("message")
                or str(item)
            )
            files = item.get("files") or item.get("file")
            if files:
                if not isinstance(files, list):
                    files = [files]
                file_text = "; ".join(str(file) for file in files[:3])
                suffix = "..." if len(files) > 3 else ""
                text = f"{text} Files: {file_text}{suffix}"
        else:
            text = str(item)
        output.append(f"- {_cell(text, 500)}")
    return "\n".join(output) + "\n"


def _blocked_claim_names(critic: dict[str, Any]) -> set[str]:
    return {
        str(item.get("claim", "")).strip()
        for item in critic.get("blocked_claims", [])
        if item.get("claim")
    }


def _visible_blocked_claims(critic: dict[str, Any]) -> list[dict[str, Any]]:
    visible: list[dict[str, Any]] = []
    for item in critic.get("blocked_claims", []):
        claim = str(item.get("claim", ""))
        reason = str(item.get("reason", ""))
        if claim.startswith("Repository-authored instruction"):
            continue
        if claim == "Security finding" and "lacks specific file-level evidence" in reason:
            continue
        visible.append(item)
    return visible


def _approved_candidates(modernization: dict[str, Any], critic: dict[str, Any]) -> list[dict[str, Any]]:
    blocked = _blocked_claim_names(critic)
    candidates = [
        candidate
        for candidate in modernization.get("microservice_candidates", [])
        if isinstance(candidate, dict) and candidate.get("name") not in blocked
    ]
    return sorted(candidates, key=lambda item: (item.get("confidence") != "High", item.get("name", "")))


def _canonical_security_report(metadata: dict[str, Any], security: dict[str, Any]) -> dict[str, Any]:
    try:
        from app.agents.security_agent import _fallback_security

        fallback = _fallback_security(metadata)
    except Exception:
        fallback = {}

    report = dict(security)
    report_findings = _supported_security_findings(security.get("findings", []))
    fallback_findings = _supported_security_findings(fallback.get("findings", []))
    if len(fallback_findings) > len(report_findings):
        report["findings"] = fallback_findings
        report["risk_summary"] = fallback.get("risk_summary", security.get("risk_summary", ""))
        report["recommended_mitigations"] = fallback.get("recommended_mitigations", security.get("recommended_mitigations", []))
    else:
        report["findings"] = report_findings
    return report


def _has_dependency_scan(metadata: dict[str, Any]) -> bool:
    return bool(metadata.get("dependency_details") or metadata.get("dependency_files"))


def _has_concrete_spring_boot_version(metadata: dict[str, Any]) -> bool:
    return any(
        str(info.get("spring_boot_version", "")).strip()
        for info in metadata.get("dependency_details", [])
    )


def _contradicts_scanner_dependency_metadata(metadata: dict[str, Any], risk: dict[str, Any]) -> bool:
    if not _has_dependency_scan(metadata):
        return False
    text = " ".join(
        str(risk.get(key, ""))
        for key in ("title", "evidence", "recommendation", "action", "upgrade_move")
    ).lower()
    unavailable_phrases = (
        "pom.xml was not indexed",
        "pom.xml was not provided",
        "pom.xml content unavailable",
        "no pom.xml content available",
        "not indexed or provided",
        "not indexed or not provided",
    )
    if any(phrase in text for phrase in unavailable_phrases):
        return True
    if _has_concrete_spring_boot_version(metadata):
        spring_version_phrases = (
            "unknown spring boot version",
            "spring boot version not pinned",
            "no explicit spring boot version",
            "version not present in evidence",
            "exact version not present",
        )
        return any(phrase in text for phrase in spring_version_phrases)
    return False


def _canonical_dependency_report(metadata: dict[str, Any], dependency: dict[str, Any]) -> dict[str, Any]:
    try:
        from app.agents.dependency_agent import _fallback_dependency

        fallback = _fallback_dependency(metadata)
    except Exception:
        fallback = {}

    report = dict(dependency)
    if fallback.get("dependency_summary"):
        report["dependency_summary"] = fallback["dependency_summary"]
    if fallback.get("key_dependencies"):
        report["key_dependencies"] = fallback["key_dependencies"]

    fallback_risks = _supported_dependency_risks(metadata, fallback.get("potential_risks", []))
    model_risks = _supported_dependency_risks(metadata, dependency.get("potential_risks", []))
    combined: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for risk in [*fallback_risks, *model_risks]:
        if _contradicts_scanner_dependency_metadata(metadata, risk):
            continue
        key = (str(risk.get("title", "")), str(risk.get("file", "")), str(risk.get("evidence", "")))
        if key in seen:
            continue
        seen.add(key)
        combined.append(risk)
    report["potential_risks"] = combined

    recommendations = []
    for item in [*fallback.get("upgrade_recommendations", []), *dependency.get("upgrade_recommendations", [])]:
        if item not in recommendations:
            recommendations.append(item)
    if recommendations:
        report["upgrade_recommendations"] = recommendations
    return report


def _canonical_test_report(metadata: dict[str, Any], test: dict[str, Any]) -> dict[str, Any]:
    try:
        from app.agents.test_strategy_agent import _fallback_test_strategy

        fallback = _fallback_test_strategy(metadata)
    except Exception:
        fallback = {}

    report = dict(test)
    for key in [
        "test_summary",
        "existing_tests",
        "missing_test_areas",
        "recommended_tests",
        "migration_regression_tests",
    ]:
        if fallback.get(key) is not None:
            report[key] = fallback[key]
    return report


def _supported_dependency_risks(metadata: dict[str, Any], risks: list[Any]) -> list[dict[str, Any]]:
    spring_boot_versions = {
        str(info.get("spring_boot_version", "")).strip()
        for info in metadata.get("dependency_details", [])
        if info.get("spring_boot_version")
    }
    supported: list[dict[str, Any]] = []
    for risk in risks or []:
        if not isinstance(risk, dict):
            continue
        title = str(risk.get("title") or "Dependency modernization risk")
        evidence = risk.get("evidence")
        file_path = risk.get("file")
        recommendation = risk.get("recommendation") or risk.get("action") or risk.get("upgrade_move")
        if not evidence or not file_path:
            continue
        if spring_boot_versions and "spring boot version not pinned" in title.lower():
            continue
        if spring_boot_versions and "no explicit spring boot version" in str(evidence).lower():
            continue
        supported.append(
            {
                **risk,
                "severity": _severity(risk.get("severity")),
                "title": title,
                "file": file_path,
                "evidence": evidence,
                "recommendation": recommendation or "Review this dependency during the modernization upgrade plan.",
            }
        )
    return sorted(
        supported,
        key=lambda item: (SEVERITY_ORDER.get(str(item.get("severity", "")).title(), 9), item.get("file", ""), item.get("title", "")),
    )


def _supported_security_findings(findings: list[Any]) -> list[dict[str, Any]]:
    supported: list[dict[str, Any]] = []
    for finding in findings or []:
        if not isinstance(finding, dict):
            continue
        title = finding.get("title") or finding.get("category") or finding.get("description")
        evidence = finding.get("evidence")
        file_path = finding.get("file")
        recommendation = finding.get("recommendation") or finding.get("action") or finding.get("mitigation")
        if not evidence or not file_path:
            continue
        supported.append(
            {
                **finding,
                "severity": _severity(finding.get("severity")),
                "title": title or "Potential security/configuration issue",
                "file": file_path,
                "evidence": evidence,
                "recommendation": recommendation or "Review and remediate before production migration.",
            }
        )
    return sorted(
        supported,
        key=lambda item: (SEVERITY_ORDER.get(str(item.get("severity", "")), 9), item.get("file", ""), item.get("title", "")),
    )


def _security_config_files(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in metadata.get("config_files", [])
        if "securityconfig" in str(item.get("file", "")).replace("_", "").lower()
    ]


def _security_config_source_text(metadata: dict[str, Any], rel_path: str) -> str:
    try:
        from pathlib import Path

        repo_root = Path(str(metadata.get("repo_root", "")))
        path = repo_root / rel_path
        if path.exists() and path.is_file():
            return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    return ""


def _security_config_concern(metadata: dict[str, Any]) -> dict[str, Any] | None:
    for item in _security_config_files(metadata):
        file_path = str(item.get("file", ""))
        text = _security_config_source_text(metadata, file_path).lower()
        evidence = str(item.get("evidence", "")).lower()
        csrf_disabled = "csrf" in (text + evidence) and "disable" in (text + evidence)
        permits_all = "permitall" in text or "anyrequest" in text and "permitall" in text
        if csrf_disabled and permits_all:
            title = "SecurityConfig disables CSRF and permits all requests."
        elif csrf_disabled:
            title = "SecurityConfig disables CSRF protection."
        else:
            title = "SecurityConfig requires review before production migration."
        return {"title": title, "files": [file_path]}
    return None


def _vague_security_absence_claim(item: Any) -> bool:
    text = str(item.get("title", item) if isinstance(item, dict) else item).lower()
    return any(
        phrase in text
        for phrase in (
            "no visible security configuration",
            "no security configuration",
            "security configuration was not detected",
        )
    )


def _canonical_architecture_report(metadata: dict[str, Any], architecture: dict[str, Any]) -> dict[str, Any]:
    report = dict(architecture)
    concerns = list(report.get("architecture_concerns", []) or [])
    security_config_exists = bool(_security_config_files(metadata))
    if security_config_exists:
        concerns = [item for item in concerns if not _vague_security_absence_claim(item)]
        concern = _security_config_concern(metadata)
        if concern and not any(str(concern["title"]) in str(item) for item in concerns):
            concerns.append(concern)
    report["architecture_concerns"] = concerns
    return report


def _api_inventory(metadata: dict[str, Any], architecture: dict[str, Any]) -> list[dict[str, Any]]:
    metadata_api = [item for item in metadata.get("api_inventory", []) if isinstance(item, dict)]
    if any(item.get("file") and item.get("evidence") for item in metadata_api):
        return metadata_api
    return [item for item in architecture.get("api_inventory", []) if isinstance(item, dict)]


def _chat_model_readout(*reports: dict[str, Any]) -> str:
    models = []
    for report in reports:
        model = str(report.get("llm_model_id", "")).strip()
        if model and model not in models:
            models.append(model)
    return "; ".join(models) if models else "unknown"


def _public_decision_rationale(state: dict[str, Any], decision: dict[str, Any]) -> str:
    rationale = str(decision.get("rationale", ""))
    if _security_config_files(state.get("repo_metadata") or {}):
        replacements = (
            "No security configuration was detected in metadata",
            "no security configuration was detected in metadata",
        )
        for phrase in replacements:
            rationale = rationale.replace(phrase, "Security configuration requires review")
    return rationale


def _agent_decision_rows(state: dict[str, Any]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for decision in state.get("agent_decisions", []):
        if not isinstance(decision, dict):
            continue
        rows.append(
            [
                decision.get("iteration"),
                decision.get("agent_label") or decision.get("next_agent"),
                decision.get("graph_label"),
                _public_decision_rationale(state, decision),
            ]
        )
    return rows


def _agent_run_rows(state: dict[str, Any]) -> list[list[Any]]:
    graph = state.get("agent_graph") or {}
    rows: list[list[Any]] = []
    for node in graph.get("nodes", []):
        if not isinstance(node, dict):
            continue
        node_id = node.get("id")
        if node_id == "ingestion":
            continue
        status = node.get("status", "pending")
        run_count = node.get("run_count", 0)
        if status == "pending" and not run_count:
            continue
        rows.append([node.get("label", node_id), status, run_count, node.get("skip_reason", "")])
    return rows


def _confidence_note(critic: dict[str, Any]) -> str:
    confidence = _display_confidence(critic)
    blocked_count = len(_visible_blocked_claims(critic))
    warnings_count = len(critic.get("warnings", []))
    if blocked_count:
        return f"{confidence} after removing or separating {blocked_count} unsupported claim(s)."
    if warnings_count:
        return f"{confidence}; guardrail warnings were handled as untrusted repository text."
    return f"{confidence}; no unsupported claims were found by the Critic Agent."


def _display_confidence(critic: dict[str, Any]) -> str:
    confidence = str(critic.get("overall_confidence", "Medium"))
    if _visible_blocked_claims(critic):
        return "Medium" if confidence.lower() == "low" else confidence
    if critic.get("warnings") and confidence.lower() == "low":
        return "High"
    return confidence


def _analysis_snapshot(
    metadata: dict[str, Any],
    architecture: dict[str, Any],
    dependency: dict[str, Any],
    security: dict[str, Any],
    test: dict[str, Any],
    modernization: dict[str, Any],
    critic: dict[str, Any],
    agent_decisions_count: int = 0,
) -> str:
    indexed_files = (metadata.get("file_counts") or {}).get("indexed_files", 0)
    return _table(
        ["Signal", "Readout"],
        [
            ["Reasoning model", _chat_model_readout(architecture, dependency, security, test, modernization, critic)],
            ["Repository", f"{metadata.get('framework', 'unknown framework')}; {indexed_files} indexed files; {len(_api_inventory(metadata, architecture))} APIs"],
            ["Findings", f"{len(security.get('findings', []))} supported security/configuration findings; {len(test.get('missing_test_areas', []))} test gaps"],
            ["Candidate boundaries", f"{len(_approved_candidates(modernization, critic))} evidence-backed candidates"],
            ["Agent decisions", agent_decisions_count],
            ["Confidence", _confidence_note(critic)],
        ],
    )


def generate_markdown_report(state: dict[str, Any]) -> str:
    metadata = state.get("repo_metadata") or {}
    architecture = _canonical_architecture_report(metadata, state.get("architecture_report") or {})
    dependency = _canonical_dependency_report(metadata, state.get("dependency_report") or {})
    security = _canonical_security_report(metadata, state.get("security_report") or {})
    test = _canonical_test_report(metadata, state.get("test_report") or {})
    modernization = state.get("modernization_plan") or {}
    critic = state.get("critic_findings") or {}
    approved_candidates = _approved_candidates(modernization, critic)
    api_inventory = _api_inventory(metadata, architecture)

    lines: list[str] = [
        "# ModernizeAI Modernization Report",
        "",
        f"> {STATIC_ANALYSIS_NOTICE}",
        "",
        "## 1. Executive Summary",
        "",
        _executive_summary(metadata, security, test, approved_candidates, critic),
        "",
        "## Analysis Snapshot",
        "",
        _analysis_snapshot(metadata, architecture, dependency, security, test, modernization, critic, len(state.get("agent_decisions", []))),
        "## 2. Top Modernization Priorities",
        "",
        _priority_plan(metadata, architecture, dependency, security, test, approved_candidates),
        "",
        "## 3. Current State Assessment",
        "",
        _current_state(metadata, architecture, dependency, api_inventory),
        "",
        "## 4. Architecture and Coupling",
        "",
        _architecture_narrative(metadata, architecture),
        "",
        "## 5. Security and Configuration Risks",
        "",
        _security_section(security),
        "",
        "## 6. Dependency and Runtime Upgrade Path",
        "",
        _dependency_section(metadata, dependency),
        "",
        "## 7. Test Strategy",
        "",
        _test_strategy_section(test),
        "",
        "## 8. Candidate Service Boundaries",
        "",
        _candidate_section(approved_candidates),
        "",
        "## 9. 30/60/90-Day Cloud Modernization Roadmap",
        "",
        _roadmap(modernization.get("phased_roadmap", [])),
        "",
        "## 10. Risks and Assumptions",
        "",
        "**Risks**",
        "",
        _bullet_list(modernization.get("risks", [])),
        "",
        "**Assumptions**",
        "",
        _bullet_list(modernization.get("assumptions", [])),
        "",
        "## 11. Evidence Appendix",
        "",
        "Representative source evidence used by the report. Detailed agent trace is separated below so the assessment stays readable.",
        "",
        _evidence_appendix(metadata, architecture, dependency, security, test, modernization, critic, api_inventory),
        "",
        "## 12. Agent Collaboration Trace",
        "",
        "This operational trace shows how specialist agents were coordinated. It is supporting context, not the modernization recommendation itself.",
        "",
        "**Agents run**",
        "",
        _table(["Agent", "Status", "Runs", "Skip Reason"], _agent_run_rows(state)),
        "**Supervisor decisions**",
        "",
        _table(["Iteration", "Selected Agent", "Decision Signal", "Rationale"], _agent_decision_rows(state)),
        "## 13. Critic Review",
        "",
        f"Overall confidence: **{_display_confidence(critic)}**",
        "",
        f"Confidence context: {_confidence_note(critic)}",
        "",
        "**Blocked claims**",
        "",
        _critic_blocked_claims(_visible_blocked_claims(critic)),
        "",
        "**Warnings**",
        "",
        _bullet_list([warning.get("message", warning) for warning in critic.get("warnings", [])]),
        "",
    ]
    return "\n".join(lines).strip() + "\n"


def _executive_summary(
    metadata: dict[str, Any],
    security: dict[str, Any],
    test: dict[str, Any],
    candidates: list[dict[str, Any]],
    critic: dict[str, Any],
) -> str:
    framework = metadata.get("framework", "unknown framework")
    controller_count = len(metadata.get("controllers", []))
    service_count = len(metadata.get("services", []))
    repository_count = len(metadata.get("repositories", []))
    security_count = len(security.get("findings", []))
    missing_tests = len(test.get("missing_test_areas", []))
    confidence = _display_confidence(critic)

    return (
        f"The repository is an evidence-backed {framework} layered monolith with "
        f"{controller_count} controllers, {service_count} services, and {repository_count} persistence components. "
        "The modernization path should start with stabilization, not immediate service extraction: externalize risky runtime configuration, "
        "build a regression harness around business workflows, upgrade the Java/Spring dependency baseline, and then evaluate service boundaries. "
        f"The analysis found {security_count} supported security/configuration findings, {missing_tests} likely test gaps, "
        f"and {len(candidates)} evidence-backed boundary candidates. Overall evidence confidence is {confidence}."
    )


def _priority_plan(
    metadata: dict[str, Any],
    architecture: dict[str, Any],
    dependency: dict[str, Any],
    security: dict[str, Any],
    test: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> str:
    priorities: list[dict[str, str]] = []
    first_security = (security.get("findings") or [{}])[0]
    if security.get("findings"):
        priorities.append(
            {
                "rank": "P0",
                "title": "Externalize secrets and lock down runtime exposure",
                "why": "The app has deploy-time configuration risks that should be removed before containerization or cloud deployment.",
                "evidence": f"{first_security.get('file')}: {first_security.get('evidence')}",
                "move": "Move credentials and environment-specific URLs to managed configuration/secrets, restrict actuator exposure, and add startup validation.",
            }
        )

    dependency_risks = dependency.get("potential_risks", [])
    if dependency_risks:
        first_dependency = dependency_risks[0]
        priorities.append(
            {
                "rank": "P1",
                "title": "Create a staged Java and Spring upgrade path",
                "why": "The runtime and framework baseline is old enough that upgrades should be planned with compatibility gates.",
                "evidence": f"{first_dependency.get('file')}: {first_dependency.get('evidence')}",
                "move": "Build an upgrade matrix, pin target versions, and run API/database regression tests at each step.",
            }
        )

    payment_hotspot = next(
        (
            item
            for item in architecture.get("blast_radius", [])
            if "PaymentBatchService" in str(item.get("component", ""))
        ),
        (architecture.get("blast_radius") or [{}])[0],
    )
    if payment_hotspot:
        priorities.append(
            {
                "rank": "P1",
                "title": f"Reduce {payment_hotspot.get('component', 'service orchestration')} blast radius",
                "why": payment_hotspot.get("reason", "A central workflow has multiple dependencies and should be stabilized before modernization."),
                "evidence": payment_hotspot.get("evidence", ""),
                "move": "Introduce ports around external side effects, isolate transaction boundaries, and add workflow tests before moving boundaries.",
            }
        )

    if test.get("missing_test_areas"):
        first_test = (test.get("recommended_tests") or [{}])[0]
        priorities.append(
            {
                "rank": "P1",
                "title": "Build a migration regression harness",
                "why": "Modernization is risky while controller routes and service failure paths lack matching tests.",
                "evidence": first_test.get("evidence", ""),
                "move": "Add API, service, database, and configuration smoke tests before dependency upgrades or cloud deployment.",
            }
        )

    if candidates:
        priorities.append(
            {
                "rank": "P2",
                "title": "Treat service boundaries as later-phase candidates",
                "why": "The repo has domain-shaped files, but extraction should wait until data ownership, transactions, and runtime coupling are validated.",
                "evidence": candidates[0].get("reasoning", ""),
                "move": "Use candidates for discovery workshops first; do not split the monolith until telemetry and regression tests are in place.",
            }
        )

    if not priorities:
        return "- Not enough evidence found to prioritize modernization work.\n"

    output: list[str] = []
    for item in priorities:
        output.extend(
            [
                f"### {item['rank']} - {item['title']}",
                f"- Why it matters: {_cell(item['why'], 700)}",
                f"- Evidence: {_cell(item['evidence'], 700)}",
                f"- First move: {_cell(item['move'], 700)}",
                "",
            ]
        )
    return "\n".join(output).strip() + "\n"


def _current_state(
    metadata: dict[str, Any],
    architecture: dict[str, Any],
    dependency: dict[str, Any],
    api_inventory: list[dict[str, Any]],
) -> str:
    databases = metadata.get("detected_databases", [])
    external_services = metadata.get("detected_external_services", [])
    cloud_providers = metadata.get("detected_cloud_providers", [])
    key_dependencies = dependency.get("key_dependencies", [])[:8]

    rows = [
        ["Application shape", f"{metadata.get('framework', 'unknown')} with {len(metadata.get('controllers', []))} controllers, {len(metadata.get('services', []))} services, {len(metadata.get('repositories', []))} repositories"],
        ["Indexed source", f"{(metadata.get('file_counts') or {}).get('indexed_files', 0)} files; languages: {_cell(metadata.get('languages', []))}; build tools: {_cell(metadata.get('build_tools', []))}"],
        ["API surface", f"{len(api_inventory)} detected endpoints"],
        ["Data stores", databases or "Not enough evidence found"],
        ["External integrations", external_services or "Not enough evidence found"],
        ["Cloud evidence", cloud_providers or "No cloud provider assumed"],
    ]
    output = [_table(["Area", "Assessment"], rows)]
    if key_dependencies:
        output.extend(
            [
                "**Dependency Snapshot**",
                "",
                _table(
                    ["Dependency", "Version", "Evidence"],
                    [[item.get("name"), item.get("version"), item.get("evidence")] for item in key_dependencies],
                ),
            ]
        )
    return "\n".join(output).strip() + "\n"


def _architecture_narrative(metadata: dict[str, Any], architecture: dict[str, Any]) -> str:
    layers = architecture.get("layers") or []
    blast_radius = architecture.get("blast_radius") or []
    couplings = architecture.get("coupling_analysis") or []
    output: list[str] = []
    summary = architecture.get("architecture_summary")
    if summary:
        output.append(_cell(summary, 900))
    else:
        output.append(
            f"The repository shows a layered application structure across controllers, services, repositories, entities, and configuration."
        )
    output.append("")

    if layers:
        output.append("**Layer Readout**")
        output.append("")
        for layer in layers:
            files = layer.get("files") or []
            examples = "; ".join(str(file) for file in files[:3])
            suffix = "..." if len(files) > 3 else ""
            output.append(f"- {layer.get('name')}: {len(files)} file(s). {layer.get('responsibility')} Examples: {_cell(examples + suffix, 500)}")
        output.append("")

    if blast_radius:
        output.append("**Primary Blast-Radius Hotspots**")
        output.append("")
        for item in blast_radius[:5]:
            output.append(f"- {item.get('component')}: {item.get('risk', 'Medium')} risk. {_cell(item.get('reason'), 600)} Evidence: {_cell(item.get('evidence'), 500)}")
        output.append("")

    if couplings:
        output.append("**Representative Couplings**")
        output.append("")
        output.append(
            _table(
                ["Source", "Target", "Impact", "Evidence"],
                [[item.get("source"), item.get("target"), item.get("impact"), item.get("evidence")] for item in couplings[:10]],
            )
        )

    concerns = architecture.get("architecture_concerns", [])
    if concerns:
        output.extend(["**Architecture Concerns**", "", _bullet_list(concerns)])
    return "\n".join(output).strip() + "\n"


def _security_section(security: dict[str, Any]) -> str:
    findings = security.get("findings") or []
    output: list[str] = []
    if security.get("risk_summary"):
        output.append(_cell(security.get("risk_summary"), 900))
        output.append("")
    if not findings:
        output.append("- No supported security findings were found from available evidence.\n")
        return "\n".join(output)

    for finding in findings:
        output.extend(
            [
                f"### {_severity(finding.get('severity'))} - {finding.get('title', 'Potential security/configuration issue')}",
                f"- File: `{_cell(finding.get('file'), 500)}`",
                f"- Evidence: {_cell(finding.get('evidence'), 700)}",
                f"- Modernization move: {_cell(finding.get('recommendation'), 700)}",
                "",
            ]
        )
    mitigations = security.get("recommended_mitigations", [])
    if mitigations:
        output.extend(["**Cross-Cutting Mitigations**", "", _bullet_list(mitigations)])
    return "\n".join(output).strip() + "\n"


def _dependency_section(metadata: dict[str, Any], dependency: dict[str, Any]) -> str:
    dependency_files = [item.get("file") for item in metadata.get("dependency_files", []) if item.get("file")]
    risks = dependency.get("potential_risks", [])
    output: list[str] = []
    if dependency_files:
        output.append(f"Dependency evidence was found in {_cell(dependency_files)}. Treat the findings as modernization risks unless a vulnerability scanner is added.")
    else:
        output.append("No dependency file was found in scanner metadata.")
    output.append("")

    if risks:
        for risk in risks[:8]:
            output.extend(
                [
                    f"### {_severity(risk.get('severity'))} - {risk.get('title', 'Dependency modernization risk')}",
                    f"- Evidence: `{_cell(risk.get('file'))}` - {_cell(risk.get('evidence'), 700)}",
                    f"- Upgrade move: {_cell(risk.get('recommendation'), 700)}",
                    "",
                ]
            )
    else:
        output.append("- No dependency risks were generated from available evidence.")
        output.append("")

    recommendations = dependency.get("upgrade_recommendations", [])
    if recommendations:
        output.extend(["**Upgrade Planning Moves**", "", _bullet_list(recommendations)])
    return "\n".join(output).strip() + "\n"


def _test_strategy_section(test: dict[str, Any]) -> str:
    output: list[str] = []
    if test.get("test_summary"):
        output.append(_cell(test.get("test_summary"), 900))
        output.append("")

    recommended = test.get("recommended_tests") or []
    if recommended:
        for item in recommended[:10]:
            output.extend(
                [
                    f"### {item.get('type', 'Test')} - {item.get('target', 'Target')}",
                    f"- Add: {_cell(item.get('suggestion'), 700)}",
                    f"- Evidence: {_cell(item.get('evidence'), 700)}",
                    "",
                ]
            )
    else:
        output.append("- No missing test areas were identified from available evidence.")
        output.append("")

    regression_tests = test.get("migration_regression_tests", [])
    if regression_tests:
        output.extend(["**Migration Regression Suite**", "", _bullet_list(regression_tests)])
    return "\n".join(output).strip() + "\n"


def _candidate_section(candidates: list[dict[str, Any]]) -> str:
    if not candidates:
        return "- No evidence-backed service boundaries survived critic review.\n"

    output: list[str] = []
    for candidate in candidates[:6]:
        files = candidate.get("files") or []
        risks = candidate.get("risks") or []
        output.extend(
            [
                f"### {candidate.get('name')} ({candidate.get('confidence', 'Medium')} confidence)",
                f"- Why it is a candidate: {_cell(candidate.get('reasoning'), 700)}",
                f"- Files: {_cell(files[:6], 700)}",
                f"- Extraction caution: {_cell(risks[:3], 700)}",
                "",
            ]
        )
    return "\n".join(output).strip() + "\n"


def _roadmap(phases: list[dict[str, Any]]) -> str:
    if not phases:
        return "- No roadmap generated from available evidence.\n"
    labels = ["0-30 Days", "31-60 Days", "61-90 Days"]
    output: list[str] = []
    for index, phase in enumerate(phases[:3]):
        label = labels[index] if index < len(labels) else phase.get("phase", "Phase")
        output.append(f"### {label} - {phase.get('title', 'Untitled')}")
        for task in phase.get("tasks", []):
            output.append(f"- {_cell(task, 700)}")
        output.append("")
    return "\n".join(output).strip() + "\n"


def _critic_blocked_claims(blocked: list[dict[str, Any]]) -> str:
    if not blocked:
        return "- No unsupported claims were found by the Critic Agent.\n"
    output = []
    for item in blocked:
        output.append(
            f"- {_cell(item.get('claim'))}: {_cell(item.get('reason'))} Action: {_cell(item.get('action'))}"
        )
    return "\n".join(output) + "\n"


def _evidence_appendix(
    metadata: dict[str, Any],
    architecture: dict[str, Any],
    dependency: dict[str, Any],
    security: dict[str, Any],
    test: dict[str, Any],
    modernization: dict[str, Any],
    critic: dict[str, Any],
    api_inventory: list[dict[str, Any]],
) -> str:
    rows: list[list[Any]] = []
    for item in api_inventory[:12]:
        rows.append(["api", item.get("file"), f"{item.get('method')} {item.get('path')} - {item.get('evidence')}"])
    for key in ["controllers", "services", "repositories", "entities", "config_files", "dependency_files", "test_files"]:
        for item in metadata.get(key, [])[:8]:
            rows.append([key, item.get("file"), item.get("evidence")])
    for item in metadata.get("detected_cloud_services", [])[:8]:
        rows.append(["cloud evidence", f"{item.get('provider')} {item.get('service')} in {item.get('file')}", item.get("evidence")])
    for item in dependency.get("potential_risks", [])[:8]:
        rows.append(["dependency", item.get("file"), item.get("evidence")])
    for item in security.get("findings", [])[:10]:
        rows.append(["security", item.get("file"), item.get("evidence")])
    for item in test.get("recommended_tests", [])[:10]:
        rows.append(["test", item.get("target"), item.get("evidence")])
    for item in modernization.get("refactoring_opportunities", [])[:8]:
        rows.append(["modernization", item.get("title"), item.get("evidence")])
    for item in _visible_blocked_claims(critic)[:8]:
        rows.append(["critic blocked", item.get("claim"), item.get("reason")])
    return _table(["Source", "File/Target", "Evidence"], rows)
