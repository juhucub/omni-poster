from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.http_rate_limit import enforce_rate_limit
from app.dependencies import get_current_user, get_db
from app.models import OutputVideo, PlatformMetadata, Project, PublishJob, SocialAccount, User
from app.routers.projects import get_owned_project
from app.schemas import OkResponse, PublishJobSummary, PublishRequest
from app.services.audit import record_audit
from app.services.notifications import create_notification
from app.services.platforms import capability_for
from app.services.project_state import sync_project_state, to_publish_job_summary
from app.services.routing import choose_social_account, is_account_routing_eligible, suggest_destination
from app.tasks.publish import process_publish_job

router = APIRouter(tags=["publish"])


def _ensure_publishable_project(project: Project) -> None:
    if project.status != "approved" or not project.approved_at:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project must be approved in the review queue before publishing",
        )


def _resolve_output(db: Session, project: Project, output_video_id: int) -> OutputVideo:
    output_video = (
        db.query(OutputVideo)
        .filter(OutputVideo.id == output_video_id, OutputVideo.project_id == project.id)
        .one_or_none()
    )
    if not output_video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Output video not found")
    return output_video


def _resolve_metadata(db: Session, project: Project, metadata_id: int, platform: str) -> PlatformMetadata:
    metadata = (
        db.query(PlatformMetadata)
        .filter(
            PlatformMetadata.id == metadata_id,
            PlatformMetadata.project_id == project.id,
            PlatformMetadata.platform == platform,
        )
        .one_or_none()
    )
    if not metadata:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Metadata not found")
    if metadata.validation_errors_json:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Metadata has validation errors")
    return metadata


def _resolve_account(
    db: Session,
    *,
    current_user: User,
    project: Project,
    platform: str,
    social_account_id: int | None,
) -> SocialAccount:
    if social_account_id is not None:
        account = (
            db.query(SocialAccount)
            .filter(SocialAccount.id == social_account_id, SocialAccount.user_id == current_user.id)
            .one_or_none()
        )
        if not account:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Social account not found")
    else:
        account, _ = choose_social_account(project, user=current_user, platform=platform)
        if not account:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No eligible social account available")

    if not is_account_routing_eligible(account, platform=platform):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Selected account is not eligible for publishing")
    if account.platform != "youtube":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only YouTube publishing is supported today")
    return account


def _create_publish_job(
    db: Session,
    *,
    current_user: User,
    project: Project,
    payload: PublishRequest,
) -> PublishJob:
    _ensure_publishable_project(project)
    capability = capability_for(payload.platform)
    if payload.publish_mode == "schedule" and not capability.scheduling_supported:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"{payload.platform} does not support scheduling")

    output_video = _resolve_output(db, project, payload.output_video_id)
    metadata = _resolve_metadata(db, project, payload.platform_metadata_id, payload.platform)
    account = _resolve_account(
        db,
        current_user=current_user,
        project=project,
        platform=payload.platform,
        social_account_id=payload.social_account_id,
    )

    job = PublishJob(
        project_id=project.id,
        social_account_id=account.id,
        output_video_id=output_video.id,
        platform_metadata_id=metadata.id,
        routing_platform=payload.platform,
        automation_mode=payload.automation_mode,
        idempotency_key=uuid.uuid4().hex,
        status="publish_queued" if payload.publish_mode == "now" else "scheduled",
        scheduled_for=payload.scheduled_for if payload.publish_mode == "schedule" else None,
    )
    project.selected_social_account_id = account.id
    project.status = "publish_queued" if job.status == "publish_queued" else "scheduled"
    db.add(job)
    db.flush()
    create_notification(
        db,
        user_id=current_user.id,
        project_id=project.id,
        category="publish.queued" if job.status == "publish_queued" else "publish.scheduled",
        message=f"Publish job #{job.id} is {'queued' if job.status == 'publish_queued' else 'scheduled'}.",
        payload={"job_id": job.id, "platform": payload.platform},
    )
    record_audit(
        db,
        user_id=current_user.id,
        action="publish.job_created",
        entity_type="publish_job",
        entity_id=job.id,
        metadata={"project_id": project.id, "platform": payload.platform, "automation_mode": payload.automation_mode},
    )
    return job


@router.post("/projects/{project_id}/publish", response_model=PublishJobSummary, status_code=status.HTTP_201_CREATED)
def create_publish_job(
    project_id: int,
    payload: PublishRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    enforce_rate_limit(
        "publish.create",
        str(current_user.id),
        limit=settings.HEAVY_ENDPOINT_RATE_LIMIT_COUNT,
        window_seconds=settings.HEAVY_ENDPOINT_RATE_LIMIT_WINDOW_SECONDS,
    )
    project = get_owned_project(db, current_user.id, project_id)
    job = _create_publish_job(db, current_user=current_user, project=project, payload=payload)
    db.commit()
    db.refresh(job)

    if job.status == "publish_queued":
        process_publish_job.delay(job.id)

    return to_publish_job_summary(job)


@router.post("/projects/{project_id}/publish/auto", response_model=PublishJobSummary, status_code=status.HTTP_201_CREATED)
def auto_publish_project(
    project_id: int,
    payload: PublishRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_owned_project(db, current_user.id, project_id)
    suggestion = suggest_destination(db, project, current_user)
    if not suggestion.social_account_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=suggestion.reason)
    payload.social_account_id = suggestion.social_account_id
    payload.automation_mode = "auto"
    payload.platform = suggestion.recommended_platform
    job = _create_publish_job(db, current_user=current_user, project=project, payload=payload)
    db.commit()
    db.refresh(job)
    if job.status == "publish_queued":
        process_publish_job.delay(job.id)
    return to_publish_job_summary(job)


@router.post("/projects/{project_id}/publish-jobs", response_model=PublishJobSummary, status_code=status.HTTP_201_CREATED)
def create_publish_job_legacy(
    project_id: int,
    payload: PublishRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return create_publish_job(project_id, payload, current_user, db)


@router.get("/publish-jobs/{job_id}", response_model=PublishJobSummary)
def get_publish_job(job_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = (
        db.query(PublishJob)
        .join(Project, Project.id == PublishJob.project_id)
        .filter(PublishJob.id == job_id, Project.user_id == current_user.id)
        .one_or_none()
    )
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Publish job not found")
    return to_publish_job_summary(job)


@router.post("/publish-jobs/{job_id}/retry", response_model=PublishJobSummary)
def retry_publish_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = (
        db.query(PublishJob)
        .join(Project, Project.id == PublishJob.project_id)
        .filter(PublishJob.id == job_id, Project.user_id == current_user.id)
        .one_or_none()
    )
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Publish job not found")
    if job.status != "failed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only failed jobs can retry")
    job.status = "publish_queued"
    job.last_error = None
    project = db.get(Project, job.project_id)
    if project:
        project.status = "publish_queued"
    db.commit()
    process_publish_job.delay(job.id)
    return to_publish_job_summary(job)


@router.post("/publish-jobs/{job_id}/cancel", response_model=OkResponse)
def cancel_publish_job(job_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = (
        db.query(PublishJob)
        .join(Project, Project.id == PublishJob.project_id)
        .filter(PublishJob.id == job_id, Project.user_id == current_user.id)
        .one_or_none()
    )
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Publish job not found")
    if job.status != "scheduled":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only scheduled jobs can be canceled")
    job.status = "canceled"
    project = db.get(Project, job.project_id)
    if project:
        sync_project_state(project)
    db.commit()
    return OkResponse()
