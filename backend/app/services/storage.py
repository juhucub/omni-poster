from __future__ import annotations

import mimetypes
import shutil
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings

ALLOWED_BACKGROUND_VIDEO_TYPES = {"video/mp4", "video/webm", "video/mpeg"}
MAX_BACKGROUND_VIDEO_SIZE = 100 * 1024 * 1024


def media_root() -> Path:
    root = Path(settings.MEDIA_DIR)
    root.mkdir(parents=True, exist_ok=True)
    return root


def preset_media_dir() -> Path:
    path = media_root() / "presets"
    path.mkdir(parents=True, exist_ok=True)
    return path


def project_media_dir(project_id: int) -> Path:
    path = media_root() / f"project_{project_id}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_background_presets() -> list[dict]:
    presets: list[dict] = []
    for path in sorted(preset_media_dir().glob("*")):
        if path.suffix.lower() not in {".mp4", ".webm", ".mpeg"}:
            continue
        presets.append(
            {
                "key": path.stem,
                "name": path.stem.replace("_", " ").title(),
                "description": "Curated background preset",
                "filename": path.name,
                "path": path,
            }
        )
    return presets


def resolve_background_preset(preset_key: str) -> dict:
    for preset in list_background_presets():
        if preset["key"] == preset_key:
            return preset
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Background preset not found")


async def save_background_asset(project_id: int, file: UploadFile) -> tuple[Path, int, str]:
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Filename is required")
    if file.content_type not in ALLOWED_BACKGROUND_VIDEO_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported background video type",
        )

    destination = project_media_dir(project_id) / f"{uuid.uuid4().hex}_{Path(file.filename).name}"
    size = 0

    try:
        await file.seek(0)
        with open(destination, "wb") as out_file:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_BACKGROUND_VIDEO_SIZE:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="Background video exceeds 100MB limit",
                    )
                out_file.write(chunk)
    except HTTPException:
        if destination.exists():
            destination.unlink()
        raise
    finally:
        await file.close()

    return destination, size, file.content_type or mimetypes.guess_type(destination.name)[0] or "video/mp4"


def copy_preset_to_project(project_id: int, preset_key: str) -> tuple[Path, int, str]:
    preset = resolve_background_preset(preset_key)
    source_path: Path = preset["path"]
    destination = project_media_dir(project_id) / f"{uuid.uuid4().hex}_{source_path.name}"
    shutil.copy2(source_path, destination)
    return destination, destination.stat().st_size, guess_mime_type(str(destination))


def store_generated_file(project_id: int, source_path: str, filename: str | None = None) -> Path:
    output_name = filename or f"{uuid.uuid4().hex}.mp4"
    destination = project_media_dir(project_id) / output_name
    shutil.copy2(source_path, destination)
    return destination


def delete_storage_key(storage_key: str) -> None:
    path = Path(storage_key)
    if path.exists() and path.is_file():
        path.unlink()


def guess_mime_type(storage_key: str) -> str:
    return mimetypes.guess_type(storage_key)[0] or "application/octet-stream"
