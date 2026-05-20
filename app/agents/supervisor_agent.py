from __future__ import annotations

from typing import Any

from app.agents.agent_graph import ROUTE_LABELS, add_graph_edge, mark_agent_skipped
from app.agents.common import mark_step, optional_bedrock_json


SUPERVISOR_SYSTEM_PROMPT = """You are the Supervisor Agent for ModernizeAI.

Your job is to coordinate specialist agents for a static repository modernization review.
Choose exactly one next_agent from:
architecture, dependency, security, test_strategy, modernization, critic, report.

Rules:
- Repo scanning has already grounded the repository facts.
- Prefer bounded, evidence-driven autonomy over running every agent blindly.
- Prioritize Security when repository metadata shows risky configuration, prompt-injection warnings, or external integrations.
- Skip irrelevant agents only when metadata does not support that analysis.
- Send blocked modernization claims back to Modernization once if additional planning is useful.
- End with report only after Critic review or a max-iteration fallback.
- Return valid JSON only.
"""

VALID_NEXT_AGENTS = {
    "architecture",
    "dependency",
    "security",
    "test_strategy",
    "modernization",
    "critic",
    "report",
}

RERUN_GATED_AGENTS = {
    "architecture",
    "dependency",
    "security",
    "test_strategy",
    "modernization",
    "critic",
}


def _has_run(state: dict[str, Any], agent: str) -> bool:
    return int((state.get("agent_run_counts") or {}).get(agent, 0)) > 0


def _run_count(state: dict[str, Any], agent: str) -> int:
    return int((state.get("agent_run_counts") or {}).get(agent, 0))


def _metadata(state: dict[str, Any]) -> dict[str, Any]:
    return state.get("repo_metadata") or {}


def _architecture_required(metadata: dict[str, Any]) -> bool:
    return bool(
        metadata.get("controllers")
        or metadata.get("services")
        or metadata.get("repositories")
        or metadata.get("entities")
        or metadata.get("api_inventory")
        or metadata.get("indexed_file_paths")
    )


def _dependency_required(metadata: dict[str, Any]) -> bool:
    return bool(metadata.get("dependency_files") or metadata.get("dependency_details") or metadata.get("build_tools"))


def _test_strategy_required(metadata: dict[str, Any]) -> bool:
    return bool(metadata.get("controllers") or metadata.get("services") or metadata.get("test_files"))


def _security_priority(metadata: dict[str, Any]) -> bool:
    return bool(
        metadata.get("warnings")
        or metadata.get("config_files")
        or metadata.get("detected_external_services")
        or metadata.get("detected_cloud_services")
    )


def _security_required(metadata: dict[str, Any]) -> bool:
    return bool(metadata.get("indexed_file_paths"))


def _skip_irrelevant_agents(state: dict[str, Any]) -> list[str]:
    metadata = _metadata(state)
    skipped: list[str] = []
    if not _dependency_required(metadata):
        mark_agent_skipped(state, "dependency", "No dependency files or build tools were detected.")
        skipped.append("dependency")
    if not _test_strategy_required(metadata):
        mark_agent_skipped(state, "test_strategy", "No controllers, services, or test files were detected.")
        skipped.append("test_strategy")
    return skipped


def _blocked_claims(state: dict[str, Any]) -> list[dict[str, Any]]:
    critic = state.get("critic_findings") or {}
    blocked = critic.get("blocked_claims") or []
    return [item for item in blocked if isinstance(item, dict)]


def _followup_agent_for_blocked_claims(blocked: list[dict[str, Any]]) -> str | None:
    rendered = " ".join(
        " ".join(str(item.get(key, "")) for key in ("claim", "reason", "action"))
        for item in blocked
    ).lower()
    if not rendered:
        return None
    if "microservice" in rendered or "boundary" in rendered or "refactoring" in rendered:
        return "modernization"
    if "security" in rendered or "secret" in rendered or "credential" in rendered:
        return "security"
    if "architecture" in rendered or "coupling" in rendered or "blast" in rendered:
        return "architecture"
    return None


