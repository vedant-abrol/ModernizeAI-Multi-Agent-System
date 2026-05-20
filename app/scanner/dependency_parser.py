from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


def _strip_namespace(root: ET.Element) -> None:
    for element in root.iter():
        if "}" in element.tag:
            element.tag = element.tag.split("}", 1)[1]


def parse_pom_xml(path: Path) -> dict[str, Any]:
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception as exc:
        return {"file": path.as_posix(), "build_tool": "Maven", "dependencies": [], "errors": [str(exc)]}
    _strip_namespace(root)

    properties = {
        child.tag: (child.text or "").strip()
        for child in root.find("properties") or []
        if child.text
    }
    dependencies: list[dict[str, str]] = []
    for dep in root.findall(".//dependency"):
        group_id = (dep.findtext("groupId") or "").strip()
        artifact_id = (dep.findtext("artifactId") or "").strip()
        version = (dep.findtext("version") or "").strip()
        if version.startswith("${") and version.endswith("}"):
            version = properties.get(version[2:-1], version)
        if group_id or artifact_id:
            dependencies.append(
                {
                    "groupId": group_id,
                    "artifactId": artifact_id,
                    "version": version,
                    "scope": (dep.findtext("scope") or "").strip(),
                }
            )

    spring_boot_version = ""
    parent = root.find("parent")
    if parent is not None and (parent.findtext("artifactId") or "") == "spring-boot-starter-parent":
        spring_boot_version = (parent.findtext("version") or "").strip()
    if not spring_boot_version:
        spring_boot_version = properties.get("spring-boot.version", "")

    return {
        "file": path.as_posix(),
        "build_tool": "Maven",
        "spring_boot_version": spring_boot_version,
        "dependencies": dependencies,
        "errors": [],
    }


def parse_package_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception as exc:
        return {"file": path.as_posix(), "build_tool": "npm", "dependencies": [], "errors": [str(exc)]}
    dependencies: list[dict[str, str]] = []
    for section in ("dependencies", "devDependencies"):
        for name, version in payload.get(section, {}).items():
            dependencies.append({"name": name, "version": str(version), "scope": section})
    return {
        "file": path.as_posix(),
        "build_tool": "npm",
        "name": payload.get("name", ""),
        "version": payload.get("version", ""),
        "dependencies": dependencies,
        "errors": [],
    }


def parse_gradle(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    dependencies: list[dict[str, str]] = []
    for match in re.finditer(
        r"(implementation|api|compileOnly|runtimeOnly|testImplementation)\s+['\"]([^:'\"]+):([^:'\"]+):([^'\"]+)['\"]",
        text,
    ):
        dependencies.append(
            {
                "configuration": match.group(1),
                "groupId": match.group(2),
                "artifactId": match.group(3),
                "version": match.group(4),
            }
        )
    spring_match = re.search(r"id\s+['\"]org\.springframework\.boot['\"]\s+version\s+['\"]([^'\"]+)", text)
    return {
        "file": path.as_posix(),
        "build_tool": "Gradle",
        "spring_boot_version": spring_match.group(1) if spring_match else "",
        "dependencies": dependencies,
        "errors": [],
    }


def parse_dependency_file(path: Path) -> dict[str, Any]:
    if path.name == "pom.xml":
        return parse_pom_xml(path)
    if path.name == "package.json":
        return parse_package_json(path)
    if path.name == "build.gradle":
        return parse_gradle(path)
    return {"file": path.as_posix(), "build_tool": "unknown", "dependencies": [], "errors": []}

