from __future__ import annotations

from pathlib import Path

from app.agents.modernization_agent import _fallback_modernization
from app.reports.markdown_report import generate_markdown_report
from app.reports.report_store import load_report_markdown, save_analysis_result
from app.scanner.repo_scanner import scan_repository


def test_report_contains_required_sections_and_redacted_evidence() -> None:
    state = {
        "repo_metadata": {
            "framework": "Spring Boot",
            "languages": ["Java"],
            "build_tools": ["Maven"],
            "file_counts": {"indexed_files": 3},
            "controllers": [{"file": "OrderController.java", "evidence": '@GetMapping("/{id}")'}],
            "services": [],
            "repositories": [],
            "test_files": [],
        },
        "architecture_report": {
            "architecture_summary": "Layered app",
            "layers": [],
            "api_inventory": [{"method": "GET", "path": "/orders", "file": "OrderController.java", "evidence": "@GetMapping"}],
            "llm_status": "bedrock",
            "llm_provider": "Amazon Bedrock",
            "llm_model_id": "us.anthropic.claude-sonnet-4-6",
        },
        "dependency_report": {"dependency_summary": "Dependency summary", "potential_risks": []},
        "security_report": {
            "risk_summary": "Security summary",
            "findings": [
                {
                    "severity": "High",
                    "title": "Potential hardcoded secret",
                    "file": "application.properties",
                    "evidence": "spring.datasource.password=<REDACTED>",
                    "recommendation": "Move to secrets manager.",
                }
            ],
        },
        "test_report": {"test_summary": "Test summary", "missing_test_areas": [], "recommended_tests": []},
        "modernization_plan": {
            "microservice_candidates": [
                {
                    "name": "Analytics microservice should be extracted",
                    "confidence": "Low",
                    "files": ["AnalyticsController.java"],
                    "reasoning": "No analytics evidence.",
                    "risks": ["Unsupported claim."],
                }
            ],
            "containerization_plan": [],
            "ci_cd_plan": [],
            "phased_roadmap": [],
            "risks": [],
            "assumptions": [],
        },
        "critic_findings": {
            "blocked_claims": [
                {
                    "claim": "Analytics microservice should be extracted",
                    "reason": "No analytics evidence.",
                    "action": "Remove.",
                }
            ],
            "warnings": [],
            "overall_confidence": "Medium",
        },
        "agent_graph": {
            "nodes": [
                {"id": "supervisor", "label": "Supervisor", "status": "completed", "run_count": 1},
                {"id": "security", "label": "Security", "status": "completed", "run_count": 1},
            ],
            "edges": [
                {"source": "supervisor", "target": "security", "label": "risk signals detected", "iteration": 1}
            ],
        },
        "agent_decisions": [
            {
                "iteration": 1,
                "agent_label": "Security",
                "graph_label": "risk signals detected",
                "rationale": "Repository metadata showed risky configuration.",
            }
        ],
    }

    report = generate_markdown_report(state)

    assert "## 1. Executive Summary" in report
    assert "## Analysis Snapshot" in report
    assert "## Demo Readout" not in report
    assert "## 9. 30/60/90-Day Cloud Modernization Roadmap" in report
    assert "AWS Migration Roadmap" not in report
    assert "| Runtime |" not in report
    assert "Agent runtime" not in report
    assert "Fallback Reason" not in report
    assert "us.anthropic.claude-sonnet-4-6" in report
    assert "0 evidence-backed candidates" in report
    assert "## 12. Agent Collaboration Trace" in report
    assert "## 13. Critic Review" in report
    assert "Repository metadata showed risky configuration." in report
    assert "Confidence context:" in report
    assert "spring.datasource.password=<REDACTED>" in report
    assert "demo-password" not in report
    boundaries_section = report.split("## 8. Candidate Service Boundaries", 1)[1].split(
        "## 9. 30/60/90-Day Cloud Modernization Roadmap", 1
    )[0]
    assert "Analytics microservice should be extracted" not in boundaries_section


