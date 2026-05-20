from __future__ import annotations

import re
from pathlib import Path


COMMON_JAVA_TYPES = {
    "Boolean",
    "Double",
    "Exception",
    "Integer",
    "List",
    "Long",
    "Map",
    "Optional",
    "ResponseEntity",
    "RestTemplate",
    "Set",
    "String",
    "Void",
}


def class_name_from_java(path: Path, text: str) -> str:
    match = re.search(r"\b(class|interface|enum)\s+([A-Za-z0-9_]+)", text)
    return match.group(2) if match else path.stem


def _annotation_path(annotation: str) -> str:
    match = re.search(r"\(\s*(?:value\s*=\s*)?\"([^\"]*)\"", annotation)
    return match.group(1) if match else ""


def extract_spring_endpoints(path: Path, text: str) -> list[dict[str, str]]:
    endpoints: list[dict[str, str]] = []
    class_request = re.search(r"@RequestMapping\s*(?:\([^)]*\))?", text)
    base_path = _annotation_path(class_request.group(0)) if class_request else ""

    method_map = {
        "GetMapping": "GET",
        "PostMapping": "POST",
        "PutMapping": "PUT",
        "PatchMapping": "PATCH",
        "DeleteMapping": "DELETE",
    }
    pattern = re.compile(
        r"@(GetMapping|PostMapping|PutMapping|PatchMapping|DeleteMapping|RequestMapping)\s*(?:\([^)]*\))?"
    )
    for match in pattern.finditer(text):
        annotation = match.group(0)
        annotation_name = match.group(1)
        if class_request and annotation_name == "RequestMapping" and match.start() == class_request.start():
            continue
        method = method_map.get(annotation_name, "ANY")
        if annotation_name == "RequestMapping":
            method_match = re.search(r"RequestMethod\.([A-Z]+)", annotation)
            if method_match:
                method = method_match.group(1)
        route = _annotation_path(annotation)
        full_path = _join_paths(base_path, route)
        line_no = text[: match.start()].count("\n") + 1
        endpoints.append(
            {
                "method": method,
                "path": full_path or "/",
                "file": path.as_posix(),
                "evidence": annotation.strip(),
                "line": str(line_no),
            }
        )
    return endpoints


def _join_paths(base_path: str, route: str) -> str:
    base = "/" + base_path.strip("/")
    child = route.strip("/")
    if not child:
        return base if base != "/" else "/"
    return f"{base}/{child}".replace("//", "/")


def extract_java_dependencies(text: str) -> list[dict[str, str]]:
    dependencies: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue

        import_match = re.match(r"import\s+com\.[A-Za-z0-9_.]+\.(?P<class>[A-Z][A-Za-z0-9_]+)\s*;", stripped)
        if import_match:
            target = import_match.group("class")
            key = ("import", target, stripped)
            if key not in seen:
                seen.add(key)
                dependencies.append(
                    {
                        "target": target,
                        "kind": "import",
                        "evidence": stripped,
                        "line": str(line_no),
                    }
                )

        if stripped.startswith(("import ", "package ", "@")):
            continue

        for match in re.finditer(r"\b([A-Z][A-Za-z0-9_]+)\s+[a-z][A-Za-z0-9_]*\b", stripped):
            target = match.group(1)
            if target in COMMON_JAVA_TYPES:
                continue
            key = ("type_reference", target, stripped)
            if key in seen:
                continue
            seen.add(key)
            dependencies.append(
                {
                    "target": target,
                    "kind": "type_reference",
                    "evidence": stripped,
                    "line": str(line_no),
                }
            )

    return dependencies
