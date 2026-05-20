from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class ModernizeState(TypedDict, total=False):
    analysis_id: str
    repo_path: str
    repo_metadata: Dict[str, Any]
    architecture_report: Optional[Dict[str, Any]]
    dependency_report: Optional[Dict[str, Any]]
    security_report: Optional[Dict[str, Any]]
    test_report: Optional[Dict[str, Any]]
    modernization_plan: Optional[Dict[str, Any]]
    critic_findings: Optional[Dict[str, Any]]
    final_report_markdown: Optional[str]
    rag_evidence: Dict[str, List[Dict[str, Any]]]
    progress: List[Dict[str, str]]
    errors: List[str]
    next_agent: str
    iteration_count: int
    max_iterations: int
    completed_agents: List[str]
    skipped_agents: List[str]
    agent_run_counts: Dict[str, int]
    agent_decisions: List[Dict[str, Any]]
    agent_messages: List[Dict[str, Any]]
    agent_graph: Dict[str, Any]
    critic_approved: bool
    critic_feedback: List[Dict[str, Any]]
    evidence_gaps: List[str]
    last_agent: str