def test_report_hides_runtime_fallback_and_formats_dict_bullets() -> None:
    state = {
        "repo_metadata": {
            "framework": "Spring Boot",
            "languages": ["Java"],
            "build_tools": ["Maven"],
            "file_counts": {"indexed_files": 4},
            "controllers": [],
            "services": [],
            "repositories": [],
            "test_files": [],
        },
        "architecture_report": {
            "architecture_summary": "Layered app",
            "layers": [],
            "api_inventory": [],
            "llm_status": "fallback",
            "llm_provider": "deterministic",
            "llm_model_id": "us.anthropic.claude-sonnet-4-6",
        },
        "dependency_report": {
            "dependency_summary": "Dependency summary",
            "potential_risks": [],
            "llm_status": "bedrock",
            "llm_provider": "Amazon Bedrock",
            "llm_model_id": "us.anthropic.claude-sonnet-4-6",
        },
        "security_report": {
            "risk_summary": "Security summary",
            "findings": [
                {
                    "severity": "High",
                    "title": "Potential hardcoded secret",
                    "file": "application.properties",
                    "evidence": "jwt.secret=<REDACTED>",
                    "recommendation": "Move to secrets manager.",
                }
            ],
            "recommended_mitigations": [
                {
                    "files": ["AccountController.java", "CustomerController.java", "PaymentBatchController.java"],
                    "action": "Enable method-level authorization on sensitive endpoints.",
                }
            ],
            "llm_status": "bedrock",
            "llm_provider": "Amazon Bedrock",
            "llm_model_id": "us.anthropic.claude-sonnet-4-6",
        },
        "test_report": {"test_summary": "Test summary", "missing_test_areas": [], "recommended_tests": []},
        "modernization_plan": {
            "microservice_candidates": [],
            "phased_roadmap": [],
            "risks": [],
            "assumptions": [],
            "llm_status": "fallback",
            "llm_provider": "deterministic",
            "llm_model_id": "us.anthropic.claude-sonnet-4-6",
        },
        "critic_findings": {
            "blocked_claims": [],
            "warnings": [],
            "overall_confidence": "High",
            "llm_status": "bedrock",
            "llm_provider": "Amazon Bedrock",
            "llm_model_id": "us.anthropic.claude-sonnet-4-6",
        },
    }

    report = generate_markdown_report(state)

    assert "mixed Bedrock + deterministic fallback" not in report
    assert "deterministic fallback" not in report
    assert "Agent runtime" not in report
    assert "Fallback Reason" not in report
    assert "LLM Status" not in report
    assert "us.anthropic.claude-sonnet-4-6" in report
    assert "{'files'" not in report
    assert "Enable method-level authorization on sensitive endpoints." in report
    assert "Files: AccountController.java; CustomerController.java; PaymentBatchController.java" in report


def test_report_prefers_scanner_test_summary_when_model_contradicts_metadata() -> None:
    state = {
        "repo_metadata": {
            "framework": "Spring Boot",
            "languages": ["Java"],
            "build_tools": ["Maven"],
            "file_counts": {"indexed_files": 3},
            "controllers": [
                {
                    "name": "AccountController",
                    "file": "src/main/java/com/example/AccountController.java",
                    "endpoints": [{"method": "GET", "path": "/accounts/{id}"}],
                }
            ],
            "services": [
                {"name": "PaymentBatchService", "file": "src/main/java/com/example/PaymentBatchService.java"}
            ],
            "repositories": [],
            "test_files": [{"file": "src/test/java/com/example/AccountControllerTest.java", "evidence": "@Test"}],
        },
        "architecture_report": {},
        "dependency_report": {},
        "security_report": {"findings": []},
        "test_report": {
            "test_summary": "No tests exist in this Spring Boot banking platform.",
            "missing_test_areas": [],
            "recommended_tests": [],
        },
        "modernization_plan": {"microservice_candidates": [], "phased_roadmap": [], "risks": [], "assumptions": []},
        "critic_findings": {"blocked_claims": [], "warnings": [], "overall_confidence": "Medium"},
    }

    report = generate_markdown_report(state)

    assert "No tests exist" not in report
    assert "Found 1 existing test files and 1 likely missing test areas" in report
    assert "PaymentBatchServiceTest was found" in report


