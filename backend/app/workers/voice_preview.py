from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.celery_app import celery
from app.db import SessionLocal
from app.models import VoicePreviewJob
from app.services.tts import TTSOrchestrator, TTSProviderError, apply_voice_lab_overrides
from app.services.voice_preview_jobs import (
    ACTIVE_VOICE_PREVIEW_STATUSES,
    build_voice_preview_failure,
    reconcile_stale_voice_preview_jobs,
)
from app.services.voice_profiles import runtime_voice_profile_payload, update_voice_profile_preparation_metadata, voice_lab_preview_dir

logger = logging.getLogger(__name__)


def _update_voice_preview_job_stage(preview_job_id: int, stage: str, progress: int) -> None:
    db: Session = SessionLocal()
    try:
        job = db.get(VoicePreviewJob, preview_job_id)
        if not job or job.status != "processing":
            return
        job.stage = stage
        job.progress = max(job.progress, progress)
        db.commit()
    finally:
        db.close()


def _load_preview_job_data(preview_job_id: int) -> dict[str, Any] | None:
    """Read the job, mark it processing, and return extracted data as plain Python values.

    Returns None if the job is missing, {"_skip": True} if it is already terminal, or a
    dict of all data needed for TTS synthesis so the session can be closed before the
    long-running TTS work begins.
    """
    db: Session = SessionLocal()
    try:
        job = (
            db.query(VoicePreviewJob)
            .options(
                joinedload(VoicePreviewJob.preset),
                joinedload(VoicePreviewJob.voice_profile),
            )
            .filter(VoicePreviewJob.id == preview_job_id)
            .one_or_none()
        )
        if not job:
            return None
        if job.status not in ACTIVE_VOICE_PREVIEW_STATUSES:
            return {"_skip": True, "status": job.status}

        job.status = "processing"
        job.progress = 20
        job.stage = "tts_started"
        job.started_at = datetime.utcnow()
        job.error_json = None
        db.commit()

        preset = job.preset
        profile_payload = runtime_voice_profile_payload(job.voice_profile, preset.display_name)
        profile_payload = apply_voice_lab_overrides(
            profile_payload,
            controls=dict(job.controls_applied_json or {}),
        )
        calibration = dict(job.calibration_json or {})
        recipe = dict(calibration.get("recipe") or {})
        if recipe:
            profile_payload["style"] = {
                **dict(profile_payload.get("style") or {}),
                "base_speaker": recipe.get("base_speaker"),
                "style_preset": recipe.get("style_preset") or "default",
            }
            provider_metadata = dict(profile_payload.get("provider_metadata") or {})
            if calibration.get("processed_reference_paths"):
                provider_metadata["processed_reference_paths"] = list(calibration.get("processed_reference_paths") or [])
                provider_metadata["processed_reference_audio_ids"] = list(calibration.get("processed_reference_audio_ids") or [])
            if calibration.get("reference_audio_sha256"):
                provider_metadata["reference_audio_sha256"] = calibration.get("reference_audio_sha256")
            if calibration.get("embedding_path"):
                profile_payload["embedding_path"] = calibration.get("embedding_path")
                provider_metadata["embedding_artifact_path"] = calibration.get("embedding_path")
            profile_payload["provider_metadata"] = provider_metadata

        return {
            "preset_display_name": preset.display_name,
            "preset_id": job.preset_id,
            "voice_profile_id": job.voice_profile_id,
            "profile_payload": profile_payload,
            "requested_provider": job.requested_provider,
            "fallback_allowed": job.fallback_allowed,
            "sample_text": job.sample_text,
        }
    finally:
        db.close()


def _write_preview_success(
    preview_job_id: int,
    *,
    result: Any,
    profile_payload: dict[str, Any],
    orchestrator: TTSOrchestrator,
) -> None:
    db: Session = SessionLocal()
    try:
        job = db.get(VoicePreviewJob, preview_job_id)
        if not job:
            return
        if result.provider_used == "openvoice" and profile_payload.get("embedding_path") and job.voice_profile is not None:
            provider_metadata = dict(profile_payload.get("provider_metadata") or {})
            update_voice_profile_preparation_metadata(
                job.voice_profile,
                embedding_path=str(profile_payload.get("embedding_path")),
                provider_metadata={
                    **provider_metadata,
                    "embedding_status": "ready",
                    "embedding_ready": True,
                    "embedding_artifact_path": str(profile_payload.get("embedding_path")),
                    "active_reference_count": len(profile_payload.get("reference_audios") or []),
                    "reference_audio_mode": "average_all_clips" if len(profile_payload.get("reference_audios") or []) > 1 else "single_clip",
                },
                db=db,
            )
            db.refresh(job)
        job.status = "completed"
        job.progress = 100
        job.stage = "completed"
        job.voice = result.voice
        job.provider_used = result.provider_used
        job.fallback_used = result.fallback_used
        job.controls_applied_json = dict(result.controls_applied or {})
        job.provider_state_json = orchestrator.provider_state()
        job.reference_audio_count = result.reference_audio_count
        job.duration_seconds = result.duration_seconds
        job.preview_audio_path = result.audio_path
        job.finished_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()


