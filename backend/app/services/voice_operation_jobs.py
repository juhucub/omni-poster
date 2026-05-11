from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import VoiceOperationJob, VoiceReferenceDataset
from app.services.memory_logging import log_memory_event
from app.services.voice_profiles import (
    ensure_seeded_voice_presets,
    ensure_voice_profile_editable,
    get_voice_profile_model,
    voice_reference_audio_profile_dir,
)

logger = logging.getLogger(__name__)

VOICE_OPERATION_TYPES = {
    "reference_audio_upload",
    "reference_dataset_clip_upload",
    "reference_dataset_analyze",
    "voice_model_attach",
    "voice_profile_prepare",
}
ACTIVE_VOICE_OPERATION_STATUSES = {"queued", "processing"}


def serialize_voice_operation_job(job: VoiceOperationJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "user_id": job.user_id,
        "voice_profile_id": job.voice_profile_id,
        "reference_dataset_id": job.reference_dataset_id,
        "operation_type": job.operation_type,
        "status": job.status,
        "progress": job.progress,
        "stage": job.stage,
        "request": dict(job.request_json or {}),
        "result": dict(job.result_json or {}) if job.result_json else None,
        "error": dict(job.error_json or {}) if job.error_json else None,
        "celery_task_id": job.celery_task_id,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }


def get_voice_operation_job(job_id: int, current_user_id: int, db: Session) -> VoiceOperationJob | None:
    return (
        db.query(VoiceOperationJob)
        .filter(VoiceOperationJob.id == job_id, VoiceOperationJob.user_id == current_user_id)
        .one_or_none()
    )


def create_voice_operation_job(
    *,
    operation_type: str,
    voice_profile_id: str,
    current_user_id: int,
    db: Session,
    reference_dataset_id: int | None = None,
    request: dict[str, Any] | None = None,
) -> VoiceOperationJob:
    if operation_type not in VOICE_OPERATION_TYPES:
        raise ValueError(f"Unsupported voice operation type: {operation_type}")
    job = VoiceOperationJob(
        user_id=current_user_id,
        voice_profile_id=voice_profile_id,
        reference_dataset_id=reference_dataset_id,
        operation_type=operation_type,
        status="queued",
        progress=0,
        stage="queued",
        request_json=dict(request or {}),
    )
    db.add(job)
    db.flush()
    return job


def mark_voice_operation_queued(job: VoiceOperationJob, *, celery_task_id: str, db: Session) -> VoiceOperationJob:
    job.celery_task_id = celery_task_id
    job.status = "queued"
    job.stage = "queued"
    job.progress = 0
    db.commit()
    db.refresh(job)
    return job


def mark_voice_operation_failed(
    job: VoiceOperationJob,
    *,
    error: dict[str, Any],
    db: Session,
    progress: int = 0,
    stage: str = "failed",
) -> VoiceOperationJob:
    job.status = "failed"
    job.progress = progress
    job.stage = stage
    job.error_json = error
    job.finished_at = datetime.utcnow()
    db.commit()
    db.refresh(job)
    return job


def validate_voice_operation_profile(
    *,
    voice_profile_id: str,
    current_user_id: int,
    db: Session,
    reference_dataset_id: int | None = None,
) -> None:
    ensure_seeded_voice_presets(db)
    profile = get_voice_profile_model(voice_profile_id, db)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice profile not found")
    ensure_voice_profile_editable(profile, current_user_id)
    if reference_dataset_id is not None:
        dataset = (
            db.query(VoiceReferenceDataset)
            .filter(
                VoiceReferenceDataset.id == reference_dataset_id,
                VoiceReferenceDataset.voice_profile_id == voice_profile_id,
            )
            .one_or_none()
        )
        if not dataset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice reference dataset not found")


def stage_voice_reference_upload(
    *,
    file: UploadFile,
    voice_profile_id: str,
    current_user_id: int,
    authorization_confirmed: bool,
    authorization_note: str | None,
    db: Session,
    reference_dataset_id: int | None = None,
) -> dict[str, Any]:
    if not authorization_confirmed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must confirm that the reference audio is original or explicitly authorized.",
        )
    validate_voice_operation_profile(
        voice_profile_id=voice_profile_id,
        current_user_id=current_user_id,
        db=db,
        reference_dataset_id=reference_dataset_id,
    )
    allowed_types = {item.strip() for item in settings.VOICE_LAB_ALLOWED_AUDIO_TYPES.split(",") if item.strip()}
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsupported reference audio type")
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Filename is required")

    pending_dir = voice_reference_audio_profile_dir(voice_profile_id) / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)
    safe_suffix = Path(file.filename).suffix or ".bin"
    pending_path = pending_dir / f"{uuid.uuid4().hex}{safe_suffix}"
    digest = hashlib.sha256()
    size_bytes = 0
    try:
        with pending_path.open("wb") as handle:
            for chunk in iter(lambda: file.file.read(1024 * 1024), b""):
                size_bytes += len(chunk)
                if size_bytes > settings.VOICE_LAB_MAX_REFERENCE_AUDIO_SIZE_BYTES:
                    pending_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="Reference audio exceeds max size",
                    )
                digest.update(chunk)
                handle.write(chunk)
    finally:
        try:
            file.file.close()
        except Exception:
            pass

    request = {
        "pending_path": str(pending_path),
        "original_filename": file.filename,
        "content_type": file.content_type,
        "uploaded_file_size_bytes": size_bytes,
        "uploaded_file_sha256": digest.hexdigest(),
        "authorization_confirmed": True,
        "authorization_note": authorization_note,
    }
    log_memory_event(
        logger,
        "voice.operation.upload_staged",
        operation_type="reference_dataset_clip_upload" if reference_dataset_id else "reference_audio_upload",
        voice_profile_id=voice_profile_id,
        reference_dataset_id=reference_dataset_id,
        pending_path=str(pending_path),
        uploaded_file_size_bytes=size_bytes,
    )
    return request
