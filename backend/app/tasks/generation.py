from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.celery_app import celery
from app.db import SessionLocal
from app.models import Asset, GenerationJob, OutputVideo, Project
from app.services.notifications import create_notification
from app.services.project_state import sync_project_state
from app.services.rendering import ProjectRenderService
from app.services.storage import guess_mime_type, store_generated_file

logger = logging.getLogger(__name__)

ACTIVE_GENERATION_STATUSES = {"queued", "processing", "retrying"}
STALE_GENERATION_MINUTES = 15
STALE_GENERATION_ERROR = "worker lost during render"


def reconcile_stale_generation_jobs(
    db: Session,
    *,
    project_id: int | None = None,
    older_than_minutes: int = STALE_GENERATION_MINUTES,
    limit: int = 100,
) -> list[int]:
    cutoff = datetime.utcnow() - timedelta(minutes=older_than_minutes)
    query = db.query(GenerationJob).filter(
        GenerationJob.status == "processing",
        GenerationJob.started_at.is_not(None),
        GenerationJob.started_at <= cutoff,
        GenerationJob.finished_at.is_(None),
    )
    if project_id is not None:
        query = query.filter(GenerationJob.project_id == project_id)

    jobs = query.order_by(GenerationJob.started_at.asc()).limit(limit).all()
    reconciled: list[int] = []
    for job in jobs:
        job.status = "failed"
        job.progress = 0
        job.error_message = STALE_GENERATION_ERROR
        job.finished_at = datetime.utcnow()
        project = db.get(Project, job.project_id)
        if project:
            project.status = "failed"
            sync_project_state(project)
        reconciled.append(job.id)

    if reconciled:
        logger.warning("Reconciled stale generation jobs: %s", reconciled)
    return reconciled


def _set_job_progress(db: Session, job: GenerationJob, project: Project, progress: int, *, status: str | None = None) -> None:
    job.progress = progress
    if status:
        job.status = status
    if progress < 100:
        project.status = "rendering"
    db.commit()


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

        render_service = ProjectRenderService()
        try:
            _set_job_progress(db, job, project, 35)
            logger.info("Generation job %s entering render pipeline", job.id)
            result = render_service.render_preview(
                project_id=project.id,
                background_video_path=asset.storage_key,
                parsed_lines=script_revision.parsed_lines_json,
                style_preset=job.style_preset,
                output_kind=job.output_kind,
            )
        except TypeError:
            # Compatibility for tests and legacy local monkeypatches that still use the older signature.
            result = render_service.render_preview(
                project.id,
                asset.storage_key,
                script_revision.parsed_lines_json,
                job.style_preset,
            )
        _set_job_progress(db, job, project, 70)
        logger.info("Generation job %s render pipeline produced output %s", job.id, result.get("output_path"))

        generated_path = result["output_path"].replace("file://", "")
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
