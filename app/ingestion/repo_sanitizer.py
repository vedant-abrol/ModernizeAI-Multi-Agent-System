from __future__ import annotations

from pathlib import Path


def find_repo_root(extracted_dir: Path) -> Path:
    children = [child for child in extracted_dir.iterdir() if not child.name.startswith("__MACOSX")]
    directories = [child for child in children if child.is_dir()]
    files = [child for child in children if child.is_file()]
    if len(directories) == 1 and not files:
        return directories[0]
    return extracted_dir


def safe_relative_path(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()

