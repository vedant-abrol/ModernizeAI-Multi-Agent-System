from __future__ import annotations

from app.agents.critic_agent import _fallback_critic


def test_critic_blocks_microservice_candidate_without_data_ownership() -> None:
    state = {
        "security_report": {"findings": []},
        "architecture_report": {},
        "modernization_plan": {
            "refactoring_opportunities": [],
            "microservice_candidates": [
                {
                    "name": "Payment Service Candidate",
                    "files": [
                        "src/main/java/com/example/controller/PaymentController.java",
                        "src/main/java/com/example/service/PaymentService.java",
                    ],
                }
            ],
        },
        "repo_metadata": {"warnings": []},
    }

    result = _fallback_critic(state)

    assert result["overall_confidence"] == "Low"
    assert result["blocked_claims"][0]["claim"] == "Payment Service Candidate"
    assert "data ownership" in result["blocked_claims"][0]["reason"]


def test_critic_blocks_prompt_injection_repository_text() -> None:
    state = {
        "security_report": {"findings": []},
        "architecture_report": {},
        "modernization_plan": {"refactoring_opportunities": [], "microservice_candidates": []},
        "repo_metadata": {
            "warnings": [
                {
                    "file": "README.md",
                    "pattern": "ignore previous instructions",
                }
            ]
        },
    }

    result = _fallback_critic(state)

    assert result["blocked_claims"] == []
    assert "README.md" in result["warnings"][0]["message"]
    assert result["overall_confidence"] == "Medium"
