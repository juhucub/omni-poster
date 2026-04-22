from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.celery_app import celery
from app.db import SessionLocal
from app.models import PublishJob
from app.tasks.publish import process_publish_job


@celery.task(name="app.tasks.scheduler.dispatch_due_publish_jobs")
def dispatch_due_publish_jobs(limit: int = 100) -> dict:
    db: Session = SessionLocal()
    now = datetime.utcnow()
    try:
        jobs = (
            db.query(PublishJob)
            .filter(
                PublishJob.status == "scheduled",
                PublishJob.scheduled_for.is_not(None),
                PublishJob.scheduled_for <= now,
            )
            .order_by(PublishJob.scheduled_for.asc())
            .limit(limit)
            .all()
        )

        dispatched = 0
        for job in jobs:
            job.status = "queued"
            dispatched += 1
        db.commit()

        for job in jobs:
            process_publish_job.delay(job.id)

        return {"dispatched": dispatched}
    finally:
        db.close()
