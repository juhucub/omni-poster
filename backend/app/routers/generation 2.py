from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.db import SessionLocal
from app.models import Asset, GenerationJob, OutputVideo, Project, User
from app.routers.projects import get_owned_project
from app.schemas import GenerationJobCreateRequest, GenerationJobSummary, OkResponse
from app.services.project_state import sync_project_state
from app.services.rendering import ProjectRenderService
from app.services.storage import guess_mime_type, store_generated_file

router = APIRouter(tags=["generation"])


def latest_background_asset(project: Project) -> Asset | None:
    assets = [asset for asset in project.assets if asset.kind == "background_video"]
    assets.sort(key=lambda asset: asset.created_at, reverse=True)
    return assets[0] if assets else None


def to_generation_summary(job: GenerationJob) -> GenerationJobSummary:
    return GenerationJobSummary(
        id=job.id,
        project_id=job.project_id,
        status=job.status,
        progress=job.progress,
        style_preset=job.style_preset,
        error_message=job.error_message,
        output_video_id=job.output_video.id if job.output_video else None,
        started_at=job.started_at,
        finished_at=job.finished_at,
        created_at=job.created_at,
    )


def process_generation_job(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if not job:
            return
        project = db.get(Project, job.project_id)
        asset = db.get(Asset, job.input_asset_id)
        if not job or not project or not asset or not job.script_revision:
            return

        job.status = "processing"
        job.progress = 20
        job.started_at = datetime.utcnow()
        project.status = "rendering"
        db.commit()

        render_service = ProjectRenderService()
        result = render_service.render_preview(
            project_id=project.id,
            background_video_path=asset.storage_key,
            parsed_lines=job.script_revision.parsed_lines_json,
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
    except Exception as exc:
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
    finally:
        db.close()


@router.post("/projects/{project_id}/generation-jobs", response_model=GenerationJobSummary, status_code=status.HTTP_201_CREATED)
def create_generation_job(
    project_id: int,
    payload: GenerationJobCreateRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_owned_project(db, current_user.id, project_id)
    background_asset = latest_background_asset(project)
    if not background_asset:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project needs a background video")

    script_revision = project.current_script_revision
    if payload.script_revision_id is not None:
        script_revision = next(
            (revision for revision in project.script_revisions if revision.id == payload.script_revision_id),
            None,
        )
    if not script_revision:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project needs an editable script")

    job = GenerationJob(
        project_id=project.id,
        input_asset_id=background_asset.id,
        script_revision_id=script_revision.id,
        style_preset=payload.background_style,
        status="queued",
        progress=0,
    )
    project.status = "rendering"
    db.add(job)
    db.commit()
    db.refresh(job)
    background_tasks.add_task(process_generation_job, job.id)
    return to_generation_summary(job)


@router.get("/generation-jobs/{job_id}", response_model=GenerationJobSummary)
def get_generation_job(job_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = (
        db.query(GenerationJob)
        .join(Project, Project.id == GenerationJob.project_id)
        .filter(GenerationJob.id == job_id, Project.user_id == current_user.id)
        .one_or_none()
    )
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation job not found")
    return to_generation_summary(job)


@router.post("/generation-jobs/{job_id}/cancel", response_model=OkResponse)
def cancel_generation_job(job_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = (
        db.query(GenerationJob)
        .join(Project, Project.id == GenerationJob.project_id)
        .filter(GenerationJob.id == job_id, Project.user_id == current_user.id)
        .one_or_none()
    )
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation job not found")
    if job.status != "queued":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only queued jobs can be canceled")
    job.status = "canceled"
    job.finished_at = datetime.utcnow()
    project = db.get(Project, job.project_id)
    if project:
        sync_project_state(project)
    db.commit()
    return OkResponse()
