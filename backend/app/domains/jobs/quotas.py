from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import settings
from app.domains.jobs.statuses import ACTIVE_GENERATION_STATUSES
from app.models import GenerationJob, Project


def check_generation_queue_limits(db: Session, user_id: int) -> str | None:
    """Return a violation message if any queue limit is exceeded, None if within limits."""
    active_statuses = tuple(ACTIVE_GENERATION_STATUSES)

    max_user_active = int(settings.MAX_ACTIVE_GENERATION_JOBS_PER_USER or 0)
    if max_user_active > 0:
        user_active = (
            db.query(GenerationJob)
            .join(Project, Project.id == GenerationJob.project_id)
            .filter(Project.user_id == user_id, GenerationJob.status.in_(active_statuses))
            .count()
        )
        if user_active >= max_user_active:
            return "Too many active render jobs for this user. Wait for one to finish before starting another."

    max_total_active = int(settings.MAX_ACTIVE_GENERATION_JOBS_TOTAL or 0)
    if max_total_active > 0:
        total_active = db.query(GenerationJob).filter(GenerationJob.status.in_(active_statuses)).count()
        if total_active >= max_total_active:
            return "Render capacity is full. Try again after queued jobs advance."

    max_total_queued = int(settings.MAX_QUEUED_GENERATION_JOBS_TOTAL or 0)
    if max_total_queued > 0:
        total_queued = db.query(GenerationJob).filter(GenerationJob.status == "queued").count()
        if total_queued >= max_total_queued:
            return "Render queue is full. Try again after queued jobs advance."

    return None
