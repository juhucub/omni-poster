from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.domains.publishing.history import to_post_summary
from app.models import Project, PublishJob, PublishedPost, User
from app.api.projects import get_owned_project
from app.schemas import PublishHistoryResponse
from app.services.project_state import to_publish_job_summary

router = APIRouter(tags=["history"])


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
