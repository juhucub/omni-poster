from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.celery_app import celery
from app.db import SessionLocal
from app.models import VoiceCalibrationBatch, VoiceOperationJob
from app.services.memory_logging import log_memory_event
from app.services.tts import TTSOrchestrator, TTSProviderError
from app.services.voice_operation_jobs import serialize_voice_operation_job
from app.services.voice_profiles import (
    get_voice_profile,
    get_voice_profile_model,
    runtime_voice_profile_payload,
    save_reference_audio_content,
    update_voice_profile_preparation_metadata,
)
from app.services.voice_replication import (
    analyze_voice_reference_dataset,
    attach_character_voice_model,
    process_calibration_batch,
    save_reference_audio_content_for_dataset,
    serialize_calibration_batch,
)

logger = logging.getLogger(__name__)


def _http_error_payload(exc: HTTPException) -> dict[str, Any]:
    detail = exc.detail
    message = detail if isinstance(detail, str) else detail.get("message") if isinstance(detail, dict) else str(detail)
    return {
        "code": "voice_operation_validation_failed" if exc.status_code == 400 else "voice_operation_failed",
        "message": message or "Voice operation failed.",
        "http_status": exc.status_code,
        "detail": detail,
    }


def _generic_error_payload(exc: Exception) -> dict[str, Any]:
    return {
        "code": "voice_operation_failed",
        "message": f"Voice operation failed: {exc}",
        "http_status": 500,
        "detail": str(exc),
    }


def _set_job_stage(db: Session, job: VoiceOperationJob, stage: str, progress: int) -> None:
    job.stage = stage
    job.progress = max(job.progress, progress)
    db.commit()
    log_memory_event(
        logger,
        "voice.operation.worker_stage",
        operation_type=job.operation_type,
        voice_profile_id=job.voice_profile_id,
        reference_dataset_id=job.reference_dataset_id,
        job_id=job.id,
        stage=stage,
    )


def _complete_job(db: Session, job: VoiceOperationJob, result: dict[str, Any]) -> dict[str, Any]:
    job.status = "completed"
    job.progress = 100
    job.stage = "completed"
    job.result_json = jsonable_encoder(result)
    job.error_json = None
    job.finished_at = datetime.utcnow()
    db.commit()
    db.refresh(job)
    log_memory_event(
        logger,
        "voice.operation.worker_completed",
        operation_type=job.operation_type,
        voice_profile_id=job.voice_profile_id,
        reference_dataset_id=job.reference_dataset_id,
        job_id=job.id,
        stage="completed",
    )
    return serialize_voice_operation_job(job)


def _fail_job(db: Session, job: VoiceOperationJob, error: dict[str, Any]) -> dict[str, Any]:
    job.status = "failed"
    job.progress = 0
    job.stage = "failed"
    job.error_json = jsonable_encoder(error)
    job.finished_at = datetime.utcnow()
    db.commit()
    db.refresh(job)
    logger.warning("Voice operation job %s failed: %s", job.id, error)
    log_memory_event(
        logger,
        "voice.operation.worker_failed",
        operation_type=job.operation_type,
        voice_profile_id=job.voice_profile_id,
        reference_dataset_id=job.reference_dataset_id,
        job_id=job.id,
        stage="failed",
    )
    return serialize_voice_operation_job(job)


