from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

import requests

from app.config import settings
from app.ingestion.zip_loader import safe_extract_zip, validate_zip_file


GITHUB_HOSTS = {"github.com", "www.github.com"}
GITHUB_API_BASE_URL = "https://api.github.com"
CHUNK_SIZE_BYTES = 1024 * 1024


@dataclass(frozen=True)
class GitHubRepoReference:
    owner: str
    repo: str
    ref: str | None = None


def _github_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ModernizeAI",
    }
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    return headers


def parse_github_repo_url(repo_url: str) -> GitHubRepoReference:
    parsed = urlparse(repo_url.strip())
    if parsed.scheme != "https" or parsed.netloc.lower() not in GITHUB_HOSTS:
        raise ValueError("Only https://github.com/{owner}/{repo} URLs are supported.")

    parts = [unquote(part) for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        raise ValueError("GitHub URL must include an owner and repository name.")

    owner = parts[0]
    repo = parts[1].removesuffix(".git")
    if not owner or not repo:
        raise ValueError("GitHub URL must include an owner and repository name.")

    ref = None
    if len(parts) > 3 and parts[2] in {"tree", "commit"}:
        ref = "/".join(parts[3:])
    elif len(parts) > 2 and parts[2] not in {"", "tree", "commit"}:
        raise ValueError("Use a GitHub repository URL, optionally with /tree/{branch}.")

    return GitHubRepoReference(owner=owner, repo=repo, ref=ref)


def parse_public_github_url(repo_url: str) -> tuple[str, str]:
    reference = parse_github_repo_url(repo_url)
    return reference.owner, reference.repo


def _github_api_get_json(url: str) -> dict[str, object]:
    response = requests.get(url, headers=_github_headers(), timeout=30)
    if response.status_code == 404:
        raise ValueError(
            "GitHub repository was not found or is private. "
            "For private repositories, set GITHUB_TOKEN or GH_TOKEN with repository read access."
        )
    if response.status_code in {401, 403}:
        raise ValueError(
            f"GitHub API rejected the request with HTTP {response.status_code}. "
            "Check GITHUB_TOKEN/GH_TOKEN permissions or rate limits."
        )
    if response.status_code >= 400:
        raise ValueError(f"GitHub API request failed with HTTP {response.status_code}.")
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("GitHub API returned an unexpected response.")
    return payload


def _write_streamed_zip(response: requests.Response, zip_path: Path, max_bytes: int) -> Path:
    content_length = response.headers.get("content-length")
    if content_length and int(content_length) > max_bytes:
        raise ValueError(f"GitHub repository archive exceeds {settings.max_upload_mb} MB limit.")

    zip_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = zip_path.with_suffix(f"{zip_path.suffix}.part")
    if temp_path.exists():
        temp_path.unlink()

    size = 0
    try:
        with temp_path.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE_BYTES):
                if not chunk:
                    continue
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError(f"GitHub repository archive exceeds {settings.max_upload_mb} MB limit.")
                handle.write(chunk)
        temp_path.replace(zip_path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise

    validate_zip_file(zip_path, max_bytes=max_bytes)
    return zip_path


def download_public_github_repo(repo_url: str, zip_path: Path, max_bytes: int | None = None) -> Path:
    reference = parse_github_repo_url(repo_url)
    repo_api_url = f"{GITHUB_API_BASE_URL}/repos/{reference.owner}/{reference.repo}"
    repo_payload = _github_api_get_json(repo_api_url)

    default_branch = repo_payload.get("default_branch")
    ref = reference.ref or (default_branch if isinstance(default_branch, str) else None)
    if not ref:
        raise ValueError("GitHub repository did not expose a default branch.")

    limit = max_bytes or settings.max_upload_bytes
    encoded_ref = quote(ref, safe="")
    zipball_url = f"{repo_api_url}/zipball/{encoded_ref}"
    response = requests.get(zipball_url, headers=_github_headers(), timeout=60, stream=True)
    try:
        if response.status_code == 404:
            raise ValueError(f"GitHub archive was not found for ref '{ref}'.")
        if response.status_code in {401, 403}:
            raise ValueError(
                f"GitHub archive download was rejected with HTTP {response.status_code}. "
                "Check GITHUB_TOKEN/GH_TOKEN permissions or rate limits."
            )
        if response.status_code >= 400:
            raise ValueError(f"GitHub archive download failed with HTTP {response.status_code}.")
        return _write_streamed_zip(response, zip_path, limit)
    finally:
        response.close()


def load_public_github_repo(
    repo_url: str,
    zip_path: Path,
    target_dir: Path,
    max_bytes: int | None = None,
) -> Path:
    downloaded = download_public_github_repo(repo_url, zip_path, max_bytes=max_bytes)
    return safe_extract_zip(downloaded, target_dir, max_bytes=max_bytes)
