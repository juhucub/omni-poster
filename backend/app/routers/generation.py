from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.http_rate_limit import enforce_rate_limit
from app.dependencies import get_current_user, get_db
from app.models import Asset, GenerationJob, OutputVideo, Project, User
from app.routers.projects import get_owned_project
from app.schemas import (
    GenerationJobCreateRequest,
    GenerationJobSummary,
    OkResponse,
    OutputVideoListResponse,
)
from app.services.audit import record_audit
from app.services.notifications import create_notification
from app.services.project_state import sync_project_state, to_generation_summary, to_output_video_summary
from app.tasks.generation import process_generation_job

router = APIRouter(tags=["generation"])


def latest_background_asset(project: Project) -> Asset | None:
    if project.background_asset_id:
        return next((asset for asset in project.assets if asset.id == project.background_asset_id), None)
    assets = [asset for asset in project.assets if asset.kind in {"background_video", "background_preset"}]
    assets.sort(key=lambda asset: asset.created_at, reverse=True)
    return assets[0] if assets else None


@router.post("/projects/{project_id}/generation-jobs", response_model=GenerationJobSummary, status_code=status.HTTP_201_CREATED)
@router.post("/projects/{project_id}/renders", response_model=GenerationJobSummary, status_code=status.HTTP_201_CREATED)
def create_generation_job(
    project_id: int,
    payload: GenerationJobCreateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    enforce_rate_limit(
        "generation.create",
        str(current_user.id),
        limit=settings.HEAVY_ENDPOINT_RATE_LIMIT_COUNT,
        window_seconds=settings.HEAVY_ENDPOINT_RATE_LIMIT_WINDOW_SECONDS,
    )
    project = get_owned_project(db, current_user.id, project_id)
    background_asset = latest_background_asset(project)
    if not background_asset:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project needs a background video or preset")

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
        output_kind=payload.output_kind,
        provider_name=payload.provider_name,
        status="queued",
        progress=0,
    )
    project.status = "render_queued"
    db.add(job)
    db.flush()
    create_notification(
        db,
        user_id=current_user.id,
        project_id=project.id,
        category="render.queued",
        message=f"{payload.output_kind.title()} render job #{job.id} is queued.",
        payload={"job_id": job.id, "output_kind": payload.output_kind},
    )
    record_audit(
        db,
        user_id=current_user.id,
        action="render.queued",
        entity_type="generation_job",
        entity_id=job.id,
        metadata={"project_id": project.id, "output_kind": payload.output_kind},
    )
    db.commit()
    db.refresh(job)
    process_generation_job.delay(job.id)
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


@router.get("/projects/{project_id}/outputs", response_model=OutputVideoListResponse)
def list_project_outputs(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_owned_project(db, current_user.id, project_id)
    outputs = sorted(project.output_videos, key=lambda output: output.created_at, reverse=True)
    return OutputVideoListResponse(items=[to_output_video_summary(item) for item in outputs])


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
