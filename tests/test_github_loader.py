from __future__ import annotations

from io import BytesIO
from pathlib import Path
import zipfile

import pytest

from app.ingestion.github_loader import (
    download_public_github_repo,
    load_public_github_repo,
    parse_github_repo_url,
    parse_public_github_url,
)


class FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        json_payload: dict[str, object] | None = None,
        content: bytes = b"",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._json_payload = json_payload or {}
        self._content = content
        self.headers = headers or {}
        self.closed = False

    def json(self) -> dict[str, object]:
        return self._json_payload

    def iter_content(self, chunk_size: int):
        for index in range(0, len(self._content), chunk_size):
            yield self._content[index : index + chunk_size]

    def close(self) -> None:
        self.closed = True


def _zip_bytes(files: dict[str, str]) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_parse_github_repo_url_accepts_common_repo_urls() -> None:
    reference = parse_github_repo_url("https://github.com/acme/widgets.git")

    assert reference.owner == "acme"
    assert reference.repo == "widgets"
    assert reference.ref is None
    assert parse_public_github_url("https://github.com/acme/widgets/") == ("acme", "widgets")


def test_parse_github_repo_url_captures_tree_ref() -> None:
    reference = parse_github_repo_url("https://github.com/acme/widgets/tree/feature/next")

    assert reference.owner == "acme"
    assert reference.repo == "widgets"
    assert reference.ref == "feature/next"


def test_parse_github_repo_url_rejects_non_github_urls() -> None:
    with pytest.raises(ValueError, match="Only https://github.com"):
        parse_github_repo_url("https://example.com/acme/widgets")


def test_download_uses_github_api_default_branch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    archive = _zip_bytes({"widgets-main/README.md": "hello"})
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_get(url: str, **kwargs):
        calls.append((url, kwargs))
        if url == "https://api.github.com/repos/acme/widgets":
            return FakeResponse(json_payload={"default_branch": "develop"})
        if url == "https://api.github.com/repos/acme/widgets/zipball/develop":
            return FakeResponse(content=archive, headers={"content-length": str(len(archive))})
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("app.ingestion.github_loader.requests.get", fake_get)

    zip_path = tmp_path / "repo.zip"
    result = download_public_github_repo("https://github.com/acme/widgets", zip_path)

    assert result == zip_path
    assert zip_path.exists()
    assert zipfile.is_zipfile(zip_path)
    assert calls[1][1]["stream"] is True


def test_download_uses_tree_ref_when_url_includes_branch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    archive = _zip_bytes({"widgets-branch/README.md": "hello"})
    requested_urls: list[str] = []

    def fake_get(url: str, **kwargs):
        requested_urls.append(url)
        if url == "https://api.github.com/repos/acme/widgets":
            return FakeResponse(json_payload={"default_branch": "main"})
        if url == "https://api.github.com/repos/acme/widgets/zipball/feature%2Fnext":
            return FakeResponse(content=archive, headers={"content-length": str(len(archive))})
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("app.ingestion.github_loader.requests.get", fake_get)

    download_public_github_repo("https://github.com/acme/widgets/tree/feature/next", tmp_path / "repo.zip")

    assert requested_urls[-1].endswith("/zipball/feature%2Fnext")


def test_load_public_github_repo_extracts_downloaded_archive(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    archive = _zip_bytes({"widgets-main/src/App.java": "class App {}"})

    def fake_get(url: str, **kwargs):
        if url == "https://api.github.com/repos/acme/widgets":
            return FakeResponse(json_payload={"default_branch": "main"})
        if url == "https://api.github.com/repos/acme/widgets/zipball/main":
            return FakeResponse(content=archive, headers={"content-length": str(len(archive))})
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("app.ingestion.github_loader.requests.get", fake_get)

    target = tmp_path / "repo"
    load_public_github_repo("https://github.com/acme/widgets", tmp_path / "repo.zip", target)

    assert (target / "widgets-main" / "src" / "App.java").read_text() == "class App {}"


def test_download_reports_private_or_missing_repo(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_get(url: str, **kwargs):
        return FakeResponse(status_code=404)

    monkeypatch.setattr("app.ingestion.github_loader.requests.get", fake_get)

    with pytest.raises(ValueError, match="not found or is private"):
        download_public_github_repo("https://github.com/acme/missing", tmp_path / "repo.zip")


def test_download_enforces_size_limit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    archive = _zip_bytes({"widgets-main/README.md": "hello"})

    def fake_get(url: str, **kwargs):
        if url == "https://api.github.com/repos/acme/widgets":
            return FakeResponse(json_payload={"default_branch": "main"})
        if url == "https://api.github.com/repos/acme/widgets/zipball/main":
            return FakeResponse(content=archive, headers={"content-length": str(len(archive))})
        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr("app.ingestion.github_loader.requests.get", fake_get)

    with pytest.raises(ValueError, match="exceeds"):
        download_public_github_repo("https://github.com/acme/widgets", tmp_path / "repo.zip", max_bytes=1)
