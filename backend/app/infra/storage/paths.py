from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.infra.storage.errors import StoragePathTraversalError


def media_root_path() -> Path:
    return Path(settings.MEDIA_DIR)


def bundled_media_root_path() -> Path:
    return Path(settings.BUNDLED_MEDIA_DIR)


def preset_media_path() -> Path:
    return bundled_media_root_path() / "presets"


def project_media_path(project_id: int) -> Path:
    return media_root_path() / f"project_{project_id}"


def generated_job_artifact_path(job_id: int) -> Path:
    return media_root_path() / "generated" / str(job_id)


def generated_job_segment_path(job_id: int) -> Path:
    return generated_job_artifact_path(job_id) / "segments"


def relative_to_root(root: str | Path, path: str | Path) -> Path:
    root_path = Path(root).resolve()
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(root_path)
    except ValueError as exc:
        raise StoragePathTraversalError("Storage path escapes its root.") from exc


def resolve_safe_relative_path(root: str | Path, relative_path: str | Path) -> Path:
    relative = Path(relative_path)
    if relative.is_absolute() or not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise StoragePathTraversalError("Storage path must be a safe relative path.")
    root_path = Path(root).resolve()
    resolved = (root_path / relative).resolve()
    relative_to_root(root_path, resolved)
    return resolved
