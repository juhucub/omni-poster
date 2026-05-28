from __future__ import annotations

import logging
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.infra.ffmpeg.probe import get_media_duration_seconds
from app.infra.storage import (
    LocalStorageAdapter,
    StoragePathTraversalError,
    bundled_media_root_path,
    generated_job_artifact_path,
    generated_job_segment_path,
    media_root_path,
    preset_media_path,
    project_media_path,
    relative_to_root,
    resolve_safe_relative_path,
)

logger = logging.getLogger(__name__)

ALLOWED_BACKGROUND_VIDEO_TYPES = {"video/mp4", "video/webm", "video/mpeg"}
ALLOWED_BACKGROUND_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
ALLOWED_BACKGROUND_TYPES = ALLOWED_BACKGROUND_VIDEO_TYPES | ALLOWED_BACKGROUND_IMAGE_TYPES
UPLOAD_CHUNK_SIZE = 1024 * 1024

_storage = LocalStorageAdapter()


def media_root() -> Path:
    return _storage.ensure_directory(media_root_path())


def bundled_media_root() -> Path:
    return _storage.ensure_directory(bundled_media_root_path())


def preset_media_dir() -> Path:
    return _storage.ensure_directory(preset_media_path())


def project_media_dir(project_id: int) -> Path:
    return _storage.ensure_directory(project_media_path(project_id))


def project_storage_usage_bytes(project_id: int) -> int:
    return _storage.directory_usage_bytes(project_media_dir(project_id))


def generated_job_artifact_dir(job_id: int) -> Path:
    return _storage.ensure_directory(generated_job_artifact_path(job_id))


def generated_job_segment_dir(job_id: int) -> Path:
    return _storage.ensure_directory(generated_job_segment_path(job_id))


def generated_job_artifact_url(job_id: int, artifact_path: Path) -> str:
    root = generated_job_artifact_dir(job_id)
    # Keep debug artifact links job-scoped so metadata never exposes arbitrary filesystem paths.
    relative = relative_to_root(root, artifact_path)
    return f"/generation-jobs/{job_id}/artifacts/{quote(relative.as_posix())}"


def resolve_generated_job_artifact(job_id: int, artifact_path: str) -> Path:
    root = generated_job_artifact_dir(job_id)
    try:
        # Reject traversal before resolving against generated storage; callers only get job-local artifacts.
        resolved = resolve_safe_relative_path(root, artifact_path)
    except StoragePathTraversalError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found") from exc
    if not _storage.is_file(resolved):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    return resolved


def list_background_presets() -> list[dict]:
    presets: list[dict] = []
    preset_dir = preset_media_dir()
    for path in sorted(preset_dir.glob("*")):
        if path.suffix.lower() not in {".mp4", ".webm", ".mpeg", ".png", ".jpg", ".jpeg", ".webp"}:
            continue
        mime_type = guess_mime_type(str(path))
        presets.append(
            {
                "key": path.stem,
                "name": path.stem.replace("_", " ").title(),
                "description": "Curated background preset",
                "filename": path.name,
                "path": path,
                "mime_type": mime_type,
            }
        )
    logger.info("Scanned bundled background presets in %s: %s found", preset_dir, len(presets))
    return presets


def resolve_background_preset(preset_key: str) -> dict:
    for preset in list_background_presets():
        if preset["key"] == preset_key:
            return preset
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Background preset not found")


def _declared_upload_mime_type(file: UploadFile) -> str:
    return (file.content_type or "").split(";", 1)[0].strip().lower()


def _detect_background_mime_type(header: bytes) -> str | None:
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "image/webp"
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return "video/mp4"
    if header.startswith(b"\x1aE\xdf\xa3"):
        return "video/webm"
    if header.startswith(b"\x00\x00\x01\xba") or header.startswith(b"\x00\x00\x01\xb3"):
        return "video/mpeg"
    return None


def _verify_background_duration(path: Path, mime_type: str) -> None:
    max_duration = float(settings.BACKGROUND_VIDEO_MAX_DURATION_SECONDS or 0)
    if max_duration <= 0 or mime_type not in ALLOWED_BACKGROUND_VIDEO_TYPES:
        return
    try:
        duration = get_media_duration_seconds(path, timeout=10)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded background video duration could not be verified",
        ) from exc
    if duration > max_duration:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Background video exceeds {max_duration:g}s duration limit",
        )


async def save_background_asset(project_id: int, file: UploadFile) -> tuple[Path, int, str]:
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Filename is required")
    declared_mime_type = _declared_upload_mime_type(file)
    if declared_mime_type not in ALLOWED_BACKGROUND_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported background media type",
        )

    destination = project_media_dir(project_id) / f"{uuid.uuid4().hex}_{Path(file.filename).name}"
    size = 0
    detected_mime_type: str | None = None
    existing_usage = project_storage_usage_bytes(project_id)
    quota_bytes = int(settings.PROJECT_STORAGE_QUOTA_BYTES or 0)
    max_upload_bytes = int(settings.BACKGROUND_UPLOAD_MAX_SIZE_BYTES or 0)

    try:
        await file.seek(0)
        with open(destination, "wb") as out_file:
            while chunk := await file.read(UPLOAD_CHUNK_SIZE):
                if detected_mime_type is None:
                    detected_mime_type = _detect_background_mime_type(chunk[:4096])
                    if detected_mime_type not in ALLOWED_BACKGROUND_TYPES or detected_mime_type != declared_mime_type:
                        raise HTTPException(
                            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            detail="Uploaded background media does not match its declared type",
                        )
                size += len(chunk)
                if max_upload_bytes > 0 and size > max_upload_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="Background media exceeds upload size limit",
                    )
                if quota_bytes > 0 and existing_usage + size > quota_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="Project storage quota exceeded",
                    )
                out_file.write(chunk)
        if not detected_mime_type:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Uploaded background media type could not be verified",
            )
        _verify_background_duration(destination, detected_mime_type)
    except HTTPException:
        if destination.exists():
            destination.unlink()
        raise
    finally:
        await file.close()

    return destination, size, detected_mime_type or guess_mime_type(str(destination))


def copy_preset_to_project(project_id: int, preset_key: str) -> tuple[Path, int, str]:
    preset = resolve_background_preset(preset_key)
    source_path: Path = preset["path"]
    # Persist the selected preset into project storage so later renders do not depend on mutable bundled files.
    destination = project_media_dir(project_id) / f"{uuid.uuid4().hex}_{source_path.name}"
    _storage.copy_file(source_path, destination)
    return destination, _storage.file_size(destination), guess_mime_type(str(destination))


def store_generated_file(project_id: int, source_path: str, filename: str | None = None) -> Path:
    output_name = filename or f"{uuid.uuid4().hex}.mp4"
    destination = project_media_dir(project_id) / output_name
    source = Path(source_path)
    return _storage.copy_file(source, destination)


def delete_storage_key(storage_key: str) -> None:
    _storage.delete_file(storage_key)


def guess_mime_type(storage_key: str) -> str:
    return _storage.guess_mime_type(storage_key)
