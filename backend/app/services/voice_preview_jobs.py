from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.models import CharacterPreset, VoicePreviewJob
from app.schemas import TTSFailureResponse, VoiceLabPreviewResponse

ACTIVE_VOICE_PREVIEW_STATUSES = {"queued", "processing"}
STALE_VOICE_PREVIEW_MINUTES = 1.5
STALE_VOICE_PREVIEW_ERROR_CODE = "worker_lost_oom"
STALE_VOICE_PREVIEW_ERROR_MESSAGE = "OpenVoice worker was killed before the preview completed, likely due to running out of memory."
STALE_VOICE_PREVIEW_SUGGESTED_ACTION = "Reduce OpenVoice usage for previews or increase Docker memory, then try again."


def build_voice_preview_failure(
    *,
    code: str,
    message: str,
    provider_state: dict[str, Any] | None = None,
    fallback_attempted: bool = False,
    attempted_providers: list[str] | None = None,
    provider_failures: dict[str, Any] | None = None,
    suggested_action: str = "Check the worker logs and retry the preview.",
) -> dict[str, Any]:
    return TTSFailureResponse(
        code=code,
        message=message,
        provider_state=provider_state or {},
        fallback_attempted=fallback_attempted,
        attempted_providers=attempted_providers or [],
        provider_failures=provider_failures or {},
        suggested_action=suggested_action,
    ).model_dump()


def create_voice_preview_job(
    *,
    user_id: int,
    preset: CharacterPreset,
    requested_provider: str,
    fallback_allowed: bool,
    sample_text: str,
    controls_applied: dict[str, Any],
    provider_state: dict[str, Any],
    reference_audio_count: int,
    db: Session,
) -> VoicePreviewJob:
    job = VoicePreviewJob(
        user_id=user_id,
        preset_id=preset.id,
        voice_profile_id=preset.voice_profile_id,
        requested_provider=requested_provider,
        fallback_allowed=fallback_allowed,
        sample_text=sample_text,
        status="queued",
        progress=0,
        stage="queued",
        controls_applied_json=dict(controls_applied or {}),
        provider_state_json=dict(provider_state or {}),
        reference_audio_count=reference_audio_count,
    )
    db.add(job)
    db.flush()
    return job


def get_voice_preview_job(job_id: int, user_id: int, db: Session) -> VoicePreviewJob | None:
    return (
        db.query(VoicePreviewJob)
        .options(joinedload(VoicePreviewJob.preset), joinedload(VoicePreviewJob.voice_profile))
        .filter(VoicePreviewJob.id == job_id, VoicePreviewJob.user_id == user_id)
        .one_or_none()
    )


def reconcile_stale_voice_preview_jobs(
    db: Session,
    *,
    user_id: int | None = None,
    older_than_minutes: int = STALE_VOICE_PREVIEW_MINUTES,
    limit: int = 100,
) -> list[int]:
    cutoff = datetime.utcnow() - timedelta(minutes=older_than_minutes)
    query = db.query(VoicePreviewJob).filter(
        VoicePreviewJob.status == "processing",
        VoicePreviewJob.started_at.is_not(None),
        VoicePreviewJob.started_at <= cutoff,
        VoicePreviewJob.finished_at.is_(None),
    )
    if user_id is not None:
        query = query.filter(VoicePreviewJob.user_id == user_id)

    jobs = query.order_by(VoicePreviewJob.started_at.asc()).limit(limit).all()
    reconciled: list[int] = []
    for job in jobs:
        job.status = "failed"
        job.progress = 0
        job.stage = "failed"
        job.finished_at = datetime.utcnow()
        job.error_json = build_voice_preview_failure(
            code=STALE_VOICE_PREVIEW_ERROR_CODE,
            message=STALE_VOICE_PREVIEW_ERROR_MESSAGE,
            provider_state=dict(job.provider_state_json or {}),
            attempted_providers=[job.requested_provider] if job.requested_provider and job.requested_provider != "auto" else [],
            suggested_action=STALE_VOICE_PREVIEW_SUGGESTED_ACTION,
        )
        reconciled.append(job.id)
    return reconciled


def voice_preview_content_url(preview_audio_path: str | None) -> str | None:
    if not preview_audio_path:
        return None
    return f"/voice-lab/previews/{Path(preview_audio_path).name}"


def to_voice_preview_response(job: VoicePreviewJob) -> VoiceLabPreviewResponse:
    error_payload = dict(job.error_json or {}) if job.error_json else None
    return VoiceLabPreviewResponse(
        status=job.status,
        job_id=job.id,
        preset_id=job.preset_id,
        voice_profile_id=job.voice_profile_id,
        voice=job.voice,
        provider_used=job.provider_used,
        fallback_used=job.fallback_used,
        controls_applied=dict(job.controls_applied_json or {}),
        reference_audio_count=job.reference_audio_count,
        provider_state=dict(job.provider_state_json or {}),
        duration_seconds=job.duration_seconds,
        sample_text=job.sample_text,
        content_url=voice_preview_content_url(job.preview_audio_path),
        error=TTSFailureResponse(**error_payload) if error_payload else None,
    )
