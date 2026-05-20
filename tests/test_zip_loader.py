from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from app.ingestion.zip_loader import safe_extract_zip, validate_zip_file


def _make_zip(path: Path, files: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)


def test_valid_zip_extracts(tmp_path: Path) -> None:
    zip_path = tmp_path / "repo.zip"
    target = tmp_path / "repo"
    _make_zip(zip_path, {"demo/README.md": "hello"})

    safe_extract_zip(zip_path, target)

    assert (target / "demo" / "README.md").read_text() == "hello"


def test_zip_slip_path_traversal_is_blocked(tmp_path: Path) -> None:
    zip_path = tmp_path / "repo.zip"
    target = tmp_path / "repo"
    _make_zip(zip_path, {"../escape.txt": "bad"})

    with pytest.raises(ValueError):
        safe_extract_zip(zip_path, target)


def test_blocked_extension_is_skipped(tmp_path: Path) -> None:
    zip_path = tmp_path / "repo.zip"
    target = tmp_path / "repo"
    _make_zip(zip_path, {"demo/run.sh": "echo no", "demo/app.java": "class App {}"})

    safe_extract_zip(zip_path, target)

    assert not (target / "demo" / "run.sh").exists()
    assert (target / "demo" / "app.java").exists()


def test_oversized_upload_is_rejected(tmp_path: Path) -> None:
    zip_path = tmp_path / "repo.zip"
    _make_zip(zip_path, {"demo/README.md": "hello"})

    with pytest.raises(ValueError):
        validate_zip_file(zip_path, max_bytes=1)