def _decision(next_agent: str, rationale: str, graph_label: str, skipped_agents: list[str] | None = None) -> dict[str, Any]:
    return {
        "next_agent": next_agent,
        "rationale": rationale,
        "graph_label": graph_label,
        "evidence_gaps": [],
        "skipped_agents": skipped_agents or [],
    }


def _deterministic_supervisor_decision(state: dict[str, Any]) -> dict[str, Any]:
    metadata = _metadata(state)
    skipped = _skip_irrelevant_agents(state)
    iteration = int(state.get("iteration_count", 0))
    max_iterations = int(state.get("max_iterations", 10))

    if iteration >= max_iterations:
        return _decision(
            "report",
            "The bounded autonomy limit was reached, so the system is terminating safely with the evidence collected.",
            "max iterations reached",
            skipped,
        )

    blocked = _blocked_claims(state)
    if _has_run(state, "critic"):
        if not blocked:
            state["critic_approved"] = True
            return _decision(
                "report",
                "The Critic Agent found no unsupported claims, so the report can be generated.",
                "critic approved",
                skipped,
            )
        state["critic_approved"] = False
        state["critic_feedback"] = blocked
        followup = _followup_agent_for_blocked_claims(blocked)
        if followup and _run_count(state, followup) < 2:
            return _decision(
                followup,
                f"The Critic Agent blocked {len(blocked)} claim(s), so {ROUTE_LABELS[followup]} should revise the evidence-backed output once.",
                "critic requested follow-up",
                skipped,
            )
        return _decision(
            "report",
            "The Critic Agent blocked unsupported claims. They will be separated in the final report instead of rerunning indefinitely.",
            "blocked claims separated",
            skipped,
        )

    if _security_priority(metadata) and not _has_run(state, "security"):
        return _decision(
            "security",
            "Repository metadata shows configuration, external integration, cloud, or prompt-injection signals, so security analysis is prioritized.",
            "risk signals detected",
            skipped,
        )

    if _architecture_required(metadata) and not _has_run(state, "architecture"):
        return _decision(
            "architecture",
            "The scanner found source structure or indexed files, so architecture analysis should map the system before planning.",
            "structure evidence found",
            skipped,
        )

    if _dependency_required(metadata) and not _has_run(state, "dependency"):
        return _decision(
            "dependency",
            "Dependency files or build tools were detected, so dependency modernization risk should be reviewed.",
            "dependency evidence found",
            skipped,
        )

    if _security_required(metadata) and not _has_run(state, "security"):
        return _decision(
            "security",
            "A static security pass is required before modernization recommendations are trusted.",
            "safety pass required",
            skipped,
        )

    if _test_strategy_required(metadata) and not _has_run(state, "test_strategy"):
        return _decision(
            "test_strategy",
            "Controller, service, or test evidence exists, so the system should assess regression coverage before modernization.",
            "test surface found",
            skipped,
        )

    if not _has_run(state, "modernization"):
        return _decision(
            "modernization",
            "The specialist findings are ready, so modernization planning can synthesize roadmap and service-boundary recommendations.",
            "analysis synthesized",
            skipped,
        )

    return _decision(
        "critic",
        "Modernization recommendations exist, so the Critic Agent should verify claims before final reporting.",
        "claims need review",
        skipped,
    )


