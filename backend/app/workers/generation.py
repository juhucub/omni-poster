from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.celery_app import celery
from app.db import SessionLocal
from app.models import Asset, GenerationJob, OutputVideo, Project
from app.services.notifications import create_notification
from app.services.project_state import sync_project_state
from app.services.render_performance import build_performance_summary
from app.services.rendering import ProjectRenderService
from app.services.storage import guess_mime_type, project_media_dir, store_generated_file
from app.services.tts import TTSProviderError

# Compatibility shims — job constants and recovery moved to domains/jobs
from app.domains.jobs.statuses import (  # noqa: F401
    ACTIVE_GENERATION_STATUSES,
    STALE_GENERATION_ERROR,
    STALE_GENERATION_MINUTES,
)
from app.domains.jobs.recovery import reconcile_stale_generation_jobs  # noqa: F401

logger = logging.getLogger(__name__)


def _set_job_progress(db: Session, job: GenerationJob, project: Project, progress: int, *, status: str | None = None) -> None:
    job.progress = progress
    if status:
        job.status = status
    if progress < 100:
        project.status = "rendering"
    db.commit()


def _render_progress_callback(db: Session, job: GenerationJob, project: Project):
    last_progress = job.progress

    def callback(stage: str, progress: int) -> None:
        nonlocal last_progress
        if progress <= last_progress:
            return
        logger.info("Generation job %s advanced to stage=%s progress=%s", job.id, stage, progress)
        _set_job_progress(db, job, project, progress)
        last_progress = progress

    return callback


