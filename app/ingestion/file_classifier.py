from __future__ import annotations

from pathlib import Path


SKIP_DIRS = {
    ".git",
    "node_modules",
    "target",
    "build",
    "dist",
    ".next",
    ".venv",
    "venv",
    "__pycache__",
    ".idea",
    ".vscode",
    "coverage",
}

ALLOWED_EXTENSIONS = {
    ".java",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".py",
    ".xml",
    ".gradle",
    ".properties",
    ".yml",
    ".yaml",
    ".json",
    ".md",
    ".txt",
    ".env",
    ".dockerfile",
}

ALLOWED_FILENAMES = {
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "pom.xml",
    "build.gradle",
    "package.json",
    "Jenkinsfile",
    ".gitignore",
    ".env.example",
}


def should_skip_path(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def is_allowed_file(path: Path) -> bool:
    if should_skip_path(path):
        return False
    if path.name in ALLOWED_FILENAMES:
        return True
    return path.suffix.lower() in ALLOWED_EXTENSIONS


def language_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".java":
        return "java"
    if suffix in {".js", ".jsx"}:
        return "javascript"
    if suffix in {".ts", ".tsx"}:
        return "typescript"
    if suffix == ".py":
        return "python"
    if suffix in {".xml", ".gradle", ".properties", ".yml", ".yaml", ".json"}:
        return "config"
    if path.name == "Dockerfile" or suffix == ".dockerfile":
        return "docker"
    return "text"


def classify_file(path: Path, content: str = "") -> str:
    lowered_path = path.as_posix().lower()
    lowered_name = path.name.lower()
    lowered_content = content.lower()

    if (
        "test" in lowered_path
        or "__tests__" in lowered_path
        or lowered_name.endswith((".spec.js", ".spec.ts", ".test.js", ".test.ts"))
        or "junit" in lowered_content
        or "jest" in lowered_content
    ):
        return "test"
    if lowered_path.startswith(".github/workflows") or path.name in {
        "Jenkinsfile",
        "Dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
    }:
        return "ci_cd"
    if path.name in {"pom.xml", "build.gradle", "package.json"}:
        return "dependency"
    if lowered_name == "readme.md":
        return "readme"
    if (
        "@restcontroller" in lowered_content
        or "@controller" in lowered_content
        or "@requestmapping" in lowered_content
        or "app.get(" in lowered_content
        or "app.post(" in lowered_content
        or "router.get(" in lowered_content
        or "router.post(" in lowered_content
        or "/controller/" in lowered_path
        or "\\controller\\" in lowered_path
    ):
        return "controller"
    if (
        "@repository" in lowered_content
        or "extends jparepository" in lowered_content
        or "/repository/" in lowered_path
        or "/dao/" in lowered_path
    ):
        return "repository"
    if "@entity" in lowered_content or "/entity/" in lowered_path or "/model/" in lowered_path:
        return "entity"
    if "@service" in lowered_content or "/service/" in lowered_path:
        return "service"
    if (
        "security" in lowered_path
        or "springsecurity" in lowered_content
        or "httpsecurity" in lowered_content
        or "csrf()" in lowered_content
    ):
        return "security_config"
    if (
        "application.properties" in lowered_name
        or "application.yml" in lowered_name
        or "application.yaml" in lowered_name
        or "/config/" in lowered_path
        or "@configuration" in lowered_content
    ):
        return "config"
    return "source" if path.suffix.lower() in {".java", ".js", ".ts", ".tsx", ".jsx", ".py"} else "config"
