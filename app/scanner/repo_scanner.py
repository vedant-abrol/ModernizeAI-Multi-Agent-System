from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from app.config import settings
from app.guardrails.prompt_injection import detect_prompt_injection
from app.guardrails.secret_redactor import redact_secrets
from app.ingestion.file_classifier import classify_file, is_allowed_file, language_for_path, should_skip_path
from app.ingestion.repo_sanitizer import safe_relative_path
from app.scanner.dependency_parser import parse_dependency_file
from app.scanner.java_scanner import class_name_from_java, extract_java_dependencies, extract_spring_endpoints
from app.scanner.node_scanner import extract_express_endpoints


DATABASE_PATTERNS = {
    "mysql": ["mysql-connector", "jdbc:mysql", "mysql2"],
    "postgres": ["postgresql", "jdbc:postgresql", "pg"],
    "mongodb": ["mongodb", "mongoose"],
    "redis": ["redis", "jedis", "lettuce"],
}

EXTERNAL_SERVICE_PATTERNS = {
    "payment-provider": ["payment.provider.url", "legacy-payment", "payment gateway"],
    "smtp": ["notification.smtp.host", "mail.internal", "smtp"],
    "stripe": ["stripe"],
    "sendgrid": ["sendgrid"],
    "twilio": ["twilio"],
    "aws-sdk": ["aws-sdk", "software.amazon.awssdk", "com.amazonaws"],
    "s3": ["s3client", "amazon s3", "aws.s3", "s3."],
    "sqs": ["sqsclient", "sqs."],
    "sns": ["snsclient", "sns."],
    "kafka": ["kafka"],
    "rabbitmq": ["rabbitmq", "amqp"],
}

CLOUD_PROVIDER_PATTERNS = {
    "AWS": {
        "terms": [
            "aws-java-sdk",
            "software.amazon.awssdk",
            "com.amazonaws",
            "amazons3",
            "aws_",
            "s3://",
            'provider "aws"',
            "aws::",
        ],
        "services": {
            "S3": ["aws-java-sdk-s3", "amazons3", "s3://", "aws.s3", "s3client"],
            "credential environment": ["aws_access_key_id", "aws_secret_access_key", "aws_session_token"],
            "CloudFormation": ["aws::"],
            "Terraform AWS provider": ['provider "aws"'],
        },
    },
    "Azure": {
        "terms": [
            "com.azure",
            "azure-",
            "azure_",
            "azure.",
            "blob.core.windows.net",
            'provider "azurerm"',
        ],
        "services": {
            "Blob Storage": ["blob.core.windows.net", "azure-storage-blob", "blobserviceclient"],
            "Azure SDK": ["com.azure", "azure-"],
            "Terraform AzureRM provider": ['provider "azurerm"'],
        },
    },
    "GCP": {
        "terms": [
            "com.google.cloud",
            "google-cloud",
            "google_application_credentials",
            "gs://",
            'provider "google"',
        ],
        "services": {
            "Cloud Storage": ["google-cloud-storage", "gs://", "storage.googleapis.com"],
            "Google Cloud SDK": ["com.google.cloud", "google-cloud"],
            "credential environment": ["google_application_credentials"],
            "Terraform Google provider": ['provider "google"'],
        },
    },
}

EVIDENCE_HINTS = {
    "controller": ["@RestController", "@RequestMapping", "@GetMapping", "@PostMapping", "@PutMapping", "@DeleteMapping"],
    "service": ["@Service", "private final", "public "],
    "repository": ["extends JpaRepository", "@Repository", "interface "],
    "entity": ["@Entity", "class "],
    "config": [
        "management.",
        "payment.provider.url",
        "notification.smtp.host",
        "spring.datasource.url",
        "server.port",
    ],
    "security_config": ["SecurityFilterChain", "csrf", "allowedOrigins", "@Configuration"],
    "dependency": ["spring-boot-starter-parent", "mysql-connector-java", "<artifactId>", "<version>"],
    "test": ["@Test", "class "],
    "ci_cd": ["FROM ", "name:", "on:", "steps:"],
    "readme": ["# ", "Legacy", "Migration"],
}


def _iter_files(repo_root: Path) -> Iterable[Path]:
    for path in repo_root.rglob("*"):
        if path.is_dir() or should_skip_path(path.relative_to(repo_root)):
            continue
        yield path


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")[: settings.max_file_chars]


