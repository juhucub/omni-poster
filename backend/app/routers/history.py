from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import Project, PublishJob, PublishedPost, User
from app.routers.projects import get_owned_project
from app.routers.publish import to_publish_job_summary
from app.schemas import PublishHistoryResponse, PublishedPostSummary

router = APIRouter(tags=["history"])


def to_post_summary(post: PublishedPost) -> PublishedPostSummary:
    return PublishedPostSummary(
        id=post.id,
        project_id=post.project_id,
        publish_job_id=post.publish_job_id,
        platform=post.platform,
        external_post_id=post.external_post_id,
        external_url=post.external_url,
        published_at=post.published_at,
    )


@router.get("/projects/{project_id}/publish-history", response_model=PublishHistoryResponse)
def get_project_publish_history(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = get_owned_project(db, current_user.id, project_id)
    jobs = (
        db.query(PublishJob)
        .filter(PublishJob.project_id == project.id)
        .order_by(PublishJob.created_at.desc())
        .all()
    )
    posts = (
        db.query(PublishedPost)
        .filter(PublishedPost.project_id == project.id)
        .order_by(PublishedPost.published_at.desc())
        .all()
    )
    return PublishHistoryResponse(
        jobs=[to_publish_job_summary(job) for job in jobs],
        posts=[to_post_summary(post) for post in posts],
    )


@router.get("/publish-history", response_model=PublishHistoryResponse)
def get_all_publish_history(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    jobs = (
        db.query(PublishJob)
        .join(Project, Project.id == PublishJob.project_id)
        .filter(Project.user_id == current_user.id)
        .order_by(PublishJob.created_at.desc())
        .all()
    )
    posts = (
        db.query(PublishedPost)
        .join(Project, Project.id == PublishedPost.project_id)
        .filter(Project.user_id == current_user.id)
        .order_by(PublishedPost.published_at.desc())
        .all()
    )
    return PublishHistoryResponse(
        jobs=[to_publish_job_summary(job) for job in jobs],
        posts=[to_post_summary(post) for post in posts],
    )