def test_report_filters_dependency_claims_contradicted_by_scanner_metadata() -> None:
    state = {
        "repo_metadata": {
            "framework": "Spring Boot",
            "languages": ["Java"],
            "build_tools": ["Maven"],
            "file_counts": {"indexed_files": 2},
            "controllers": [],
            "services": [],
            "repositories": [],
            "test_files": [],
            "dependency_files": [{"file": "pom.xml", "evidence": "<artifactId>spring-boot-starter-parent</artifactId>"}],
            "dependency_details": [
                {
                    "file": "pom.xml",
                    "spring_boot_version": "1.5.22.RELEASE",
                    "dependencies": [{"groupId": "mysql", "artifactId": "mysql-connector-java", "version": "5.1.47"}],
                }
            ],
        },
        "architecture_report": {},
        "dependency_report": {
            "dependency_summary": "Dependency summary",
            "potential_risks": [
                {
                    "severity": "Low",
                    "title": "Spring Boot version not pinned in evidence",
                    "file": "pom.xml",
                    "evidence": "No explicit Spring Boot version visible in provided evidence.",
                    "recommendation": "Confirm Spring Boot version.",
                },
                {
                    "severity": "high",
                    "title": "Unknown Spring Boot version may contain known CVEs",
                    "file": "pom.xml",
                    "evidence": "No pom.xml content available to verify Spring Boot parent version.",
                    "recommendation": "Extract and verify Spring Boot parent version.",
                },
                {
                    "severity": "medium",
                    "title": "No dependency version pinning visibility",
                    "file": "pom.xml",
                    "evidence": "pom.xml was not indexed or provided.",
                    "recommendation": "Run mvn dependency:tree.",
                },
            ],
        },
        "security_report": {"findings": []},
        "test_report": {},
        "modernization_plan": {"microservice_candidates": [], "phased_roadmap": [], "risks": [], "assumptions": []},
        "critic_findings": {"blocked_claims": [], "warnings": [], "overall_confidence": "Medium"},
    }

    report = generate_markdown_report(state)

    assert "Spring Boot version not pinned in evidence" not in report
    assert "Unknown Spring Boot version" not in report
    assert "No dependency version pinning visibility" not in report
    assert "No pom.xml content available" not in report
    assert "pom.xml was not indexed or provided" not in report
    assert "Potential legacy Spring Boot baseline" in report
    assert "Spring Boot version 1.5.22.RELEASE" in report
    assert "### Medium - Potential legacy Spring Boot baseline" in report
    assert "### high" not in report
    assert "### medium" not in report


def test_report_rewrites_vague_security_config_absence_when_security_config_exists() -> None:
    metadata = scan_repository(Path("sample_repos/legacy-retail-banking-platform"), "security-config")
    state = {
        "repo_metadata": metadata,
        "architecture_report": {
            "architecture_summary": "Layered app",
            "layers": [],
            "api_inventory": [],
            "architecture_concerns": ["No Visible Security Configuration Files: AccountController.java"],
        },
        "dependency_report": {},
        "security_report": {"findings": []},
        "test_report": {},
        "modernization_plan": {"microservice_candidates": [], "phased_roadmap": [], "risks": [], "assumptions": []},
        "critic_findings": {"blocked_claims": [], "warnings": [], "overall_confidence": "Medium"},
    }

    report = generate_markdown_report(state)

    assert "No Visible Security Configuration" not in report
    assert "SecurityConfig disables CSRF and permits all requests" in report


def test_report_security_summary_count_matches_visible_findings() -> None:
    findings = [
        {
            "severity": "low",
            "title": f"Finding {index}",
            "file": f"file-{index}.properties",
            "evidence": f"setting-{index}=true",
            "recommendation": "Review before migration.",
        }
        for index in range(1, 12)
    ]
    state = {
        "repo_metadata": {
            "framework": "Spring Boot",
            "languages": ["Java"],
            "build_tools": ["Maven"],
            "file_counts": {"indexed_files": 11},
            "controllers": [],
            "services": [],
            "repositories": [],
            "test_files": [],
        },
        "architecture_report": {},
        "dependency_report": {},
        "security_report": {"findings": findings},
        "test_report": {},
        "modernization_plan": {"microservice_candidates": [], "phased_roadmap": [], "risks": [], "assumptions": []},
        "critic_findings": {"blocked_claims": [], "warnings": [], "overall_confidence": "Medium"},
    }

    report = generate_markdown_report(state)

    assert "11 supported security/configuration findings" in report
    assert "### Low - Finding 11" in report
    assert "### low" not in report