def _evidence_line(text: str, file_type: str, needle: str | None = None) -> str:
    hints = [needle] if needle else EVIDENCE_HINTS.get(file_type, [])
    candidates = list(enumerate(text.splitlines(), start=1))
    for hint in [item for item in hints if item]:
        lowered_hint = hint.lower()
        for line_no, line in candidates:
            stripped = line.strip()
            if stripped and lowered_hint in stripped.lower():
                return f"line {line_no}: {redact_secrets(stripped)[:220]}"

    for line_no, line in candidates:
        stripped = line.strip()
        if stripped:
            return f"line {line_no}: {redact_secrets(stripped)[:220]}"
    return ""


def _entry(repo_root: Path, path: Path, text: str, file_type: str) -> dict[str, Any]:
    rel = safe_relative_path(path, repo_root)
    name = path.stem
    if path.suffix == ".java":
        name = class_name_from_java(path, text)
    entry = {
        "name": name,
        "file": rel,
        "file_type": file_type,
        "language": language_for_path(path),
        "evidence": _evidence_line(text, file_type),
    }
    if path.suffix == ".java":
        entry["source_dependencies"] = extract_java_dependencies(text)
    return entry


def _detect_framework(all_text: str, dependency_infos: list[dict[str, Any]]) -> str:
    lowered = all_text.lower()
    if "spring-boot-starter" in lowered or "@springbootapplication" in lowered:
        return "Spring Boot"
    for info in dependency_infos:
        if info.get("build_tool") == "npm":
            names = [dep.get("name", "").lower() for dep in info.get("dependencies", [])]
            if "express" in names or "express()" in lowered:
                return "Node/Express"
    if "express()" in lowered:
        return "Node/Express"
    return "unknown"


def _detect_languages(files: list[Path]) -> list[str]:
    languages: set[str] = set()
    for path in files:
        if path.suffix == ".java":
            languages.add("Java")
        elif path.suffix in {".js", ".jsx"}:
            languages.add("JavaScript")
        elif path.suffix in {".ts", ".tsx"}:
            languages.add("TypeScript")
        elif path.suffix == ".py":
            languages.add("Python")
    return sorted(languages)


def _detect_build_tools(files: list[Path]) -> list[str]:
    tools: set[str] = set()
    names = {path.name for path in files}
    if "pom.xml" in names:
        tools.add("Maven")
    if "build.gradle" in names:
        tools.add("Gradle")
    if "package.json" in names:
        tools.add("npm")
    return sorted(tools)


def _detect_terms(all_text: str, patterns: dict[str, list[str]]) -> list[str]:
    lowered = all_text.lower()
    detected = [name for name, terms in patterns.items() if any(term in lowered for term in terms)]
    return sorted(set(detected))


def _detect_cloud_evidence(file_texts: list[tuple[str, str]]) -> tuple[list[str], list[dict[str, str]]]:
    providers: set[str] = set()
    services: list[dict[str, str]] = []
    seen_services: set[tuple[str, str, str]] = set()

    for rel_path, text in file_texts:
        lowered = text.lower()
        for provider, provider_config in CLOUD_PROVIDER_PATTERNS.items():
            if any(term.lower() in lowered for term in provider_config["terms"]):
                providers.add(provider)

            for service_name, terms in provider_config["services"].items():
                matched_term = next((term for term in terms if term.lower() in lowered), None)
                if not matched_term:
                    continue
                providers.add(provider)
                key = (provider, service_name, rel_path)
                if key in seen_services:
                    continue
                seen_services.add(key)
                services.append(
                    {
                        "provider": provider,
                        "service": service_name,
                        "file": rel_path,
                        "evidence": _evidence_line(text, "config", matched_term),
                    }
                )

    return sorted(providers), services


def _component_kind(file_path: str) -> str:
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


def _build_component_couplings(components: list[dict[str, Any]]) -> list[dict[str, str]]:
    by_name = {item.get("name"): item for item in components if item.get("name")}
    couplings: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for source in components:
        source_name = source.get("name")
        source_file = source.get("file", "")
        internal_dependencies: list[dict[str, str]] = []
        for dependency in source.get("source_dependencies", []):
            target_name = dependency.get("target")
            target = by_name.get(target_name)
            if not target or target_name == source_name:
                continue
            target_file = target.get("file", "")
            key = (source_file, target_file)
            if key in seen:
                continue
            seen.add(key)
            relationship = f"{_component_kind(source_file)} -> {_component_kind(target_file)}"
            coupling = {
                "source": source_name,
                "source_file": source_file,
                "target": target_name,
                "target_file": target_file,
                "relationship": relationship,
                "evidence": dependency.get("evidence", ""),
                "line": dependency.get("line", ""),
            }
            internal_dependencies.append(coupling)
            couplings.append(coupling)
        source["internal_dependencies"] = internal_dependencies

    return couplings


