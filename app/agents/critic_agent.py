from __future__ import annotations

from typing import Any

from app.agents.common import mark_step, optional_bedrock_json
from app.agents.rag import collect_rag_evidence
from app.llm.prompts import CRITIC_SYSTEM_PROMPT


def _weak_evidence(evidence: str | None) -> bool:
    text = (evidence or "").strip()
    lowered = text.lower()
    if not text:
        return True
    weak_prefixes = (
        "package ",
        "line 1: package ",
        "<project",
        "line 1: <project",
    )
    return lowered.startswith(weak_prefixes)


def _add_block(blocked: list[dict[str, str]], claim: str, reason: str, action: str) -> None:
    blocked.append({"claim": claim, "reason": reason, "action": action})


def _candidate_has_data_ownership(files: list[str]) -> bool:
    return any("/repository/" in file.lower() or "/entity/" in file.lower() or "/dao/" in file.lower() for file in files)


def _candidate_has_service(files: list[str]) -> bool:
    return any("/service/" in file.lower() for file in files)


def _fallback_critic(state: dict[str, Any]) -> dict[str, Any]:
    security = state.get("security_report") or {}
    architecture = state.get("architecture_report") or {}
    modernization = state.get("modernization_plan") or {}
    metadata = state.get("repo_metadata") or {}
    blocked: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    approved: list[str] = []

    for finding in security.get("findings", []):
        if not finding.get("file") or _weak_evidence(finding.get("evidence")):
            _add_block(
                blocked,
                finding.get("title", "Security finding"),
                "Security finding lacks specific file-level evidence.",
                "Remove from final report or mark as unsupported.",
            )
        else:
            approved.append(finding.get("title", "Security finding"))

    for concern in architecture.get("blast_radius", []):
        if _weak_evidence(concern.get("evidence")):
            _add_block(
                blocked,
                concern.get("component", "Architecture concern"),
                "Architecture blast-radius claim lacks concrete coupling evidence.",
                "Remove the concern or attach a source dependency line.",
            )
        else:
            approved.append(concern.get("component", "Architecture concern"))

    for opportunity in modernization.get("refactoring_opportunities", []):
        if not isinstance(opportunity, dict):
            _add_block(
                blocked,
                "Malformed refactoring opportunity",
                "Modernization Agent returned a refactoring item that was not structured evidence.",
                "Ignore the malformed item and keep only structured recommendations.",
            )
            continue
        if _weak_evidence(opportunity.get("evidence")):
            _add_block(
                blocked,
                opportunity.get("title", "Refactoring opportunity"),
                "Refactoring recommendation lacks concrete code/config/dependency evidence.",
                "Remove the recommendation or attach scanner evidence.",
            )
        else:
            approved.append(opportunity.get("title", "Refactoring opportunity"))

    for candidate in modernization.get("microservice_candidates", []):
        if not isinstance(candidate, dict):
            _add_block(
                blocked,
                "Malformed microservice candidate",
                "Modernization Agent returned a service candidate that was not structured evidence.",
                "Ignore the malformed item and keep only structured candidates.",
            )
            continue
        files = candidate.get("files") or []
        if not files:
            _add_block(
                blocked,
                candidate.get("name", "Microservice candidate"),
                "Suggested boundary does not reference concrete files or modules.",
                "Remove from final report or mark as speculative.",
            )
        elif not _candidate_has_service(files):
            _add_block(
                blocked,
                candidate.get("name", "Microservice candidate"),
                "Suggested boundary has no service-layer implementation evidence.",
                "Remove from final report or keep as a package inventory item.",
            )
        elif not _candidate_has_data_ownership(files):
            _add_block(
                blocked,
                candidate.get("name", "Microservice candidate"),
                "Suggested boundary has controller/service files but no repository, DAO, entity, or model evidence showing data ownership.",
                "Remove from microservice boundary list; keep as an integration refactoring item until ownership is proven.",
            )
        else:
            approved.append(candidate.get("name", "Microservice candidate"))
            if candidate.get("coupling_notes"):
                warnings.append(
                    {
                        "message": (
                            f"{candidate.get('name')} is evidence-backed but coupled outside its domain; "
                            "treat extraction as a later-phase candidate."
                        )
                    }
                )

    for warning in metadata.get("warnings", []):
        warnings.append(
            {
                "message": (
                    f"{warning.get('file')}: prompt-injection-like text '{warning.get('pattern')}' "
                    "was treated as untrusted repository content and ignored."
                )
            }
        )

    confidence = "Low" if blocked else "High" if approved else "Medium"
    return {
        "approved_claims": approved,
        "blocked_claims": blocked,
        "warnings": warnings,
        "required_report_edits": [
            item["action"] for item in blocked
        ],
        "overall_confidence": confidence,
    }


def run_critic_agent(state: dict[str, Any]) -> dict[str, Any]:
    mark_step(state, "critic_agent", "running")
    fallback = _fallback_critic(state)
    retrieved_evidence = collect_rag_evidence(
        state,
        "critic_agent",
        [
            "evidence for security findings files snippets",
            "microservice candidate service repository entity ownership evidence",
            "architecture coupling blast radius evidence source target dependency",
        ],
    )
    findings = optional_bedrock_json(
        CRITIC_SYSTEM_PROMPT,
        {
            "repo_metadata": state.get("repo_metadata"),
            "retrieved_evidence": retrieved_evidence,
            "architecture_report": state.get("architecture_report"),
            "dependency_report": state.get("dependency_report"),
            "security_report": state.get("security_report"),
            "test_report": state.get("test_report"),
            "modernization_plan": state.get("modernization_plan"),
            "critic_checks": fallback,
        },
        fallback,
    )
    findings["blocked_claims"] = fallback.get("blocked_claims", [])
    findings["required_report_edits"] = fallback.get("required_report_edits", [])
    findings["warnings"] = fallback.get("warnings", [])
    findings["overall_confidence"] = fallback.get("overall_confidence", findings.get("overall_confidence", "Medium"))
    findings["retrieved_evidence"] = retrieved_evidence
    state["critic_findings"] = findings
    mark_step(state, "critic_agent", "completed")
    return state