@celery.task(
    name="app.tasks.voice_operations.process_voice_operation_job",
    acks_late=False,
    reject_on_worker_lost=False,
)
def process_voice_operation_job(job_id: int) -> dict[str, Any]:
    db: Session = SessionLocal()
    pending_path: Path | None = None
    try:
        job = db.get(VoiceOperationJob, job_id)
        if not job:
            return {"ok": False, "reason": "missing_job"}
        if job.status not in {"queued", "processing"}:
            return serialize_voice_operation_job(job)

        job.status = "processing"
        job.stage = "started"
        job.progress = 10
        job.started_at = datetime.utcnow()
        job.error_json = None
        db.commit()
        request = dict(job.request_json or {})
        log_memory_event(
            logger,
            "voice.operation.worker_started",
            operation_type=job.operation_type,
            voice_profile_id=job.voice_profile_id,
            reference_dataset_id=job.reference_dataset_id,
            job_id=job.id,
            stage="started",
        )

        if job.operation_type in {"reference_audio_upload", "reference_dataset_clip_upload"}:
            pending_path = Path(str(request.get("pending_path") or ""))
            if not pending_path.exists():
                raise HTTPException(status_code=400, detail="Staged reference audio is missing.")
            _set_job_stage(db, job, "validating_reference_audio", 30)
            content = pending_path.read_bytes()
            if job.operation_type == "reference_audio_upload":
                voice_profile, reference_audio = save_reference_audio_content(
                    content=content,
                    filename=str(request.get("original_filename") or pending_path.name),
                    content_type=request.get("content_type"),
                    voice_profile_id=job.voice_profile_id,
                    current_user_id=job.user_id,
                    authorization_confirmed=bool(request.get("authorization_confirmed")),
                    authorization_note=request.get("authorization_note"),
                    db=db,
                )
                return _complete_job(db, job, {"voice_profile": voice_profile, "reference_audio": reference_audio})
            voice_profile, dataset, reference_audio = save_reference_audio_content_for_dataset(
                content=content,
                filename=str(request.get("original_filename") or pending_path.name),
                content_type=request.get("content_type"),
                voice_profile_id=job.voice_profile_id,
                reference_dataset_id=int(job.reference_dataset_id or 0),
                current_user_id=job.user_id,
                authorization_confirmed=bool(request.get("authorization_confirmed")),
                authorization_note=request.get("authorization_note"),
                db=db,
            )
            return _complete_job(db, job, {"voice_profile": voice_profile, "dataset": dataset, "reference_audio": reference_audio})

        if job.operation_type == "reference_dataset_analyze":
            _set_job_stage(db, job, "analyzing_reference_dataset", 35)
            voice_profile, dataset = analyze_voice_reference_dataset(
                voice_profile_id=job.voice_profile_id,
                reference_dataset_id=int(job.reference_dataset_id or request.get("reference_dataset_id")),
                current_user_id=job.user_id,
                db=db,
            )
            return _complete_job(db, job, {"voice_profile": voice_profile, "dataset": dataset})

        if job.operation_type == "voice_model_attach":
            _set_job_stage(db, job, "attaching_model", 35)
            voice_profile = attach_character_voice_model(
                voice_profile_id=job.voice_profile_id,
                provider=str(request.get("provider")),
                character_slug=request.get("character_slug"),
                model_checkpoint_path=str(request.get("model_checkpoint_path")),
                model_index_path=request.get("model_index_path"),
                reference_dataset_id=request.get("reference_dataset_id"),
                recipe=dict(request.get("recipe") or {}),
                current_user_id=job.user_id,
                db=db,
            )
            return _complete_job(db, job, {"voice_profile": voice_profile})

        if job.operation_type == "voice_profile_prepare":
            _set_job_stage(db, job, "preparing_voice_profile", 25)
            profile_model = get_voice_profile_model(job.voice_profile_id, db)
            if not profile_model:
                raise HTTPException(status_code=404, detail="Voice profile not found.")
            payload = runtime_voice_profile_payload(profile_model, profile_model.display_name)
            orchestrator = TTSOrchestrator()
            result = orchestrator.prepare_voice_profile(payload)
            profile_model = update_voice_profile_preparation_metadata(
                profile_model,
                embedding_path=result.get("cached_artifact_path"),
                provider_metadata=result.get("provider_metadata"),
                db=db,
            )
            voice_profile = get_voice_profile(profile_model.id, db)
            return _complete_job(
                db,
                job,
                {
                    "voice_profile": voice_profile,
                    "provider_used": result["provider_used"],
                    "provider_state": result["provider_state"],
                    "prepared": result["prepared"],
                    "cached_artifact_path": result.get("cached_artifact_path"),
                    "message": result["message"],
                },
            )

        raise HTTPException(status_code=400, detail=f"Unsupported voice operation type: {job.operation_type}")
    except TTSProviderError as exc:
        db.rollback()
        job = db.get(VoiceOperationJob, job_id)
        if job:
            profile_model = get_voice_profile_model(job.voice_profile_id, db)
            if profile_model:
                profile_model.embedding_path = None
                metadata = dict(profile_model.provider_metadata_json or {})
                metadata.update(
                    {
                        "embedding_status": "failed",
                        "embedding_ready": False,
                        "embedding_artifact_path": None,
                        "last_error": exc.as_dict(),
                    }
                )
                profile_model.provider_metadata_json = metadata
            return _fail_job(db, job, {**exc.as_dict(), "http_status": 503})
        return {"ok": False, "reason": exc.code}
    except HTTPException as exc:
        db.rollback()
        job = db.get(VoiceOperationJob, job_id)
        return _fail_job(db, job, _http_error_payload(exc)) if job else {"ok": False, "reason": "missing_job_after_error"}
    except Exception as exc:
        logger.exception("Voice operation job %s failed", job_id)
        db.rollback()
        job = db.get(VoiceOperationJob, job_id)
        return _fail_job(db, job, _generic_error_payload(exc)) if job else {"ok": False, "reason": str(exc)}
    finally:
        if pending_path is not None:
            pending_path.unlink(missing_ok=True)
        db.close()


@celery.task(
    name="app.tasks.voice_operations.process_voice_calibration_batch",
    acks_late=False,
    reject_on_worker_lost=False,
)
def process_voice_calibration_batch(batch_id: int) -> dict[str, Any]:
    db: Session = SessionLocal()
    try:
        batch = db.get(VoiceCalibrationBatch, batch_id)
        if not batch:
            return {"ok": False, "reason": "missing_batch"}
        if batch.status not in {"queued", "processing"}:
            return serialize_calibration_batch(batch)
        log_memory_event(
            logger,
            "voice.calibration.worker_started",
            operation_type="voice_calibration_batch",
            voice_profile_id=batch.voice_profile_id,
            reference_dataset_id=batch.reference_dataset_id,
            job_id=batch.id,
            stage="started",
        )
        result = process_calibration_batch(batch_id=batch.id, db=db)
        log_memory_event(
            logger,
            "voice.calibration.worker_completed",
            operation_type="voice_calibration_batch",
            voice_profile_id=batch.voice_profile_id,
            reference_dataset_id=batch.reference_dataset_id,
            job_id=batch.id,
            stage=result.get("status"),
        )
        return result
    except Exception as exc:
        logger.exception("Voice calibration batch %s failed", batch_id)
        db.rollback()
        batch = db.get(VoiceCalibrationBatch, batch_id)
        if batch:
            batch.status = "failed"
            batch.error_json = _generic_error_payload(exc)
            batch.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(batch)
            return serialize_calibration_batch(batch)
        return {"ok": False, "reason": str(exc)}
    finally:
        db.close()