def scan_repository(repo_root: Path, analysis_id: str) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    files = list(_iter_files(repo_root))
    allowed_files = [path for path in files if is_allowed_file(path.relative_to(repo_root))]

    controllers: list[dict[str, Any]] = []
    services: list[dict[str, Any]] = []
    repositories: list[dict[str, Any]] = []
    entities: list[dict[str, Any]] = []
    config_files: list[dict[str, Any]] = []
    dependency_files: list[dict[str, Any]] = []
    test_files: list[dict[str, Any]] = []
    ci_cd_files: list[dict[str, Any]] = []
    readme_files: list[dict[str, Any]] = []
    api_inventory: list[dict[str, str]] = []
    dependency_infos: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    all_text_parts: list[str] = []
    file_texts: list[tuple[str, str]] = []
    indexed_file_paths: list[str] = []

    for path in allowed_files:
        rel = safe_relative_path(path, repo_root)
        text = _read_text(path)
        all_text_parts.append(text)
        file_texts.append((rel, text))
        file_type = classify_file(path.relative_to(repo_root), text)
        indexed_file_paths.append(rel)
        prompt_patterns = detect_prompt_injection(text)
        for pattern in prompt_patterns:
            warnings.append(
                {
                    "type": "prompt_injection_pattern",
                    "file": rel,
                    "pattern": pattern,
                    "message": "Repository text contains a prompt-injection-like phrase.",
                }
            )

        entry = _entry(repo_root, path, text, file_type)
        if file_type == "controller":
            endpoints = extract_spring_endpoints(Path(rel), text)
            endpoints.extend(extract_express_endpoints(Path(rel), text))
            entry["endpoints"] = endpoints
            api_inventory.extend(endpoints)
            controllers.append(entry)
        elif file_type == "service":
            services.append(entry)
        elif file_type == "repository":
            repositories.append(entry)
        elif file_type == "entity":
            entities.append(entry)
        elif file_type in {"config", "security_config"}:
            config_files.append(entry)
        elif file_type == "dependency":
            dependency_files.append(entry)
            parsed = parse_dependency_file(path)
            parsed["file"] = rel
            dependency_infos.append(parsed)
        elif file_type == "test":
            test_files.append(entry)
        elif file_type == "ci_cd":
            ci_cd_files.append(entry)
        elif file_type == "readme":
            readme_files.append(entry)

    all_text = "\n".join(all_text_parts)
    framework = _detect_framework(all_text, dependency_infos)
    components = controllers + services + repositories + entities
    component_couplings = _build_component_couplings(components)
    detected_cloud_providers, detected_cloud_services = _detect_cloud_evidence(file_texts)

    return {
        "analysis_id": analysis_id,
        "repo_root": repo_root.as_posix(),
        "framework": framework,
        "languages": _detect_languages(allowed_files),
        "build_tools": _detect_build_tools(allowed_files),
        "file_counts": {"total_files": len(files), "indexed_files": len(allowed_files)},
        "controllers": controllers,
        "services": services,
        "repositories": repositories,
        "entities": entities,
        "config_files": config_files,
        "dependency_files": dependency_files,
        "dependency_details": dependency_infos,
        "test_files": test_files,
        "ci_cd_files": ci_cd_files,
        "readme_files": readme_files,
        "api_inventory": api_inventory,
        "detected_databases": _detect_terms(all_text, DATABASE_PATTERNS),
        "detected_external_services": _detect_terms(all_text, EXTERNAL_SERVICE_PATTERNS),
        "detected_cloud_providers": detected_cloud_providers,
        "detected_cloud_services": detected_cloud_services,
        "component_couplings": component_couplings,
        "indexed_file_paths": indexed_file_paths,
        "warnings": warnings,
    }


def matching_test_exists(target_name: str, test_files: list[dict[str, Any]]) -> bool:
    normalized = re.sub(r"(controller|service|repository)$", "", target_name, flags=re.I).lower()
    for test_file in test_files:
        file_name = Path(test_file.get("file", "")).stem.lower()
        if normalized and normalized in file_name:
            return True
    return False
