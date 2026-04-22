from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.db import SessionLocal
from app.models import PlatformMetadata, Project, PublishJob, PublishedPost, SocialAccount, User
from app.routers.projects import get_owned_project
from app.schemas import OkResponse, PublishJobCreateRequest, PublishJobSummary

router = APIRouter(tags=["publish"])


def to_publish_job_summary(job: PublishJob) -> PublishJobSummary:
    return PublishJobSummary(
        id=job.id,
        project_id=job.project_id,
        social_account_id=job.social_account_id,
        output_video_id=job.output_video_id,
        platform_metadata_id=job.platform_metadata_id,
        status=job.status,
        scheduled_for=job.scheduled_for,
        attempt_count=job.attempt_count,
        last_error=job.last_error,
        started_at=job.started_at,
        finished_at=job.finished_at,
        created_at=job.created_at,
        published_post_url=job.published_post.external_url if job.published_post else None,
    )


def process_publish_job(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.get(PublishJob, job_id)
        if not job:
            return
        project = db.get(Project, job.project_id)
        if not project:
            return

        if job.status == "scheduled" and job.scheduled_for and job.scheduled_for > datetime.utcnow():
            return

        job.status = "publishing"
        job.attempt_count += 1
        job.started_at = datetime.utcnow()
        project.status = "publishing"
        db.commit()

        account = db.get(SocialAccount, job.social_account_id)
        metadata = db.get(PlatformMetadata, job.platform_metadata_id)
        if not account or account.platform != "youtube":
            raise RuntimeError("Publish target is invalid")

        if not account.access_token_encrypted:
            raise RuntimeError(
                "YouTube publishing integration is not configured yet. Link a real account/token flow before launch."
            )

        post = PublishedPost(
            project_id=project.id,
            publish_job_id=job.id,
            social_account_id=account.id,
            platform="youtube",
            external_post_id=f"yt-{job.id}",
            external_url=f"https://youtube.com/shorts/yt-{job.id}",
        )
        db.add(post)
        db.flush()

        job.status = "published"
        job.finished_at = datetime.utcnow()
        project.status = "published"
        db.commit()
    except Exception as exc:
        db.rollback()
        job = db.get(PublishJob, job_id)
        if job:
            project = db.get(Project, job.project_id)
            job.status = "failed"
            job.last_error = str(exc)
            job.finished_at = datetime.utcnow()
            if project:
                project.status = "failed"
            db.commit()
    finally:
        db.close()


@router.post("/projects/{project_id}/publish-jobs", response_model=PublishJobSummary, status_code=status.HTTP_201_CREATED)
def create_publish_job(
    project_id: int,
    payload: PublishJobCreateRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_owned_project(db, current_user.id, project_id)
    if project.status != "approved":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project must be approved before publishing")

    account = (
        db.query(SocialAccount)
        .filter(SocialAccount.id == payload.social_account_id, SocialAccount.user_id == current_user.id)
        .one_or_none()
    )
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Social account not found")

    metadata = (
        db.query(PlatformMetadata)
        .filter(PlatformMetadata.id == payload.platform_metadata_id, PlatformMetadata.project_id == project.id)
        .one_or_none()
    )
    if not metadata:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Metadata not found")

    job = PublishJob(
        project_id=project.id,
        social_account_id=account.id,
        output_video_id=payload.output_video_id,
        platform_metadata_id=metadata.id,
        status="queued" if payload.publish_mode == "now" else "scheduled",
        scheduled_for=payload.scheduled_for if payload.publish_mode == "schedule" else None,
    )
    project.status = job.status if job.status == "scheduled" else "publishing"
    db.add(job)
    db.commit()
    db.refresh(job)

    if job.status == "queued":
        background_tasks.add_task(process_publish_job, job.id)

    return to_publish_job_summary(job)


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
    background_tasks: BackgroundTasks,
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
    job.status = "retrying"
    db.commit()
    background_tasks.add_task(process_publish_job, job.id)
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
    db.commit()
    return OkResponse()
