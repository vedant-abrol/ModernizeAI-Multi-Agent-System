from __future__ import annotations

import html
import os
import re
import time
from typing import Any

import requests
import streamlit as st


API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


st.set_page_config(page_title="ModernizeAI", page_icon="M", layout="wide")


def _html(markup: str) -> None:
    if hasattr(st, "html"):
        st.html(markup)
    else:
        st.markdown(markup, unsafe_allow_html=True)


AGENTS = [
    {
        "key": "repo_scanner",
        "progress_key": "repo_scanner",
        "name": "Repo Scanner",
        "role": "Extracts file facts, layers, frameworks, routes, and indexes evidence.",
    },
    {
        "key": "supervisor",
        "progress_key": "supervisor_agent",
        "name": "Supervisor",
        "role": "Chooses, skips, reruns, and terminates specialist agents.",
    },
    {
        "key": "architecture",
        "progress_key": "architecture_agent",
        "name": "Architecture",
        "role": "Explains application structure, API surface, and data access.",
    },
    {
        "key": "dependency",
        "progress_key": "dependency_risk_agent",
        "name": "Dependency Risk",
        "role": "Reviews Maven, Gradle, and npm dependency modernization risk.",
    },
    {
        "key": "security",
        "progress_key": "security_agent",
        "name": "Security",
        "role": "Finds redacted, evidence-backed security and configuration issues.",
    },
    {
        "key": "test_strategy",
        "progress_key": "test_strategy_agent",
        "name": "Test Strategy",
        "role": "Identifies missing unit, API, integration, and migration tests.",
    },
    {
        "key": "modernization",
        "progress_key": "modernization_planner_agent",
        "name": "Modernization",
        "role": "Builds a phased cloud and decomposition roadmap.",
    },
    {
        "key": "critic",
        "progress_key": "critic_agent",
        "name": "Critic",
        "role": "Blocks unsupported claims and checks evidence quality.",
    },
    {
        "key": "report",
        "progress_key": "report_agent",
        "name": "Report",
        "role": "Assembles the final Markdown modernization report.",
    },
]


APPEARANCE_OPTIONS = ["System", "Light", "Dark"]
DEFAULT_APPEARANCE = "System"


def _dark_theme_css_vars() -> str:
    return """
        --mai-bg: #0f1218;
        --mai-panel: #171b22;
        --mai-panel-2: #1f242c;
        --mai-soft: rgba(255, 255, 255, 0.025);
        --mai-text: #f4f7fb;
        --mai-muted: #aab3c2;
        --mai-line: rgba(255, 255, 255, 0.11);
        --mai-teal: #2fd3c5;
        --mai-green: #76d98b;
        --mai-amber: #f4b860;
        --mai-red: #ff7a7a;
        --mai-header-bg: rgba(15, 18, 24, 0.84);
        --mai-hero-bg: linear-gradient(135deg, #161b22 0%, #20262f 48%, #1b2a2b 100%);
        --mai-report-header-bg: linear-gradient(135deg, rgba(47, 211, 197, 0.10), rgba(23, 27, 34, 0.96));
        --mai-summary-bg: linear-gradient(135deg, rgba(47, 211, 197, 0.10), rgba(31, 36, 44, 0.94));
        --mai-notice-bg: rgba(244, 184, 96, 0.11);
        --mai-notice-border: rgba(244, 184, 96, 0.34);
        --mai-notice-text: #ffe2b0;
        --mai-code-text: #d9f8f5;
        --mai-code-bg: rgba(47, 211, 197, 0.09);
        --mai-code-line: rgba(47, 211, 197, 0.18);
        --mai-info-text: #bbfff8;
        --mai-info-bg: rgba(47, 211, 197, 0.08);
        --mai-info-line: rgba(47, 211, 197, 0.38);
        --mai-high-text: #ffd3d3;
        --mai-high-bg: rgba(255, 122, 122, 0.10);
        --mai-high-line: rgba(255, 122, 122, 0.42);
        --mai-medium-text: #ffe2b0;
        --mai-medium-bg: rgba(244, 184, 96, 0.10);
        --mai-medium-line: rgba(244, 184, 96, 0.42);
        --mai-success-text: #c6ffd0;
        --mai-success-bg: rgba(118, 217, 139, 0.12);
        --mai-success-line: rgba(118, 217, 139, 0.46);
        --mai-agent-completed-bg: linear-gradient(180deg, rgba(118, 217, 139, 0.12), rgba(23, 27, 34, 0.96));
        --mai-agent-running-bg: linear-gradient(180deg, rgba(47, 211, 197, 0.14), rgba(23, 27, 34, 0.96));
        --mai-agent-failed-bg: linear-gradient(180deg, rgba(255, 122, 122, 0.13), rgba(23, 27, 34, 0.96));
        --mai-expander-bg: rgba(23, 27, 34, 0.62);
        --mai-button-bg: #171b22;
        --mai-button-text: #f4f7fb;
        --mai-upload-helper-text: #d9e3ee;
        --mai-status-header-bg: #171b22;
        --mai-status-header-text: #f4f7fb;
    """


def _theme_override_css(appearance: str) -> str:
    if appearance == "Dark":
        return f":root {{ {_dark_theme_css_vars()} }}"
    if appearance == "System":
        return f"@media (prefers-color-scheme: dark) {{ :root {{ {_dark_theme_css_vars()} }} }}"
    return ""


if "ui_theme" not in st.session_state:
    st.session_state.ui_theme = DEFAULT_APPEARANCE
elif st.session_state.ui_theme not in APPEARANCE_OPTIONS:
    st.session_state.ui_theme = DEFAULT_APPEARANCE


