from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from ..tasks.crawl import crawl_creator_task
from ..dependencies import get_current_user  # reuse your auth
import redis

router = APIRouter(prefix="/crawl", tags=["crawl"])

class EnqueueBody(BaseModel):
    platform: str = Field(pattern="^(youtube|instagram|tiktok)$")
    creator_external_id: str
    latest_n: int = 20
    include_comments: bool = False
    priority: int = 5

@router.post("/enqueue")
def enqueue(body: EnqueueBody, user=Depends(get_current_user)):
    task = crawl_creator_task.apply_async(kwargs=body.model_dump(), priority=body.priority)
    return {"task_id": task.id, "status": "queued"}

@router.get("/status/{task_id}")
def status(task_id: str, user=Depends(get_current_user)):
    from ..celery_app import celery
    a = celery.AsyncResult(task_id)
    return {"task_id": task_id, "state": a.state, "info": a.info if isinstance(a.info, dict) else str(a.info)}

@router.get("/ops/metrics")
def ops_metrics(user=Depends(get_current_user)):
    r = redis.Redis.from_url("redis://localhost:6379/0", decode_responses=True)
    # Minimal metrics
    buckets = {
        "yt_units": r.hgetall("yt:units") or {},
        "ig_requests": r.hgetall("ig:req") or {},
        "tt_requests": r.hgetall("tt:req") or {},
    }
    # Queue depth (Celery Redis keys vary by config; this is illustrative)
    depth = r.llen("celery")
    return {"queue_depth": depth, "buckets": buckets}