@celery.task(name="app.tasks.generation.process_generation_job")
def process_generation_job(job_id: int) -> dict:
    db: Session = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if not job:
            return {"ok": False, "reason": "missing_job"}
        if job.status not in ACTIVE_GENERATION_STATUSES:
            return {"ok": True, "status": job.status}

        project = db.get(Project, job.project_id)
        asset = db.get(Asset, job.input_asset_id)
        script_revision = job.script_revision
        if not project or not asset or not script_revision:
            raise RuntimeError("Generation job references missing project data.")

        reconcile_stale_generation_jobs(db, project_id=job.project_id)
        job.status = "processing"
        job.progress = 20
        job.started_at = datetime.utcnow()
        job.error_message = None
        project.status = "rendering"
        db.commit()
        logger.info("Generation job %s started for project %s", job.id, project.id)

        render_service = ProjectRenderService(db=db, project_id=project.id)
        progress_callback = _render_progress_callback(db, job, project)
        direct_output_path = project_media_dir(project.id) / f"preview_{job.id}.mp4"
        try:
            _set_job_progress(db, job, project, 35)
            logger.info("Generation job %s entering render pipeline", job.id)
            result = render_service.render_preview(
                project_id=project.id,
                background_video_path=asset.storage_key,
                parsed_lines=script_revision.parsed_lines_json,
                style_preset=job.style_preset,
                output_kind=job.output_kind,
                progress_callback=progress_callback,
                voice_manifest=job.voice_manifest_json or {},
                render_settings=job.render_settings_json or {},
                job_id=job.id,
                output_path=direct_output_path,
            )
        except TypeError:
            # Compatibility for tests and legacy local monkeypatches that still use the older signature.
            result = render_service.render_preview(
                project.id,
                asset.storage_key,
                script_revision.parsed_lines_json,
                job.style_preset,
            )
        metadata = dict(result.get("metadata") or {})
        tts_result = dict(metadata.get("tts_result") or {})
        if tts_result:
            # Persist provider diagnostics separately from the output asset so failed/refresh states remain explainable.
            job.tts_result_json = tts_result
            job.provider_state_json = dict(tts_result.get("provider_state") or {})
        _set_job_progress(db, job, project, 70)
        logger.info("Generation job %s render pipeline produced output %s", job.id, result.get("output_path"))

        generated_path = result["output_path"].replace("file://", "")
        # Store the final MP4 as a project asset while segment WAVs stay under generated job artifacts.
        stored_path = Path(generated_path)
        if stored_path.resolve() != direct_output_path.resolve():
            stored_path = store_generated_file(project.id, generated_path, f"preview_{job.id}.mp4")
        _set_job_progress(db, job, project, 82)
        output_asset = Asset(
            user_id=project.user_id,
            project_id=project.id,
            kind="render_output",
            source_type="generated",
            provider_name=job.provider_name,
            storage_key=str(stored_path),
            original_filename=stored_path.name,
            mime_type=guess_mime_type(str(stored_path)),
            size_bytes=stored_path.stat().st_size,
            duration_ms=int((result.get("duration_seconds") or 0) * 1000) or None,
            metadata_json=metadata,
        )
        db.add(output_asset)
        db.flush()
        _set_job_progress(db, job, project, 90)

        output_video = OutputVideo(
            project_id=project.id,
            generation_job_id=job.id,
            asset_id=output_asset.id,
            output_kind=job.output_kind,
            provider_name=job.provider_name,
            is_preview=job.output_kind == "preview",
            duration_ms=output_asset.duration_ms,
        )
        db.add(output_video)
        db.flush()
        _set_job_progress(db, job, project, 95)

        project.current_output_video_id = output_video.id
        project.background_asset_id = project.background_asset_id or asset.id
        project.background_style = job.style_preset
        project.approved_at = None
        project.status = "preview_ready" if job.output_kind == "preview" else "assets_ready"
        job.status = "completed"
        job.progress = 100
        job.finished_at = datetime.utcnow()
        if job.started_at:
            generation_job_duration_seconds = max((job.finished_at - job.started_at).total_seconds(), 0.0)
            job_tts_result = dict(job.tts_result_json or {})
            job_tts_result["generation_job_duration_seconds"] = generation_job_duration_seconds
            job.tts_result_json = job_tts_result
            job_tts_result["performance_summary"] = build_performance_summary(job)
            job.tts_result_json = job_tts_result
            output_metadata = dict(output_asset.metadata_json or {})
            output_metadata["generation_job_duration_seconds"] = generation_job_duration_seconds
            output_metadata["performance_summary"] = job_tts_result["performance_summary"]
            if isinstance(output_metadata.get("tts_result"), dict):
                output_metadata["tts_result"] = {
                    **dict(output_metadata["tts_result"]),
                    "generation_job_duration_seconds": generation_job_duration_seconds,
                    "performance_summary": job_tts_result["performance_summary"],
                }
            output_asset.metadata_json = output_metadata
        sync_project_state(project)
        create_notification(
            db,
            user_id=project.user_id,
            project_id=project.id,
            category="render.ready",
            message=f"{job.output_kind.title()} render is ready for review.",
            payload={"job_id": job.id, "output_video_id": output_video.id},
        )
        db.commit()
        logger.info("Generation job %s completed with output video %s", job.id, output_video.id)
        return {"ok": True, "status": job.status, "output_video_id": output_video.id}
    except TTSProviderError as exc:
        logger.exception("Generation job %s failed during TTS provider selection", job_id)
        db.rollback()
        job = db.get(GenerationJob, job_id)
        if job:
            project = db.get(Project, job.project_id)
            error_payload = exc.as_dict()
            job.status = "failed"
            job.progress = 0
            job.error_message = exc.message
            job.tts_result_json = {"status": "failed", "error": error_payload}
            job.provider_state_json = dict(exc.provider_state or {})
            job.finished_at = datetime.utcnow()
            if project:
                project.status = "failed"
                create_notification(
                    db,
                    user_id=project.user_id,
                    project_id=project.id,
                    category="render.failed",
                    message="A render job failed because the selected TTS provider was unavailable.",
                    payload={"job_id": job.id, "error": error_payload},
                )
            db.commit()
        return {"ok": False, "reason": exc.message, "error": exc.as_dict()}
    except Exception as exc:
        logger.exception("Generation job %s failed", job_id)
        db.rollback()
        job = db.get(GenerationJob, job_id)
        if job:
            project = db.get(Project, job.project_id)
            job.status = "failed"
            job.progress = 0
            job.error_message = str(exc)
            job.finished_at = datetime.utcnow()
            if project:
                project.status = "failed"
                create_notification(
                    db,
                    user_id=project.user_id,
                    project_id=project.id,
                    category="render.failed",
                    message="A render job failed and needs attention.",
                    payload={"job_id": job.id, "error": str(exc)},
                )
            db.commit()
        return {"ok": False, "reason": str(exc)}
    finally:
        db.close()


@celery.task(name="app.tasks.generation.reconcile_stale_generation_jobs")
def reconcile_stale_generation_jobs_task(limit: int = 100) -> dict:
    db: Session = SessionLocal()
    try:
        reconciled = reconcile_stale_generation_jobs(db, limit=limit)
        db.commit()
        return {"reconciled": len(reconciled), "job_ids": reconciled}
    finally:
        db.close()