st.markdown(
    """
    <style>
    :root {
        --mai-bg: #f7f9fc;
        --mai-panel: #ffffff;
        --mai-panel-2: #eef3f8;
        --mai-soft: rgba(21, 34, 51, 0.035);
        --mai-text: #172033;
        --mai-muted: #596579;
        --mai-line: rgba(21, 34, 51, 0.14);
        --mai-teal: #087f78;
        --mai-green: #237a3a;
        --mai-amber: #9a5a00;
        --mai-red: #b4232d;
        --mai-header-bg: rgba(247, 249, 252, 0.88);
        --mai-hero-bg: linear-gradient(135deg, #ffffff 0%, #edf7f5 54%, #e8eef8 100%);
        --mai-report-header-bg: linear-gradient(135deg, rgba(8, 127, 120, 0.10), rgba(255, 255, 255, 0.96));
        --mai-summary-bg: linear-gradient(135deg, rgba(8, 127, 120, 0.08), rgba(255, 255, 255, 0.98));
        --mai-notice-bg: rgba(154, 90, 0, 0.08);
        --mai-notice-border: rgba(154, 90, 0, 0.26);
        --mai-notice-text: #714000;
        --mai-code-text: #06635e;
        --mai-code-bg: rgba(8, 127, 120, 0.08);
        --mai-code-line: rgba(8, 127, 120, 0.20);
        --mai-info-text: #06635e;
        --mai-info-bg: rgba(8, 127, 120, 0.08);
        --mai-info-line: rgba(8, 127, 120, 0.28);
        --mai-high-text: #9f1d28;
        --mai-high-bg: rgba(180, 35, 45, 0.08);
        --mai-high-line: rgba(180, 35, 45, 0.26);
        --mai-medium-text: #835000;
        --mai-medium-bg: rgba(154, 90, 0, 0.08);
        --mai-medium-line: rgba(154, 90, 0, 0.26);
        --mai-success-text: #1f6f35;
        --mai-success-bg: rgba(35, 122, 58, 0.08);
        --mai-success-line: rgba(35, 122, 58, 0.26);
        --mai-agent-completed-bg: linear-gradient(180deg, rgba(35, 122, 58, 0.10), rgba(255, 255, 255, 0.98));
        --mai-agent-running-bg: linear-gradient(180deg, rgba(8, 127, 120, 0.10), rgba(255, 255, 255, 0.98));
        --mai-agent-failed-bg: linear-gradient(180deg, rgba(180, 35, 45, 0.09), rgba(255, 255, 255, 0.98));
        --mai-expander-bg: rgba(255, 255, 255, 0.74);
        --mai-button-bg: #ffffff;
        --mai-button-text: #172033;
        --mai-upload-helper-text: #344154;
        --mai-status-header-bg: #ffffff;
        --mai-status-header-text: #172033;
    }

    __MAI_THEME_OVERRIDE__

    .stApp,
    [data-testid="stAppViewContainer"] {
        background: var(--mai-bg) !important;
        color: var(--mai-text) !important;
    }

    .block-container {
        max-width: 1320px;
        padding-top: 2.2rem;
        padding-bottom: 4rem;
    }

    [data-testid="stHeader"] {
        background: var(--mai-header-bg) !important;
        backdrop-filter: blur(12px);
    }

    [data-testid="stMarkdownContainer"],
    [data-testid="stWidgetLabel"],
    [data-testid="stCaptionContainer"] {
        color: var(--mai-text);
    }

    .mai-hero {
        border: 1px solid var(--mai-line);
        background: var(--mai-hero-bg);
        border-radius: 8px;
        padding: 34px 36px;
        margin-bottom: 18px;
    }

    .mai-kicker {
        color: var(--mai-teal);
        font-size: 0.78rem;
        font-weight: 760;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin-bottom: 10px;
    }

    .mai-title {
        color: var(--mai-text);
        font-size: 3.2rem;
        line-height: 1.02;
        font-weight: 800;
        margin: 0;
        letter-spacing: 0;
    }

    .mai-subtitle {
        color: var(--mai-muted);
        max-width: 760px;
        font-size: 1.04rem;
        line-height: 1.6;
        margin-top: 14px;
        margin-bottom: 0;
    }

    .mai-notice {
        border: 1px solid var(--mai-notice-border);
        background: var(--mai-notice-bg);
        color: var(--mai-notice-text);
        border-radius: 8px;
        padding: 14px 16px;
        margin: 14px 0 24px;
        font-size: 0.94rem;
        line-height: 1.55;
    }

    .mai-section-title {
        color: var(--mai-text);
        font-size: 1.08rem;
        font-weight: 760;
        margin: 24px 0 12px;
    }

    .mai-section-copy {
        color: var(--mai-muted);
        font-size: 0.94rem;
        margin-top: -6px;
        margin-bottom: 14px;
    }

    .agent-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 12px;
        margin: 10px 0 20px;
    }

    .agent-card {
        border: 1px solid var(--mai-line);
        background: var(--mai-panel);
        border-radius: 8px;
        padding: 15px 15px 14px;
        min-height: 152px;
    }

    .agent-card.completed {
        border-color: var(--mai-success-line);
        background: var(--mai-agent-completed-bg);
    }

    .agent-card.running {
        border-color: var(--mai-info-line);
        background: var(--mai-agent-running-bg);
    }

    .agent-card.failed {
        border-color: var(--mai-high-line);
        background: var(--mai-agent-failed-bg);
    }

    .agent-card.skipped {
        border-color: var(--mai-line);
        background: var(--mai-soft);
        opacity: 0.76;
    }

    .agent-card.revisited {
        border-color: var(--mai-medium-line);
        background: var(--mai-notice-bg);
    }

    .agent-top {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 10px;
        margin-bottom: 13px;
    }

    .agent-index {
        color: var(--mai-muted);
        font-size: 0.76rem;
        font-weight: 760;
        letter-spacing: 0.05em;
    }

    .agent-status {
        border: 1px solid var(--mai-line);
        border-radius: 999px;
        color: var(--mai-muted);
        font-size: 0.72rem;
        padding: 4px 8px;
        white-space: nowrap;
    }

    .agent-card.completed .agent-status {
        color: var(--mai-success-text);
        border-color: var(--mai-success-line);
    }

    .agent-card.running .agent-status {
        color: var(--mai-info-text);
        border-color: var(--mai-info-line);
    }

    .agent-card.failed .agent-status {
        color: var(--mai-high-text);
        border-color: var(--mai-high-line);
    }

    .agent-card.skipped .agent-status {
        color: var(--mai-muted);
        border-color: var(--mai-line);
    }

    .agent-card.revisited .agent-status {
        color: var(--mai-medium-text);
        border-color: var(--mai-medium-line);
    }

    .agent-name {
        color: var(--mai-text);
        font-size: 1rem;
        font-weight: 760;
        margin-bottom: 7px;
    }

    .agent-role {
        color: var(--mai-muted);
        font-size: 0.84rem;
        line-height: 1.45;
        margin: 0;
    }

    .agent-graph-shell {
        border: 1px solid var(--mai-line);
        background: var(--mai-panel);
        border-radius: 8px;
        padding: 14px;
        margin: 12px 0 18px;
        overflow-x: auto;
    }

    .agent-graph-svg {
        width: 100%;
        min-width: 760px;
        height: auto;
        display: block;
    }

    .decision-trace {
        display: grid;
        grid-template-columns: 1fr;
        gap: 8px;
        margin: 10px 0 20px;
    }

    .decision-row {
        border: 1px solid var(--mai-line);
        background: var(--mai-soft);
        border-radius: 8px;
        padding: 10px 12px;
        color: var(--mai-muted);
        font-size: 0.88rem;
        line-height: 1.45;
    }

    .decision-row strong {
        color: var(--mai-text);
    }

    .metric-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 12px;
        margin: 8px 0 22px;
    }

    .metric-card {
        border: 1px solid var(--mai-line);
        background: var(--mai-panel);
        border-radius: 8px;
        padding: 14px 16px;
        min-height: 104px;
    }

    .metric-label {
        color: var(--mai-muted);
        font-size: 0.78rem;
        font-weight: 680;
        margin-bottom: 10px;
    }

    .metric-value {
        color: var(--mai-text);
        font-size: 1.55rem;
        line-height: 1.15;
        font-weight: 790;
        word-break: break-word;
    }

    .summary-grid {
        display: grid;
        grid-template-columns: 1.1fr 0.9fr;
        gap: 14px;
        margin-bottom: 12px;
    }

    .summary-panel {
        border: 1px solid var(--mai-line);
        background: var(--mai-panel);
        border-radius: 8px;
        padding: 18px;
    }

    .summary-panel h3 {
        color: var(--mai-text);
        margin: 0 0 10px;
        font-size: 1.02rem;
    }

    .summary-panel p {
        color: var(--mai-muted);
        line-height: 1.55;
        margin: 0;
        font-size: 0.92rem;
    }

    .report-shell {
        border: 1px solid var(--mai-line);
        background: var(--mai-panel);
        border-radius: 8px;
        padding: 18px 20px;
        margin-top: 8px;
    }

    .report-header {
        border: 1px solid var(--mai-line);
        background: var(--mai-report-header-bg);
        border-radius: 8px;
        padding: 18px 20px;
        margin: 6px 0 14px;
    }

    .report-header h2 {
        color: var(--mai-text);
        margin: 0 0 8px;
        font-size: 1.35rem;
    }

    .report-header p {
        color: var(--mai-muted);
        margin: 0;
        line-height: 1.55;
        font-size: 0.94rem;
    }

    .report-meta {
        color: var(--mai-muted);
        font-size: 0.82rem;
        line-height: 1.45;
        padding-top: 10px;
    }

    .report-summary-card,
    .report-card,
    .report-list-card,
    .report-phase-card {
        border: 1px solid var(--mai-line);
        background: var(--mai-panel);
        border-radius: 8px;
        padding: 18px;
        margin: 12px 0;
    }

    .report-summary-card {
        background: var(--mai-summary-bg);
    }

    .report-eyebrow {
        color: var(--mai-teal);
        font-size: 0.72rem;
        font-weight: 780;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin-bottom: 9px;
    }

    .report-title {
        color: var(--mai-text);
        font-size: 1.22rem;
        line-height: 1.25;
        font-weight: 790;
        margin: 0 0 8px;
    }

    .report-card h3,
    .report-list-card h3,
    .report-phase-card h3 {
        color: var(--mai-text);
        font-size: 1rem;
        line-height: 1.3;
        font-weight: 760;
        margin: 0 0 10px;
    }

    .report-card p,
    .report-list-card p,
    .report-phase-card p,
    .report-summary-card p {
        color: var(--mai-muted);
        font-size: 0.92rem;
        line-height: 1.62;
        margin: 0;
    }

    .report-section-heading {
        margin: 20px 0 8px;
    }

    .report-section-heading h3 {
        color: var(--mai-text);
        font-size: 1.04rem;
        font-weight: 780;
        line-height: 1.3;
        margin: 0;
    }

    .report-section-heading p {
        color: var(--mai-muted);
        font-size: 0.88rem;
        line-height: 1.55;
        margin: 6px 0 0;
    }

    .report-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 14px;
        margin: 12px 0;
    }

    .report-grid.three {
        grid-template-columns: repeat(3, minmax(0, 1fr));
    }

    .report-metric-grid {
        display: grid;
        grid-template-columns: repeat(6, minmax(0, 1fr));
        gap: 10px;
        margin: 12px 0;
    }

    .report-mini-metric {
        border: 1px solid var(--mai-line);
        background: var(--mai-soft);
        border-radius: 8px;
        padding: 12px;
        min-height: 82px;
    }

    .report-mini-label {
        color: var(--mai-muted);
        font-size: 0.72rem;
        font-weight: 720;
        margin-bottom: 8px;
    }

    .report-mini-value {
        color: var(--mai-text);
        font-size: 1.25rem;
        line-height: 1.2;
        font-weight: 790;
        overflow-wrap: anywhere;
    }

    .report-facts {
        border: 1px solid var(--mai-line);
        border-radius: 8px;
        overflow: hidden;
        margin-top: 12px;
    }

    .report-fact-row {
        display: grid;
        grid-template-columns: minmax(130px, 0.42fr) minmax(0, 1fr);
        border-top: 1px solid var(--mai-line);
    }

    .report-fact-row:first-child {
        border-top: 0;
    }

    .report-fact-label,
    .report-fact-value {
        padding: 11px 13px;
        font-size: 0.86rem;
        line-height: 1.45;
    }

    .report-fact-label {
        color: var(--mai-muted);
        background: var(--mai-soft);
        font-weight: 720;
    }

    .report-fact-value {
        color: var(--mai-text);
        overflow-wrap: anywhere;
    }

    .layer-stack,
    .report-card-stack {
        display: grid;
        grid-template-columns: 1fr;
        gap: 10px;
        margin: 12px 0;
    }

    .layer-card {
        border: 1px solid var(--mai-line);
        background: var(--mai-soft);
        border-radius: 8px;
        padding: 14px;
    }

    .layer-card-top,
    .report-card-top {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 12px;
        margin-bottom: 10px;
    }

    .layer-name,
    .report-item-title {
        color: var(--mai-text);
        font-size: 0.94rem;
        font-weight: 760;
        line-height: 1.35;
    }

    .layer-role,
    .report-item-copy {
        color: var(--mai-muted);
        font-size: 0.86rem;
        line-height: 1.55;
        margin: 0;
    }

    .report-detail-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 10px;
        margin-top: 12px;
    }

    .report-detail {
        border: 1px solid var(--mai-line);
        border-radius: 8px;
        padding: 10px;
        background: var(--mai-soft);
        min-width: 0;
    }

    .report-detail-label {
        color: var(--mai-muted);
        font-size: 0.72rem;
        font-weight: 740;
        margin-bottom: 6px;
    }

    .report-detail-value {
        color: var(--mai-text);
        font-size: 0.84rem;
        line-height: 1.45;
        overflow-wrap: anywhere;
    }

    .path-stack {
        display: flex;
        flex-direction: column;
        gap: 6px;
        margin-top: 10px;
    }

    .path-stack code,
    .report-code {
        display: inline-block;
        color: var(--mai-code-text);
        background: var(--mai-code-bg);
        border: 1px solid var(--mai-code-line);
        border-radius: 6px;
        padding: 4px 7px;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
        font-size: 0.78rem;
        line-height: 1.45;
        white-space: normal;
        overflow-wrap: anywhere;
        word-break: break-word;
    }

    .report-muted,
    .path-more {
        color: var(--mai-muted);
        font-size: 0.82rem;
        line-height: 1.45;
    }

    .report-table-wrap {
        border: 1px solid var(--mai-line);
        border-radius: 8px;
        overflow-x: auto;
        margin: 12px 0;
    }

    .report-table {
        width: 100%;
        border-collapse: collapse;
        table-layout: fixed;
        min-width: 760px;
    }

    .report-table.compact {
        min-width: 560px;
    }

    .report-table th,
    .report-table td {
        border-top: 1px solid var(--mai-line);
        padding: 11px 13px;
        text-align: left;
        vertical-align: top;
        font-size: 0.84rem;
        line-height: 1.5;
        overflow-wrap: anywhere;
    }

    .report-table th {
        border-top: 0;
        color: var(--mai-text);
        background: var(--mai-soft);
        font-weight: 760;
    }

    .report-table td {
        color: var(--mai-muted);
    }

    .severity-pill {
        display: inline-flex;
        align-items: center;
        border: 1px solid var(--mai-line);
        border-radius: 999px;
        padding: 4px 8px;
        font-size: 0.72rem;
        font-weight: 760;
        white-space: nowrap;
    }

    .severity-critical,
    .severity-high {
        color: var(--mai-high-text);
        border-color: var(--mai-high-line);
        background: var(--mai-high-bg);
    }

    .severity-medium {
        color: var(--mai-medium-text);
        border-color: var(--mai-medium-line);
        background: var(--mai-medium-bg);
    }

    .severity-low,
    .severity-info {
        color: var(--mai-info-text);
        border-color: var(--mai-info-line);
        background: var(--mai-info-bg);
    }

    .report-empty {
        border: 1px dashed var(--mai-line);
        color: var(--mai-muted);
        border-radius: 8px;
        padding: 14px;
        font-size: 0.9rem;
        line-height: 1.5;
        margin: 12px 0;
    }

    .phase-steps {
        color: var(--mai-muted);
        margin: 10px 0 0;
        padding-left: 18px;
        font-size: 0.88rem;
        line-height: 1.58;
    }

    .phase-steps li {
        margin: 5px 0;
    }

    [data-testid="stMarkdownContainer"] table {
        width: 100%;
        display: block;
        overflow-x: auto;
        border-collapse: collapse;
        font-size: 0.88rem;
    }

    [data-testid="stMarkdownContainer"] th,
    [data-testid="stMarkdownContainer"] td {
        overflow-wrap: anywhere;
        word-break: break-word;
        vertical-align: top;
    }

    .report-block {
        border: 1px solid var(--mai-line);
        background: var(--mai-panel);
        border-radius: 8px;
        padding: 16px 18px;
        margin: 10px 0 14px;
    }

    .report-block h3 {
        color: var(--mai-text);
        margin: 0 0 10px;
        font-size: 1rem;
    }

    .report-block .stMarkdown {
        color: var(--mai-muted);
    }

    div[data-testid="stExpander"] {
        border-color: var(--mai-line) !important;
        background: var(--mai-expander-bg) !important;
        border-radius: 8px;
    }

    div[data-testid="stExpander"] details {
        border-color: var(--mai-line) !important;
        background: var(--mai-panel) !important;
    }

    div[data-testid="stExpander"] summary {
        background: var(--mai-status-header-bg) !important;
        color: var(--mai-status-header-text) !important;
    }

    div[data-testid="stExpander"] summary:hover,
    div[data-testid="stExpander"] summary:focus-visible {
        background: var(--mai-status-header-bg) !important;
    }

    div[data-testid="stExpander"] summary *,
    div[data-testid="stExpander"] summary p,
    div[data-testid="stExpander"] summary span,
    div[data-testid="stExpander"] summary svg {
        color: var(--mai-status-header-text) !important;
        fill: currentColor !important;
        stroke: currentColor !important;
    }

    div[data-testid="stExpanderDetails"] {
        border-top-color: var(--mai-line) !important;
        background: var(--mai-panel) !important;
        color: var(--mai-text) !important;
    }

    div[data-testid="stExpanderDetails"] [data-testid="stMarkdownContainer"],
    div[data-testid="stExpanderDetails"] [data-testid="stMarkdownContainer"] p {
        color: var(--mai-text) !important;
    }

    div[data-testid="stFileUploader"] section {
        border-radius: 8px;
        border-color: var(--mai-info-line) !important;
        background: var(--mai-info-bg) !important;
    }

    div[data-testid="stFileUploader"] section p,
    div[data-testid="stFileUploader"] section span,
    div[data-testid="stFileUploader"] section small {
        color: var(--mai-upload-helper-text) !important;
    }

    div[data-testid="stFileUploader"] section button,
    div[data-testid="stFileUploader"] section button * {
        color: #f4f7fb !important;
        fill: currentColor !important;
    }

    div[data-testid="stStatusWidget"] {
        border-color: var(--mai-line) !important;
        background: var(--mai-panel) !important;
        color: var(--mai-text) !important;
    }

    div[data-testid="stStatusWidget"] > div:first-child {
        background: var(--mai-status-header-bg) !important;
        color: var(--mai-status-header-text) !important;
    }

    div[data-testid="stStatusWidget"] > div:first-child *,
    div[data-testid="stStatusWidget"] > div:first-child p,
    div[data-testid="stStatusWidget"] > div:first-child span {
        color: var(--mai-status-header-text) !important;
        fill: currentColor !important;
        stroke: currentColor !important;
    }

    div[data-testid="stStatusWidget"] [data-testid="stMarkdownContainer"],
    div[data-testid="stStatusWidget"] [data-testid="stMarkdownContainer"] p {
        color: var(--mai-text) !important;
    }

    button[data-baseweb="tab"] {
        color: var(--mai-muted) !important;
    }

    button[data-baseweb="tab"] p {
        color: inherit !important;
    }

    button[data-baseweb="tab"][aria-selected="true"] {
        color: var(--mai-teal) !important;
    }

    div[data-baseweb="tab-highlight"] {
        background-color: var(--mai-teal) !important;
    }

    div[data-testid="stButtonGroup"] div[data-baseweb="button-group"] {
        width: 100%;
        border: 1px solid var(--mai-line) !important;
        border-radius: 8px !important;
        background: var(--mai-panel) !important;
        overflow: hidden;
        box-shadow: none !important;
    }

    div[data-testid="stButtonGroup"] div[data-baseweb="button-group"] button {
        min-height: 34px;
        border-color: var(--mai-line) !important;
        background: var(--mai-panel) !important;
        color: var(--mai-muted) !important;
        box-shadow: none !important;
        font-weight: 720;
    }

    div[data-testid="stButtonGroup"] div[data-baseweb="button-group"] button * {
        color: inherit !important;
        fill: currentColor !important;
    }

    div[data-testid="stButtonGroup"] div[data-baseweb="button-group"] button:hover {
        background: var(--mai-soft) !important;
        color: var(--mai-text) !important;
    }

    div[data-testid="stButtonGroup"] div[data-baseweb="button-group"] button[aria-checked="true"] {
        border-color: var(--mai-info-line) !important;
        background: var(--mai-info-bg) !important;
        color: var(--mai-teal) !important;
        box-shadow: inset 0 0 0 1px var(--mai-info-line) !important;
    }

    .stButton > button {
        border-radius: 7px;
        min-height: 44px;
        font-weight: 720;
        color: var(--mai-button-text) !important;
        border-color: var(--mai-line) !important;
        background: var(--mai-button-bg) !important;
    }

    .stDownloadButton > button {
        border-radius: 7px;
        min-height: 44px;
        font-weight: 720;
        color: var(--mai-button-text) !important;
        border-color: var(--mai-line) !important;
        background: var(--mai-button-bg) !important;
    }

    @media (max-width: 1100px) {
        .agent-grid,
        .metric-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }
        .summary-grid {
            grid-template-columns: 1fr;
        }
        .report-grid,
        .report-grid.three {
            grid-template-columns: 1fr;
        }
        .report-metric-grid {
            grid-template-columns: repeat(3, minmax(0, 1fr));
        }
        .mai-title {
            font-size: 2.55rem;
        }
    }

    @media (max-width: 700px) {
        .agent-grid,
        .metric-grid {
            grid-template-columns: 1fr;
        }
        .report-metric-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }
        .report-fact-row {
            grid-template-columns: 1fr;
        }
        .report-detail-grid {
            grid-template-columns: 1fr;
        }
        .mai-hero {
            padding: 26px 22px;
        }
        .mai-title {
            font-size: 2.15rem;
        }
    }
    </style>
    """.replace("__MAI_THEME_OVERRIDE__", _theme_override_css(st.session_state.ui_theme)),
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="mai-hero">
        <div class="mai-kicker">Static analysis multi-agent system</div>
        <h1 class="mai-title">ModernizeAI</h1>
        <p class="mai-subtitle">
            Upload a legacy Java/Spring Boot or Node.js repository and generate an evidence-backed
            modernization report with architecture, dependency, security, testing, planning, and critic review.
        </p>
    </div>
    <div class="mai-notice">
        ModernizeAI performs static analysis only. It does not execute uploaded code, install dependencies,
        deploy applications, delete files, or perform migrations. All recommendations require human review.
    </div>
    """,
    unsafe_allow_html=True,
)

appearance_col, _ = st.columns([0.24, 0.76])
with appearance_col:
    st.segmented_control(
        "Appearance",
        APPEARANCE_OPTIONS,
        key="ui_theme",
        width="stretch",
    )


def _start_upload(uploaded_file) -> dict[str, Any]:
    files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/zip")}
    response = requests.post(f"{API_BASE_URL}/analyze/upload/start", files=files, timeout=120)
    response.raise_for_status()
    return response.json()


def _start_github(repo_url: str) -> dict[str, Any]:
    response = requests.post(f"{API_BASE_URL}/analyze/github/start", json={"repo_url": repo_url}, timeout=120)
    response.raise_for_status()
    return response.json()


def _get_json(path: str) -> dict[str, Any]:
    response = requests.get(f"{API_BASE_URL}{path}", timeout=120)
    response.raise_for_status()
    return response.json()


def _get_bytes(path: str) -> bytes:
    response = requests.get(f"{API_BASE_URL}{path}", timeout=120)
    response.raise_for_status()
    return response.content


def _metric_value(value: Any) -> str:
    if value is None:
        return "0"
    if isinstance(value, (list, tuple, set)):
        items = [str(item).strip().rstrip(".") for item in value if str(item).strip()]
        return "; ".join(items) if items else "None"
    return str(value)


def _escape(value: Any) -> str:
    return html.escape(_metric_value(value), quote=True)


def _listify(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item not in (None, "")]
    if isinstance(value, str):
        return [value] if value else []
    return [str(value)]


def _plain(value: Any, fallback: str = "None found") -> str:
    if value is None:
        return fallback
    if isinstance(value, str) and not value.strip():
        return fallback
    if isinstance(value, (list, tuple, set)) and not value:
        return fallback
    text = _metric_value(value)
    return text if text else fallback


def _path_stack(value: Any, limit: int = 6) -> str:
    paths = _listify(value)
    if not paths:
        return '<span class="report-muted">None found</span>'
    visible = paths[:limit]
    hidden = len(paths) - len(visible)
    chips = "".join(f"<code>{_escape(path)}</code>" for path in visible)
    if hidden:
        chips += f'<span class="path-more">+{hidden} more</span>'
    return f'<div class="path-stack">{chips}</div>'


def _severity_pill(value: Any) -> str:
    label = _plain(value, "Info")
    css = label.strip().lower()
    if css not in {"critical", "high", "medium", "low"}:
        css = "info"
    return f'<span class="severity-pill severity-{css}">{_escape(label)}</span>'


def _empty_report_state(message: str) -> str:
    return f'<div class="report-empty">{_escape(message)}</div>'


def _fact_table(rows: list[tuple[str, Any]]) -> str:
    rendered_rows = []
    for label, value in rows:
        rendered_rows.append(
            '<div class="report-fact-row">'
            f'<div class="report-fact-label">{_escape(label)}</div>'
            f'<div class="report-fact-value">{_escape(_plain(value))}</div>'
            '</div>'
        )
    return f'<div class="report-facts">{"".join(rendered_rows)}</div>'


def _report_metric_strip(cards: list[tuple[str, Any]]) -> str:
    rendered_cards = []
    for label, value in cards:
        rendered_cards.append(
            '<div class="report-mini-metric">'
            f'<div class="report-mini-label">{_escape(label)}</div>'
            f'<div class="report-mini-value">{_escape(value)}</div>'
            '</div>'
        )
    return f'<div class="report-metric-grid">{"".join(rendered_cards)}</div>'


def _report_table(headers: list[str], rows: list[list[str]], empty_message: str, compact: bool = False) -> str:
    if not rows:
        return _empty_report_state(empty_message)
    header_cells = "".join(f"<th>{_escape(header)}</th>" for header in headers)
    body_rows = []
    expected_width = len(headers)
    for row in rows:
        padded = row[:expected_width] + [""] * max(0, expected_width - len(row))
        body_rows.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in padded) + "</tr>")
    css_class = "report-table compact" if compact else "report-table"
    return (
        '<div class="report-table-wrap">'
        f'<table class="{css_class}"><thead><tr>{header_cells}</tr></thead>'
        f'<tbody>{"".join(body_rows)}</tbody></table>'
        '</div>'
    )


def _simple_card(title: str, body: Any, eyebrow: str | None = None) -> str:
    eyebrow_markup = f'<div class="report-eyebrow">{_escape(eyebrow)}</div>' if eyebrow else ""
    return (
        '<section class="report-card">'
        f"{eyebrow_markup}"
        f'<h3>{_escape(title)}</h3>'
        f'<p>{_escape(_plain(body))}</p>'
        '</section>'
    )


def _status_label(status: str) -> str:
    labels = {
        "pending": "Pending",
        "running": "Running",
        "completed": "Completed",
        "skipped": "Skipped",
        "revisited": "Revisited",
        "failed": "Failed",
    }
    return labels.get(status, status.replace("_", " ").title() if status else "Pending")


def _progress_map(steps: list[dict[str, str]] | None) -> dict[str, str]:
    return {step.get("name", ""): step.get("status", "pending") for step in steps or []}


def _graph_node_map(agent_graph: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(agent_graph, dict):
        return {}
    return {
        node.get("id", ""): node
        for node in agent_graph.get("nodes", [])
        if isinstance(node, dict) and node.get("id")
    }


def _agent_status(agent: dict[str, str], progress: dict[str, str], graph_nodes: dict[str, dict[str, Any]]) -> tuple[str, int]:
    graph_node = graph_nodes.get(agent["key"], {})
    status = graph_node.get("status") or progress.get(agent.get("progress_key", agent["key"]), "pending")
    run_count = int(graph_node.get("run_count") or 0)
    return str(status), run_count


def _node_style(status: str) -> tuple[str, str, str]:
    if status == "running":
        return "#e8fffc", "#087f78", "#087f78"
    if status in {"completed", "revisited"}:
        return "#ebfff0", "#237a3a", "#237a3a"
    if status == "failed":
        return "#fff0f0", "#b4232d", "#b4232d"
    if status == "skipped":
        return "#f3f6fa", "#8a94a6", "#596171"
    return "#ffffff", "#c8d2df", "#596171"


def _render_agent_graph_svg(agent_graph: dict[str, Any] | None) -> str:
    graph_nodes = _graph_node_map(agent_graph)
    if not graph_nodes:
        return '<div class="agent-graph-shell"><div class="report-empty">The live graph will appear once analysis starts.</div></div>'

    active_ids: list[str] = []
    for edge in (agent_graph or {}).get("edges", []):
        for node_id in (edge.get("source"), edge.get("target")):
            if node_id and node_id in graph_nodes and node_id not in active_ids:
                active_ids.append(node_id)
    for node_id, node in graph_nodes.items():
        if node.get("status") not in {"pending", None} and node_id not in active_ids:
            active_ids.append(node_id)
    if not active_ids:
        active_ids = ["ingestion", "repo_scanner", "supervisor"]

    width = 980
    cell_w = 220
    cell_h = 96
    gap_x = 24
    gap_y = 34
    cols = 4
    positions: dict[str, tuple[int, int]] = {}
    for index, node_id in enumerate(active_ids):
        col = index % cols
        row = index // cols
        positions[node_id] = (24 + col * (cell_w + gap_x), 24 + row * (cell_h + gap_y))
    height = 24 + ((len(active_ids) - 1) // cols + 1) * (cell_h + gap_y) + 20

    svg_parts = [
        f'<svg class="agent-graph-svg" viewBox="0 0 {width} {height}" role="img" aria-label="Live agent graph">',
        '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" fill="#7a8597"/></marker></defs>',
    ]
    for edge in (agent_graph or {}).get("edges", []):
        source = edge.get("source")
        target = edge.get("target")
        if source not in positions or target not in positions:
            continue
        sx, sy = positions[source]
        tx, ty = positions[target]
        x1 = sx + cell_w
        y1 = sy + cell_h / 2
        x2 = tx
        y2 = ty + cell_h / 2
        if tx <= sx:
            x1 = sx + cell_w / 2
            y1 = sy + cell_h
            x2 = tx + cell_w / 2
            y2 = ty
        svg_parts.append(
            f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" stroke="#7a8597" stroke-width="1.6" marker-end="url(#arrow)" opacity="0.72"/>'
        )

    for node_id in active_ids:
        node = graph_nodes[node_id]
        x, y = positions[node_id]
        status = str(node.get("status", "pending"))
        fill, stroke, text_color = _node_style(status)
        label = _escape(node.get("label", node_id))
        status_text = _escape(_status_label(status))
        run_count = int(node.get("run_count") or 0)
        count_text = f" x{run_count}" if run_count > 1 else ""
        svg_parts.append(
            f'<rect x="{x}" y="{y}" width="{cell_w}" height="{cell_h}" rx="8" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'
            f'<text x="{x + 14}" y="{y + 31}" fill="{text_color}" font-size="15" font-weight="700">{label}</text>'
            f'<text x="{x + 14}" y="{y + 58}" fill="#596171" font-size="12">{status_text}{count_text}</text>'
        )
    svg_parts.append("</svg>")

    edge_rows = []
    for edge in (agent_graph or {}).get("edges", [])[-8:]:
        source = graph_nodes.get(edge.get("source"), {}).get("label", edge.get("source", ""))
        target = graph_nodes.get(edge.get("target"), {}).get("label", edge.get("target", ""))
        label = edge.get("label", "")
        edge_rows.append(
            f'<div class="decision-row"><strong>{_escape(source)} -> {_escape(target)}</strong>: {_escape(label)}</div>'
        )
    trace = f'<div class="decision-trace">{"".join(edge_rows)}</div>' if edge_rows else ""
    return f'<div class="agent-graph-shell">{"".join(svg_parts)}{trace}</div>'


def _render_decision_trace(decisions: list[dict[str, Any]] | None) -> str:
    if not decisions:
        return '<div class="decision-row">Supervisor decisions will appear as the graph forms.</div>'
    rows = []
    for decision in decisions[-6:]:
        rows.append(
            '<div class="decision-row">'
            f'<strong>Iteration {_escape(decision.get("iteration", ""))}: Supervisor selected {_escape(decision.get("agent_label", decision.get("next_agent", "")))}</strong>'
            f' because {_escape(decision.get("rationale", "no rationale recorded"))}'
            '</div>'
        )
    return f'<div class="decision-trace">{"".join(rows)}</div>'


def _render_agent_board(status_payload: dict[str, Any] | None = None) -> None:
    status_payload = status_payload or {}
    progress = _progress_map(status_payload.get("steps"))
    graph = status_payload.get("agent_graph")
    graph_nodes = _graph_node_map(graph)
    cards: list[str] = []
    for index, agent in enumerate(AGENTS, start=1):
        status, run_count = _agent_status(agent, progress, graph_nodes)
        css_status = status if status in {"completed", "running", "failed", "skipped", "revisited"} else "pending"
        run_badge = f" x{run_count}" if run_count > 1 else ""
        cards.append(
            f'<div class="agent-card {css_status}">'
            '<div class="agent-top">'
            f'<span class="agent-index">{index:02d}</span>'
            f'<span class="agent-status">{_escape(_status_label(status))}{run_badge}</span>'
            '</div>'
            f'<div class="agent-name">{_escape(agent["name"])}</div>'
            f'<p class="agent-role">{_escape(agent["role"])}</p>'
            '</div>'
        )
    _html(
        '<div class="mai-section-title">Live Agent Graph</div>'
        '<div class="mai-section-copy">The Supervisor builds this graph at runtime as it selects, skips, or revisits specialist agents.</div>'
        f'<div class="agent-grid">{"".join(cards)}</div>'
        + _render_agent_graph_svg(graph)
        + '<div class="mai-section-title">Decision Trace</div>'
        + _render_decision_trace(status_payload.get("agent_decisions"))
    )


def _update_agent_board(slot, status_payload: dict[str, Any] | None = None) -> None:
    slot.empty()
    with slot.container():
        _render_agent_board(status_payload)


def _wait_for_analysis(result: dict[str, Any], board_slot) -> dict[str, Any]:
    analysis_id = result["analysis_id"]
    st.session_state.analysis_id = analysis_id
    while True:
        status_payload = _get_json(f"/analysis/{analysis_id}/status")
        _update_agent_board(board_slot, status_payload)
        status = status_payload.get("status")
        if status == "completed":
            return result
        if status == "failed":
            raise RuntimeError(status_payload.get("error") or "Analysis failed. Check the API logs for the agent error.")
        time.sleep(0.5)


def _render_metric_cards(cards: list[tuple[str, Any]]) -> None:
    html_cards = [
        '<div class="metric-card">'
        f'<div class="metric-label">{_escape(label)}</div>'
        f'<div class="metric-value">{_escape(value)}</div>'
        '</div>'
        for label, value in cards
    ]
    _html(f'<div class="metric-grid">{"".join(html_cards)}</div>')


def _render_summary_panels(evidence: dict[str, Any]) -> None:
    metadata = evidence.get("repo_metadata", {})
    architecture = evidence.get("architecture_report", {})
    security = evidence.get("security_report", {})
    critic = evidence.get("critic_findings", {})
    vector_index = metadata.get("vector_index", {})
    warnings = critic.get("warnings", [])
    blocked_count = len(critic.get("blocked_claims", []))
    approved_count = len(_approved_candidates(evidence))
    warning_text = warnings[0].get("message") if warnings else "No critic warnings are currently blocking the report."
    model = _reasoning_model(evidence)
    _html(
        '<div class="summary-grid">'
        '<div class="summary-panel">'
        '<h3>Repository Signal</h3>'
        '<p>'
        f'Framework: {_escape(metadata.get("framework", "unknown"))}. '
        f'Indexed files: {_escape((metadata.get("file_counts") or {}).get("indexed_files", 0))}. '
        f'Chunks indexed: {_escape(vector_index.get("chunks_indexed", 0))}. '
        f'Detected databases: {_escape(metadata.get("detected_databases", []) or "None found")}.'
        '</p>'
        '</div>'
        '<div class="summary-panel">'
        '<h3>Reasoning and Guardrails</h3>'
        '<p>'
        f'Security findings: {_escape(len(security.get("findings", [])))}. '
        f'Reasoning model: {_escape(model)}. '
        f'Critic review: {_escape(critic.get("overall_confidence", "Medium"))}; '
        f'{_escape(blocked_count)} blocked claims; {_escape(approved_count)} approved service candidates. '
        f'{_escape(warning_text)}'
        '</p>'
        '</div>'
        '</div>'
    )


def _split_report_sections(report_markdown: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current_title = "Preamble"
    current_lines: list[str] = []
    for line in report_markdown.splitlines():
        match = re.match(r"^##\s+(.+)$", line)
        if match:
            sections[current_title] = current_lines
            current_title = match.group(1).strip()
            current_lines = []
            continue
        if line.startswith("# ModernizeAI Modernization Report"):
            continue
        current_lines.append(line)
    sections[current_title] = current_lines
    return {title: "\n".join(lines).strip() for title, lines in sections.items() if "\n".join(lines).strip()}


def _section(sections: dict[str, str], prefix: str) -> str:
    for title, body in sections.items():
        if title.startswith(prefix):
            return body
    return ""


def _render_section_block(title: str, body: str, empty_text: str = "No evidence available for this section.") -> None:
    with st.container(border=True):
        st.markdown(f"#### {title}")
        if body:
            st.markdown(body)
        else:
            st.caption(empty_text)


def _section_intro(body: str) -> str:
    if not body:
        return ""
    return re.split(r"\n\s*\|", body, maxsplit=1)[0].strip()


def _report_detail(label: str, value_html: str) -> str:
    return (
        '<div class="report-detail">'
        f'<div class="report-detail-label">{_escape(label)}</div>'
        f'<div class="report-detail-value">{value_html}</div>'
        '</div>'
    )


def _report_section_heading(title: str, subtitle: str | None = None) -> str:
    subtitle_markup = f"<p>{_escape(subtitle)}</p>" if subtitle else ""
    return f'<div class="report-section-heading"><h3>{_escape(title)}</h3>{subtitle_markup}</div>'


def _render_overview_tab(sections: dict[str, str], evidence: dict[str, Any]) -> None:
    metadata = evidence.get("repo_metadata", {})
    architecture = evidence.get("architecture_report", {})
    security = evidence.get("security_report", {})
    test_report = evidence.get("test_report", {})
    critic = evidence.get("critic_findings", {})
    file_counts = metadata.get("file_counts") or {}

    executive_summary = _section(sections, "1. Executive Summary")
    architecture_summary = architecture.get("architecture_summary") or _section_intro(
        _section(sections, "3. Architecture Summary")
    )

    summary_markup = (
        '<section class="report-summary-card">'
        '<div class="report-eyebrow">Executive Summary</div>'
        f'<h2 class="report-title">{_escape(metadata.get("framework", "Application"))} modernization assessment</h2>'
        f'<p>{_escape(executive_summary or "No executive summary generated.")}</p>'
        '</section>'
    )

    metrics_markup = _report_metric_strip(
        [
            ("Framework", metadata.get("framework", "unknown")),
            ("Controllers", len(metadata.get("controllers", []))),
            ("Services", len(metadata.get("services", []))),
            ("Security", len(security.get("findings", []))),
            ("Test Gaps", len(test_report.get("missing_test_areas", []))),
            ("Critic Review", critic.get("overall_confidence", "Medium")),
        ]
    )

    repository_facts = _fact_table(
        [
            ("Languages", metadata.get("languages", [])),
            ("Build Tools", metadata.get("build_tools", [])),
            ("Repositories", len(metadata.get("repositories", []))),
            ("Test Files", len(metadata.get("test_files", []))),
            ("Indexed Files", file_counts.get("indexed_files", 0)),
            ("Detected Databases", metadata.get("detected_databases", []) or "None found"),
        ]
    )

    overview_markup = (
        summary_markup
        + metrics_markup
        + '<div class="report-grid">'
        + '<section class="report-card">'
        + '<div class="report-eyebrow">Repository Overview</div>'
        + '<h3>Repository signal</h3>'
        + repository_facts
        + '</section>'
        + _simple_card("Architecture Summary", architecture_summary or "No architecture summary generated.", "Architecture")
        + '</div>'
    )

    layer_cards: list[str] = []
    for layer in architecture.get("layers", []):
        layer_cards.append(
            '<article class="layer-card">'
            '<div class="layer-card-top">'
            f'<div class="layer-name">{_escape(layer.get("name", "Layer"))}</div>'
            f'<span class="severity-pill severity-info">{_escape(len(_listify(layer.get("files"))))} files</span>'
            '</div>'
            f'<p class="layer-role">{_escape(layer.get("responsibility", "No responsibility summary generated."))}</p>'
            f'{_path_stack(layer.get("files"))}'
            '</article>'
        )

    if layer_cards:
        overview_markup += (
            _report_section_heading("Architecture Layers", "Layer responsibilities and supporting file evidence.")
            + f'<div class="layer-stack">{"".join(layer_cards)}</div>'
        )
    else:
        overview_markup += _report_section_heading("Architecture Layers") + _empty_report_state(
            "No architecture layers were generated."
        )

    api_items = architecture.get("api_inventory") or metadata.get("api_inventory", [])
    api_rows = [
        [
            f'<span class="severity-pill severity-info">{_escape(item.get("method", "HTTP"))}</span>',
            f'<span class="report-code">{_escape(item.get("path", ""))}</span>',
            _path_stack(item.get("file"), limit=1),
            f'<span class="report-code">{_escape(item.get("evidence", ""))}</span>',
        ]
        for item in api_items
    ]
    overview_markup += _report_section_heading("API Inventory")
    overview_markup += _report_table(["Method", "Path", "File", "Evidence"], api_rows, "No API inventory found.")
    _html(overview_markup)


def _finding_cards(title: str, items: list[dict[str, Any]], empty_message: str) -> str:
    if not items:
        return _report_section_heading(title) + _empty_report_state(empty_message)
    cards = []
    for item in items:
        details = [
            _report_detail("File", _path_stack(item.get("file"), limit=1)),
            _report_detail("Evidence", f'<span class="report-code">{_escape(item.get("evidence", "None found"))}</span>'),
            _report_detail("Recommendation", _escape(item.get("recommendation", "No recommendation generated."))),
        ]
        cards.append(
            '<section class="report-list-card">'
            '<div class="report-card-top">'
            f'<div class="report-item-title">{_escape(item.get("title", "Finding"))}</div>'
            f'{_severity_pill(item.get("severity"))}'
            '</div>'
            f'<div class="report-detail-grid">{"".join(details)}</div>'
            '</section>'
        )
    return _report_section_heading(title) + f'<div class="report-card-stack">{"".join(cards)}</div>'


def _test_cards(items: list[dict[str, Any]]) -> str:
    if not items:
        return _report_section_heading("Recommended Tests") + _empty_report_state("No test recommendations generated.")
    cards = []
    for item in items:
        details = [
            _report_detail("Target", _escape(item.get("target", "Unknown target"))),
            _report_detail("Evidence", _escape(item.get("evidence", "None found"))),
        ]
        cards.append(
            '<section class="report-list-card">'
            '<div class="report-card-top">'
            f'<div class="report-item-title">{_escape(item.get("suggestion", "Add tests for this area."))}</div>'
            f'{_severity_pill(item.get("type", "Test"))}'
            '</div>'
            f'<div class="report-detail-grid">{"".join(details)}</div>'
            '</section>'
        )
    return _report_section_heading("Recommended Tests") + f'<div class="report-card-stack">{"".join(cards)}</div>'


def _render_findings_tab(sections: dict[str, str], evidence: dict[str, Any]) -> None:
    dependency = evidence.get("dependency_report", {})
    security = evidence.get("security_report", {})
    test_report = evidence.get("test_report", {})
    dependency_summary = dependency.get("dependency_summary") or _section_intro(_section(sections, "5. Dependency Risk Report"))
    security_summary = security.get("risk_summary") or _section_intro(_section(sections, "6. Security Findings"))
    test_summary = test_report.get("test_summary") or _section_intro(_section(sections, "9. Test Strategy"))

    markup = (
        '<div class="report-grid three">'
        + _simple_card("Dependency Signal", dependency_summary or "No dependency summary generated.", "Dependencies")
        + _simple_card("Security Signal", security_summary or "No security summary generated.", "Security")
        + _simple_card("Test Signal", test_summary or "No test strategy generated.", "Testing")
        + '</div>'
        + _finding_cards(
            "Dependency Risks",
            dependency.get("potential_risks", []),
            "No dependency risks were generated from the available evidence.",
        )
        + _finding_cards(
            "Security Findings",
            security.get("findings", []),
            "No security findings were generated from the available evidence.",
        )
        + _test_cards(test_report.get("recommended_tests", []))
    )
    _html(markup)


def _phase_cards(phases: list[dict[str, Any]]) -> str:
    if not phases:
        return _empty_report_state("No migration roadmap generated.")
    cards = []
    for phase in phases:
        tasks = "".join(f"<li>{_escape(task)}</li>" for task in phase.get("tasks", []))
        cards.append(
            '<section class="report-phase-card">'
            '<div class="report-card-top">'
            f'<div class="report-item-title">{_escape(phase.get("phase", "Phase"))} - {_escape(phase.get("title", "Untitled"))}</div>'
            f'{_severity_pill(phase.get("confidence", "Plan"))}'
            '</div>'
            f'<ul class="phase-steps">{tasks or "<li>No tasks generated.</li>"}</ul>'
            '</section>'
        )
    return f'<div class="report-card-stack">{"".join(cards)}</div>'


def _candidate_cards(candidates: list[dict[str, Any]]) -> str:
    if not candidates:
        return _empty_report_state("No service boundary candidates generated.")
    cards = []
    for candidate in candidates:
        details = [
            _report_detail("Files", _path_stack(candidate.get("files"))),
            _report_detail("Reasoning", _escape(candidate.get("reasoning", "No reasoning generated."))),
            _report_detail("Risks", _escape(candidate.get("risks", "No risks generated."))),
        ]
        cards.append(
            '<section class="report-list-card">'
            '<div class="report-card-top">'
            f'<div class="report-item-title">{_escape(candidate.get("name", "Service Candidate"))}</div>'
            f'{_severity_pill(candidate.get("confidence", "Medium"))}'
            '</div>'
            f'<div class="report-detail-grid">{"".join(details)}</div>'
            '</section>'
        )
    return f'<div class="report-card-stack">{"".join(cards)}</div>'


def _blocked_claims(evidence: dict[str, Any]) -> set[str]:
    critic = evidence.get("critic_findings", {})
    return {
        str(item.get("claim", "")).strip()
        for item in critic.get("blocked_claims", [])
        if item.get("claim")
    }


def _approved_candidates(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    modernization = evidence.get("modernization_plan", {})
    blocked = _blocked_claims(evidence)
    return [
        candidate
        for candidate in modernization.get("microservice_candidates", [])
        if candidate.get("name") not in blocked
    ]


def _api_count(evidence: dict[str, Any]) -> int:
    metadata = evidence.get("repo_metadata", {})
    architecture = evidence.get("architecture_report", {})
    return len(architecture.get("api_inventory") or metadata.get("api_inventory", []))


def _reasoning_model(evidence: dict[str, Any]) -> str:
    for key in (
        "architecture_report",
        "dependency_report",
        "security_report",
        "test_report",
        "modernization_plan",
        "critic_findings",
    ):
        model = str((evidence.get(key) or {}).get("llm_model_id", "")).strip()
        if model:
            return model
    return "Not reported"


def _confidence_context(critic: dict[str, Any]) -> str:
    confidence = critic.get("overall_confidence", "Medium")
    blocked_count = len(critic.get("blocked_claims", []))
    if str(confidence).lower() == "low":
        return (
            f"{confidence} reflects static-only evidence limits and {blocked_count} blocked claim(s); "
            "it is a guardrail signal, not a failed analysis."
        )
    if blocked_count:
        return f"{confidence} with {blocked_count} blocked claim(s) separated into Critic Review."
    return f"{confidence}; no unsupported claims were found by the Critic Agent."


def _analysis_snapshot_markup(evidence: dict[str, Any]) -> str:
    metadata = evidence.get("repo_metadata", {})
    security = evidence.get("security_report", {})
    test_report = evidence.get("test_report", {})
    critic = evidence.get("critic_findings", {})
    indexed_files = (metadata.get("file_counts") or {}).get("indexed_files", 0)
    blocked_count = len(critic.get("blocked_claims", []))
    approved_count = len(_approved_candidates(evidence))
    model = _reasoning_model(evidence)
    return (
        '<section class="report-summary-card">'
        '<div class="report-eyebrow">Analysis Snapshot</div>'
        '<h2 class="report-title">Grounded evidence with agent review</h2>'
        '<p>'
        'Static scanners collect file-level facts first. The Supervisor Agent then coordinates specialist agents, '
        'records each routing decision, and uses critic feedback before final reporting.'
        '</p>'
        + _report_metric_strip(
            [
                ("Framework", metadata.get("framework", "unknown")),
                ("Reasoning Model", model),
                ("Indexed", indexed_files),
                ("APIs", _api_count(evidence)),
                ("Security", len(security.get("findings", []))),
                ("Test Gaps", len(test_report.get("missing_test_areas", []))),
                ("Decisions", len(evidence.get("agent_decisions", []))),
                ("Guardrails", f"{blocked_count} blocked / {approved_count} candidates"),
            ]
        )
        + f'<p>{_escape(_confidence_context(critic))}</p>'
        '</section>'
    )


def _bullet_panel(title: str, items: list[Any], empty_message: str) -> str:
    if not items:
        body = _empty_report_state(empty_message)
    else:
        bullets = []
        for item in items:
            if isinstance(item, dict):
                text = item.get("task") or item.get("title") or item.get("recommendation") or item.get("message") or str(item)
            else:
                text = str(item)
            bullets.append(f"<li>{_escape(text)}</li>")
        body = f'<ul class="phase-steps">{"".join(bullets)}</ul>'
    return f'<section class="report-card"><h3>{_escape(title)}</h3>{body}</section>'


def _refactoring_panel(modernization: dict[str, Any]) -> str:
    opportunities = modernization.get("refactoring_opportunities") or []
    if not opportunities:
        return _bullet_panel(
            "Refactoring Opportunities",
            modernization.get("containerization_plan", []) + modernization.get("ci_cd_plan", []),
            "No refactoring opportunities generated.",
        )
    cards = []
    for item in opportunities:
        details = [
            _report_detail("Rationale", _escape(item.get("rationale", "No rationale generated."))),
            _report_detail("Action", _escape(item.get("action", "No action generated."))),
            _report_detail("Evidence", _escape(item.get("evidence", "No evidence generated."))),
        ]
        cards.append(
            '<section class="report-list-card">'
            '<div class="report-card-top">'
            f'<div class="report-item-title">{_escape(item.get("title", "Refactoring Opportunity"))}</div>'
            f'{_severity_pill(item.get("priority", "Medium"))}'
            '</div>'
            f'<div class="report-detail-grid">{"".join(details)}</div>'
            '</section>'
        )
    return _report_section_heading("Refactoring Opportunities") + f'<div class="report-card-stack">{"".join(cards)}</div>'


def _render_roadmap_tab(evidence: dict[str, Any]) -> None:
    modernization = evidence.get("modernization_plan", {})
    markup = (
        _report_section_heading("Cloud Modernization Roadmap")
        + _phase_cards(modernization.get("phased_roadmap", []))
        + _report_section_heading("Suggested Microservice Boundaries")
        + _candidate_cards(_approved_candidates(evidence))
        + _refactoring_panel(modernization)
        + '<div class="report-grid three">'
        + _bullet_panel("Risks", modernization.get("risks", []), "No risks generated.")
        + _bullet_panel("Assumptions", modernization.get("assumptions", []), "No assumptions generated.")
        + '</div>'
    )
    _html(markup)


def _evidence_rows(evidence: dict[str, Any]) -> list[list[str]]:
    metadata = evidence.get("repo_metadata", {})
    architecture = evidence.get("architecture_report", {})
    dependency = evidence.get("dependency_report", {})
    security = evidence.get("security_report", {})
    test_report = evidence.get("test_report", {})
    rows: list[list[str]] = []

    for key in ["controllers", "services", "repositories", "entities", "config_files", "dependency_files", "test_files"]:
        for item in metadata.get(key, []):
            rows.append([_escape(key), _path_stack(item.get("file"), limit=1), _escape(item.get("evidence", ""))])
    for item in architecture.get("evidence", []):
        rows.append([_escape("architecture"), _path_stack(item.get("file"), limit=1), _escape(item.get("evidence", ""))])
    for item in dependency.get("potential_risks", []):
        rows.append([_escape("dependency"), _path_stack(item.get("file"), limit=1), _escape(item.get("evidence", ""))])
    for item in security.get("findings", []):
        rows.append([_escape("security"), _path_stack(item.get("file"), limit=1), _escape(item.get("evidence", ""))])
    for item in test_report.get("recommended_tests", []):
        rows.append([_escape("test"), _escape(item.get("target", "")), _escape(item.get("evidence", ""))])
    return rows


def _render_critic_tab(evidence: dict[str, Any]) -> None:
    critic = evidence.get("critic_findings", {})
    blocked = critic.get("blocked_claims", [])
    warnings = critic.get("warnings", [])

    blocked_cards = []
    for item in blocked:
        details = [
            _report_detail("Reason", _escape(item.get("reason", "No reason generated."))),
            _report_detail("Action", _escape(item.get("action", "No action generated."))),
        ]
        blocked_cards.append(
            '<section class="report-list-card">'
            f'<div class="report-item-title">{_escape(item.get("claim", "Blocked claim"))}</div>'
            f'<div class="report-detail-grid">{"".join(details)}</div>'
            '</section>'
        )

    warning_cards = []
    for warning in warnings:
        message = warning.get("message", warning) if isinstance(warning, dict) else warning
        warning_cards.append(
            '<section class="report-list-card">'
            f'<p class="report-item-copy">{_escape(message)}</p>'
            '</section>'
        )

    markup = (
        '<div class="report-grid">'
        + _simple_card("Evidence Confidence", _confidence_context(critic), "Critic Review")
        + _simple_card(
            "Guardrail Result",
            "Unsupported claims are listed below when the critic finds them."
            if blocked
            else "No unsupported claims were found by the critic checks.",
            "Claims",
        )
        + '</div>'
        + _report_section_heading("Blocked Claims")
        + (f'<div class="report-card-stack">{"".join(blocked_cards)}</div>' if blocked_cards else _empty_report_state("No blocked claims."))
        + _report_section_heading("Warnings")
        + (f'<div class="report-card-stack">{"".join(warning_cards)}</div>' if warning_cards else _empty_report_state("No critic warnings."))
        + _report_section_heading("Evidence Appendix")
        + _report_table(["Source", "File/Target", "Evidence"], _evidence_rows(evidence), "No evidence appendix generated.")
    )
    _html(markup)


def _render_report_workspace(report_markdown: str, analysis_id: str, evidence: dict[str, Any] | None) -> None:
    sections = _split_report_sections(report_markdown)
    evidence = evidence or {}
    _html(
        '<div class="report-header">'
        '<h2>Modernization Report</h2>'
        '<p>'
        'Grounded static evidence, agent analysis, and critic guardrails in one reviewable output.'
        '</p>'
        '</div>'
    )
    if evidence:
        _html(_analysis_snapshot_markup(evidence))

    markdown_col, word_col, id_col = st.columns([0.22, 0.20, 0.58])
    with markdown_col:
        st.download_button(
            "Download Markdown",
            data=report_markdown,
            file_name=f"modernizeai-report-{analysis_id}.md",
            mime="text/markdown",
            use_container_width=True,
        )
    with word_col:
        try:
            docx_bytes = _get_bytes(f"/analysis/{analysis_id}/report.docx") if analysis_id else b""
            st.download_button(
                "Download Word",
                data=docx_bytes,
                file_name=f"modernizeai-report-{analysis_id}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
                disabled=not docx_bytes,
            )
        except Exception:
            st.caption("Word export unavailable")
    with id_col:
        _html(f'<div class="report-meta">Analysis ID: <code>{_escape(analysis_id)}</code></div>')

    overview_tab, findings_tab, roadmap_tab, critic_tab, full_tab = st.tabs(
        ["Overview", "Findings", "Roadmap", "Critic & Evidence", "Full Markdown"]
    )

    with overview_tab:
        _render_overview_tab(sections, evidence)

    with findings_tab:
        _render_findings_tab(sections, evidence)

    with roadmap_tab:
        _render_roadmap_tab(evidence)

    with critic_tab:
        _render_critic_tab(evidence)

    with full_tab:
        st.code(report_markdown, language="markdown")


if "analysis_id" not in st.session_state:
    st.session_state.analysis_id = None
if "report" not in st.session_state:
    st.session_state.report = None
if "evidence" not in st.session_state:
    st.session_state.evidence = None

status_payload: dict[str, Any] = {"steps": []}
if st.session_state.analysis_id:
    try:
        status_payload = _get_json(f"/analysis/{st.session_state.analysis_id}/status")
    except Exception:
        status_payload = {"steps": []}

agent_board_slot = st.empty()
_update_agent_board(agent_board_slot, status_payload)

left, right = st.columns([1.05, 0.95], gap="large")

with left:
    st.markdown('<div class="mai-section-title">Analyze Repository</div>', unsafe_allow_html=True)
    upload_tab, github_tab = st.tabs(["Upload ZIP", "GitHub URL"])

    with upload_tab:
        uploaded_file = st.file_uploader("Repository ZIP", type=["zip"], accept_multiple_files=False)
        if st.button("Analyze Repository", key="analyze_upload", type="primary", disabled=uploaded_file is None):
            with st.status("Analyzing repository...", expanded=True) as status:
                try:
                    st.write("Running scanner and Supervisor-selected specialist agents")
                    result = _wait_for_analysis(_start_upload(uploaded_file), agent_board_slot)
                    st.session_state.report = _get_json(result["report_url"])
                    st.session_state.evidence = _get_json(f"/analysis/{result['analysis_id']}/evidence")
                    status.update(label="Analysis completed", state="complete")
                    st.rerun()
                except Exception as exc:
                    status.update(label="Analysis failed", state="error")
                    st.error(str(exc))

    with github_tab:
        repo_url = st.text_input("GitHub repository URL", placeholder="https://github.com/user/repo")
        if st.button("Analyze Repository", key="analyze_github", type="primary", disabled=not repo_url.strip()):
            with st.status("Downloading and analyzing repository...", expanded=True) as status:
                try:
                    st.write("Running scanner and Supervisor-selected specialist agents")
                    result = _wait_for_analysis(_start_github(repo_url.strip()), agent_board_slot)
                    st.session_state.report = _get_json(result["report_url"])
                    st.session_state.evidence = _get_json(f"/analysis/{result['analysis_id']}/evidence")
                    status.update(label="Analysis completed", state="complete")
                    st.rerun()
                except Exception as exc:
                    status.update(label="Analysis failed", state="error")
                    st.error(str(exc))

with right:
    st.markdown('<div class="mai-section-title">Analysis Workflow</div>', unsafe_allow_html=True)
    _html(
        '<div class="summary-panel">'
        '<h3>Grounded modernization assessment</h3>'
        '<p>'
        'ModernizeAI scans repository evidence first, coordinates specialist agents for architecture, security, '
        'dependencies, testing, and modernization, then applies critic guardrails before producing the final report.'
        '</p>'
        '</div>'
    )


if st.session_state.evidence:
    evidence = st.session_state.evidence
    metadata = evidence.get("repo_metadata", {})
    security = evidence.get("security_report", {})
    test_report = evidence.get("test_report", {})
    modernization = evidence.get("modernization_plan", {})
    critic = evidence.get("critic_findings", {})

    st.markdown('<div class="mai-section-title">Analysis Dashboard</div>', unsafe_allow_html=True)
    _render_summary_panels(evidence)
    _render_metric_cards(
        [
            ("Framework", metadata.get("framework", "unknown")),
            ("Controllers", len(metadata.get("controllers", []))),
            ("Services", len(metadata.get("services", []))),
            ("Repositories", len(metadata.get("repositories", []))),
            ("Security Findings", len(security.get("findings", []))),
            ("Missing Test Areas", len(test_report.get("missing_test_areas", []))),
            ("Service Candidates", len(_approved_candidates(evidence))),
            ("Critic Confidence", critic.get("overall_confidence", "Medium")),
        ]
    )

if st.session_state.report:
    report_markdown = st.session_state.report.get("report_markdown", "")
    _render_report_workspace(
        report_markdown,
        st.session_state.analysis_id,
        st.session_state.evidence,
    )
