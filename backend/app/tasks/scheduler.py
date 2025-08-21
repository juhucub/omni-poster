from ..celery_app import celery
from sqlalchemy.orm import Session
from ..db import SessionLocal
from ..models import Creator
from .crawl import crawl_creator_task

TIER_LIMITS = {"T0": 20, "T1": 10, "T2": 5}


# Celery entrypoint used by Celery Beat (see celery_app.py) to enqueue crawl jobs by tier.
# Inputs:
#   - tier (str): One of "T0", "T1", "T2" (or future tiers). Determines freshness/limits.
# Returns:
#   - Dict[str, Any]: {"enqueued": <count>, "tier": <tier>} for lightweight monitoring.
# Side effects:
#   - Reads from the DB to select creators; enqueues a Celery task per selected creator.
#   - No writes to the DB here; downstream crawl task performs upserts/snapshots.
# Depends on:
#   - SessionLocal for DB connection.
#   - Creator model with `platform`, `external_id`, optional `tier`, and `handle` fields.
#   - `crawl_creator_task` to execute the actual crawling work.
@celery.task(name="app.tasks.scheduler.enqueue_tier")
def enqueue_tier(tier: str):
    db: Session = SessionLocal()
    try:
        #select creators w a non-null handle 
        creators = db.query(Creator).filter(Creator.handle != None).all()
        # TODO: add a real tier column; for now, naive filter by name/tag
        selected = [c for c in creators if getattr(c, "tier", "T2") == tier]

        #ddetermine hgow many recent videos to request per creator for this tier
        limit = TIER_LIMITS.get(tier, 5)
        for c in selected:
            crawl_creator_task.apply_async(kwargs={
                "platform": c.platform,
                "creator_external_id": c.external_id,
                "latest_n": limit,
                "include_comments": False,
            }, priority=5       #FIXME: Map priority to tier (T0=10, T1=5, T2=1)
            )

        return {"enqueued": len(selected), "tier": tier}
    finally:
        db.close()
