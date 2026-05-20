from __future__ import annotations

import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath

from app.config import settings


BLOCKED_EXTENSIONS = {".exe", ".dll", ".so", ".dmg", ".bin", ".sh", ".bat", ".cmd"}


def validate_zip_file(zip_path: Path, max_bytes: int | None = None) -> None:
    if zip_path.suffix.lower() != ".zip":
        raise ValueError("Only .zip uploads are supported.")
    if not zip_path.exists():
        raise ValueError(f"Zip file does not exist: {zip_path}")
    limit = max_bytes or settings.max_upload_bytes
    if zip_path.stat().st_size > limit:
        raise ValueError(f"Upload exceeds {settings.max_upload_mb} MB limit.")
    if not zipfile.is_zipfile(zip_path):
        raise ValueError("Uploaded file is not a valid zip archive.")


def _is_zip_symlink(member: zipfile.ZipInfo) -> bool:
    mode = member.external_attr >> 16
    return stat.S_ISLNK(mode)


def _validate_member_path(member_name: str, target_dir: Path) -> Path:
    if not member_name or member_name.startswith(("/", "\\")):
        raise ValueError(f"Unsafe zip path detected: {member_name}")
    pure = PurePosixPath(member_name)
    if any(part in {"..", ""} for part in pure.parts):
        raise ValueError(f"Unsafe zip path detected: {member_name}")
    resolved = (target_dir / Path(*pure.parts)).resolve()
    resolved.relative_to(target_dir.resolve())
    return resolved


def safe_extract_zip(zip_path: Path, target_dir: Path, max_bytes: int | None = None) -> Path:
    validate_zip_file(zip_path, max_bytes=max_bytes)
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        for member in zip_ref.infolist():
            resolved = _validate_member_path(member.filename, target_dir)
            if _is_zip_symlink(member):
                continue
            if Path(member.filename).suffix.lower() in BLOCKED_EXTENSIONS:
                continue
            if member.is_dir():
                resolved.mkdir(parents=True, exist_ok=True)
                continue
            resolved.parent.mkdir(parents=True, exist_ok=True)
            with zip_ref.open(member) as source, resolved.open("wb") as destination:
                shutil.copyfileobj(source, destination)
    return target_dir

