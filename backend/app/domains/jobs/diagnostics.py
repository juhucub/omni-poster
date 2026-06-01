from __future__ import annotations

from datetime import datetime

from app.domains.jobs.statuses import STALE_GENERATION_MINUTES


def job_age_seconds(started_at: datetime | None) -> float | None:
    if started_at is None:
        return None
    return (datetime.utcnow() - started_at).total_seconds()


def is_job_stale(
    started_at: datetime | None,
    finished_at: datetime | None,
    *,
    older_than_minutes: int = STALE_GENERATION_MINUTES,
) -> bool:
    if started_at is None or finished_at is not None:
        return False
    age = job_age_seconds(started_at)
    return age is not None and age >= older_than_minutes * 60
