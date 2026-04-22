from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.celery_app import celery
from app.db import SessionLocal
from app.models import Asset, GenerationJob, OutputVideo, Project
from app.services.project_state import sync_project_state
from app.services.rendering import ProjectRenderService
from app.services.storage import guess_mime_type, store_generated_file

logger = logging.getLogger(__name__)


@celery.task(name="app.tasks.generation.process_generation_job")
def process_generation_job(job_id: int) -> dict:
    db: Session = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if not job:
            return {"ok": False, "reason": "missing_job"}
        if job.status not in {"queued", "retrying"}:
            return {"ok": True, "status": job.status}

        project = db.get(Project, job.project_id)
        asset = db.get(Asset, job.input_asset_id)
        script_revision = job.script_revision
        if not project or not asset or not script_revision:
            raise RuntimeError("Generation job references missing project data.")

        job.status = "processing"
        job.progress = 20
        job.started_at = datetime.utcnow()
        job.error_message = None
        project.status = "rendering"
        db.commit()

        render_service = ProjectRenderService()
        result = render_service.render_preview(
            project_id=project.id,
            background_video_path=asset.storage_key,
            parsed_lines=script_revision.parsed_lines_json,
            style_preset=job.style_preset,
        )

        generated_path = result["output_path"].replace("file://", "")
        stored_path = store_generated_file(project.id, generated_path, f"preview_{job.id}.mp4")
        output_asset = Asset(
            user_id=project.user_id,
            project_id=project.id,
            kind="render_output",
            storage_key=str(stored_path),
            original_filename=stored_path.name,
            mime_type=guess_mime_type(str(stored_path)),
            size_bytes=stored_path.stat().st_size,
            duration_ms=int((result.get("duration_seconds") or 0) * 1000) or None,
        )
        db.add(output_asset)
        db.flush()

        output_video = OutputVideo(
            project_id=project.id,
            generation_job_id=job.id,
            asset_id=output_asset.id,
            is_preview=True,
            duration_ms=output_asset.duration_ms,
        )
        db.add(output_video)
        db.flush()

        project.current_output_video_id = output_video.id
        project.background_style = job.style_preset
        project.approved_at = None
        job.status = "completed"
        job.progress = 100
        job.finished_at = datetime.utcnow()
        sync_project_state(project)
        db.commit()
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
            db.commit()
        return {"ok": False, "reason": str(exc)}
    finally:
        db.close()