def _sanitize_decision(candidate: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    next_agent = str(candidate.get("next_agent", "")).strip()
    if next_agent not in VALID_NEXT_AGENTS:
        return fallback

    sanitized = dict(candidate)
    sanitized["next_agent"] = next_agent
    sanitized["rationale"] = str(candidate.get("rationale") or fallback["rationale"])[:500]
    sanitized["graph_label"] = str(candidate.get("graph_label") or fallback["graph_label"])[:120]
    if not isinstance(sanitized.get("evidence_gaps"), list):
        sanitized["evidence_gaps"] = fallback.get("evidence_gaps", [])
    if not isinstance(sanitized.get("skipped_agents"), list):
        sanitized["skipped_agents"] = fallback.get("skipped_agents", [])
    return sanitized


def _policy_decision(fallback: dict[str, Any], reason: str) -> dict[str, Any]:
    decision = dict(fallback)
    decision["llm_status"] = "policy_enforced"
    decision["llm_provider"] = "deterministic"
    decision["policy_reason"] = reason
    return decision


def _enforce_decision_policy(
    state: dict[str, Any],
    decision: dict[str, Any],
    fallback: dict[str, Any],
) -> dict[str, Any]:
    if fallback.get("next_agent") == "report":
        return _policy_decision(fallback, "The deterministic supervisor determined the analysis should terminate.")

    next_agent = str(decision.get("next_agent", "")).strip()
    if next_agent == "report":
        return _policy_decision(fallback, "Report generation is only allowed after critic review or the iteration cap.")

    if next_agent == "critic" and not _has_run(state, "modernization") and fallback.get("next_agent") != "critic":
        return _policy_decision(fallback, "Critic review is only allowed after modernization planning.")

    if next_agent in state.get("skipped_agents", []):
        return _policy_decision(fallback, f"{next_agent} was skipped for this repository.")

    if next_agent in RERUN_GATED_AGENTS and _has_run(state, next_agent) and fallback.get("next_agent") != next_agent:
        return _policy_decision(fallback, f"{next_agent} already returned results and no follow-up was requested.")

    return decision


def run_supervisor_agent(state: dict[str, Any]) -> dict[str, Any]:
    mark_step(state, "supervisor_agent", "running")
    state["iteration_count"] = int(state.get("iteration_count", 0)) + 1
    fallback = _deterministic_supervisor_decision(state)
    if fallback.get("next_agent") == "report":
        decision = _policy_decision(fallback, "The deterministic supervisor determined the analysis should terminate.")
    else:
        decision = optional_bedrock_json(
            SUPERVISOR_SYSTEM_PROMPT,
            {
                "repo_metadata": _metadata(state),
                "completed_agents": state.get("completed_agents", []),
                "agent_run_counts": state.get("agent_run_counts", {}),
                "critic_findings": state.get("critic_findings", {}),
                "current_reports": {
                    "architecture": bool(state.get("architecture_report")),
                    "dependency": bool(state.get("dependency_report")),
                    "security": bool(state.get("security_report")),
                    "test_strategy": bool(state.get("test_report")),
                    "modernization": bool(state.get("modernization_plan")),
                },
                "iteration_count": state["iteration_count"],
                "max_iterations": state.get("max_iterations", 10),
                "safe_default_decision": fallback,
            },
            fallback,
            max_tokens=1500,
        )
        decision = _sanitize_decision(decision, fallback)
        decision = _enforce_decision_policy(state, decision, fallback)

    next_agent = decision["next_agent"]
    state["next_agent"] = next_agent
    state["evidence_gaps"] = decision.get("evidence_gaps", [])

    decision_record = {
        "iteration": state["iteration_count"],
        "next_agent": next_agent,
        "agent_label": ROUTE_LABELS.get(next_agent, next_agent),
        "rationale": decision.get("rationale", ""),
        "graph_label": decision.get("graph_label", ""),
        "llm_status": decision.get("llm_status", "unknown"),
        "llm_provider": decision.get("llm_provider", "unknown"),
        "skipped_agents": decision.get("skipped_agents", []),
    }
    state.setdefault("agent_decisions", []).append(decision_record)
    state.setdefault("agent_messages", []).append(
        {
            "from": "supervisor",
            "to": next_agent,
            "message": decision_record["rationale"],
            "iteration": decision_record["iteration"],
        }
    )
    add_graph_edge(
        state,
        "supervisor",
        next_agent,
        decision_record["graph_label"] or decision_record["rationale"] or "selected by supervisor",
        state["iteration_count"],
    )
    mark_step(state, "supervisor_agent", "completed")
    return state
