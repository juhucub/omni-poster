from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.domains.jobs.statuses import STALE_GENERATION_ERROR, STALE_GENERATION_MINUTES
from app.models import GenerationJob, Project
from app.services.project_state import sync_project_state

logger = logging.getLogger(__name__)


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