def test_report_cloud_roadmap_does_not_assume_aws_without_repo_evidence() -> None:
    state = {
        "repo_metadata": {
            "framework": "Spring Boot",
            "languages": ["Java"],
            "build_tools": ["Maven"],
            "file_counts": {"indexed_files": 1},
            "controllers": [],
            "services": [],
            "repositories": [],
            "test_files": [],
            "detected_cloud_providers": [],
            "detected_cloud_services": [],
        },
        "architecture_report": {
            "architecture_summary": "Layered app",
            "layers": [],
            "api_inventory": [],
            "llm_status": "disabled",
            "llm_provider": "deterministic",
            "llm_model_id": "",
        },
        "dependency_report": {"dependency_summary": "Dependency summary", "potential_risks": []},
        "security_report": {"risk_summary": "Security summary", "findings": []},
        "test_report": {"test_summary": "Test summary", "missing_test_areas": [], "recommended_tests": []},
        "modernization_plan": {
            "microservice_candidates": [],
            "containerization_plan": [],
            "ci_cd_plan": [],
            "phased_roadmap": [
                {
                    "phase": "Phase 1",
                    "title": "Neutral phase",
                    "tasks": ["Move secrets to a managed secrets/configuration service selected by the client."],
                }
            ],
            "risks": [],
            "assumptions": [
                "Static analysis does not assume a cloud provider; choose the target platform from client standards."
            ],
        },
        "critic_findings": {"blocked_claims": [], "warnings": [], "overall_confidence": "Medium"},
    }

    report = generate_markdown_report(state)
    roadmap_section = report.split("## 9. 30/60/90-Day Cloud Modernization Roadmap", 1)[1].split(
        "## 10. Risks and Assumptions", 1
    )[0]

    assert "AWS" not in roadmap_section
    assert "EC2" not in roadmap_section
    assert "30/60/90-Day Cloud Modernization Roadmap" in report


def test_sample_aws_s3_evidence_is_context_not_migration_target() -> None:
    repo_root = Path("sample_repos/legacy-claims-processing-platform")
    metadata = scan_repository(repo_root, "analysis-claims")
    plan = _fallback_modernization(
        {
            "repo_metadata": metadata,
            "architecture_report": {},
            "dependency_report": {},
            "security_report": {},
            "test_report": {},
        }
    )

    rendered_plan = "\n".join(
        str(value)
        for section in (
            plan["cloud_migration_plan"],
            plan["refactoring_opportunities"],
            plan["phased_roadmap"],
            plan["assumptions"],
        )
        for item in section
        for value in (item.values() if isinstance(item, dict) else [item])
    )

    assert "AWS S3 integration was detected and should be reviewed" in rendered_plan
    assert "migrate to aws" not in rendered_plan.lower()
    assert "EC2" not in rendered_plan


def test_load_report_markdown_regenerates_full_analysis_reports(tmp_path, monkeypatch) -> None:
    from app.config import settings

    original_report_dir = settings.report_dir
    object.__setattr__(settings, "report_dir", tmp_path)
    try:
        analysis_id = "regenerate-report"
        save_analysis_result(
            analysis_id,
            {
                "repo_metadata": {
                    "framework": "Spring Boot",
                    "languages": ["Java"],
                    "build_tools": ["Maven"],
                    "file_counts": {"indexed_files": 1},
                    "controllers": [],
                    "services": [],
                    "repositories": [],
                    "test_files": [],
                },
                "architecture_report": {},
                "dependency_report": {},
                "security_report": {},
                "test_report": {},
                "modernization_plan": {},
                "critic_findings": {},
                "final_report_markdown": "# Old Stored Report\n",
            },
        )

        report = load_report_markdown(analysis_id)

        assert "# Old Stored Report" not in report
        assert "## 2. Top Modernization Priorities" in report
    finally:
        object.__setattr__(settings, "report_dir", original_report_dir)