def _write_preview_provider_error(preview_job_id: int, exc: TTSProviderError) -> None:
    db: Session = SessionLocal()
    try:
        job = db.get(VoicePreviewJob, preview_job_id)
        if not job:
            return
        if job.voice_profile is not None:
            job.voice_profile.embedding_path = None
            metadata = dict(job.voice_profile.provider_metadata_json or {})
            metadata.update(
                {
                    "embedding_status": "failed",
                    "embedding_ready": False,
                    "embedding_artifact_path": None,
                    "last_error": exc.as_dict(),
                }
            )
            job.voice_profile.provider_metadata_json = metadata
        job.status = "failed"
        job.progress = 0
        job.stage = "failed"
        job.provider_state_json = dict(exc.provider_state or {})
        job.error_json = exc.as_dict()
        job.finished_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()


def _write_preview_error(preview_job_id: int, exc: Exception) -> None:
    db: Session = SessionLocal()
    try:
        job = db.get(VoicePreviewJob, preview_job_id)
        if not job:
            return
        job.status = "failed"
        job.progress = 0
        job.stage = "failed"
        job.error_json = build_voice_preview_failure(
            code="voice_lab_preview_failed",
            message=f"Voice preview failed: {exc}",
        )
        job.finished_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()


@celery.task(
    name="app.tasks.voice_preview.process_voice_lab_preview",
    acks_late=False,
    reject_on_worker_lost=False,
)
def process_voice_lab_preview(preview_job_id: int) -> dict:
    job_data = _load_preview_job_data(preview_job_id)
    if job_data is None:
        return {"ok": False, "reason": "missing_job"}
    if job_data.get("_skip"):
        return {"ok": True, "status": job_data["status"]}

    preset_id = job_data["preset_id"]
    voice_profile_id = job_data["voice_profile_id"]
    profile_payload = job_data["profile_payload"]

    preview_dir = voice_lab_preview_dir()
    orchestrator = TTSOrchestrator()
    try:
        segments = orchestrator.synthesize_dialogue(
            lines=[{"speaker": job_data["preset_display_name"], "text": job_data["sample_text"], "order": 0}],
            voice_profile_map={job_data["preset_display_name"]: profile_payload},
            output_dir=preview_dir,
            requested_provider=job_data["requested_provider"],
            fallback_allowed=job_data["fallback_allowed"],
            options={"stage_callback": lambda stage, progress: _update_voice_preview_job_stage(preview_job_id, stage, progress)},
        )
    except TTSProviderError as exc:
        logger.warning("Voice preview job %s failed with provider error %s", preview_job_id, exc.code)
        _write_preview_provider_error(preview_job_id, exc)
        return {"ok": False, "reason": exc.code}
    except Exception as exc:
        logger.exception("Voice preview job %s failed", preview_job_id)
        _write_preview_error(preview_job_id, exc)
        return {"ok": False, "reason": str(exc)}

    result = segments[0]
    _write_preview_success(preview_job_id, result=result, profile_payload=profile_payload, orchestrator=orchestrator)
    logger.info("Voice preview job %s completed for preset=%s profile=%s", preview_job_id, preset_id, voice_profile_id)
    return {"ok": True, "status": "completed", "job_id": preview_job_id}


@celery.task(name="app.tasks.voice_preview.reconcile_stale_voice_preview_jobs")
def reconcile_stale_voice_preview_jobs_task(limit: int = 100) -> dict:
    db: Session = SessionLocal()
    try:
        reconciled = reconcile_stale_voice_preview_jobs(db, limit=limit)
        db.commit()
        if reconciled:
            logger.warning("Reconciled stale voice preview jobs: %s", reconciled)
        return {"reconciled": len(reconciled), "job_ids": reconciled}
    finally:
        db.close()
