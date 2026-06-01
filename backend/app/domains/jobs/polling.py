from __future__ import annotations

from sqlalchemy.orm import Session

from app.domains.jobs.statuses import ACTIVE_GENERATION_STATUSES
from app.models import GenerationJob


def find_active_generation_job(db: Session, project_id: int, output_kind: str) -> GenerationJob | None:
    return (
        db.query(GenerationJob)
        .filter(
            GenerationJob.project_id == project_id,
            GenerationJob.output_kind == output_kind,
            GenerationJob.status.in_(tuple(ACTIVE_GENERATION_STATUSES)),
        )
        .order_by(GenerationJob.created_at.desc())
        .first()
    )


def find_latest_generation_job(db: Session, project_id: int) -> GenerationJob | None:
    return (
        db.query(GenerationJob)
        .filter(GenerationJob.project_id == project_id)
        .order_by(GenerationJob.created_at.desc())
        .first()
    )


def find_latest_active_generation_job(db: Session, project_id: int) -> GenerationJob | None:
    return (
        db.query(GenerationJob)
        .filter(
            GenerationJob.project_id == project_id,
            GenerationJob.status.in_(tuple(ACTIVE_GENERATION_STATUSES)),
        )
        .order_by(GenerationJob.created_at.desc())
        .first()
    )
