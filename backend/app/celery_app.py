from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery = Celery(
    "omniposter",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.generation",
        "app.tasks.publish",
        "app.tasks.scheduler",
    ],
)

celery.conf.update(
    task_default_queue="default",
    task_routes={
        "app.tasks.generation.process_generation_job": {"queue": "generation"},
        "app.tasks.generation.reconcile_stale_generation_jobs": {"queue": "generation"},
        "app.tasks.publish.process_publish_job": {"queue": "publish"},
        "app.tasks.scheduler.dispatch_due_publish_jobs": {"queue": "publish"},
    },
    worker_max_tasks_per_child=200,
    task_acks_late=True,
    task_track_started=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    worker_prefetch_multiplier=1,
    enable_utc=True,
    timezone="UTC",
    task_annotations={
        "app.tasks.generation.process_generation_job": {"soft_time_limit": 840, "time_limit": 900},
    },
    beat_schedule={
        "reconcile-stale-generation-jobs": {
            "task": "app.tasks.generation.reconcile_stale_generation_jobs",
            "schedule": crontab(minute="*"),
        },
        "dispatch-due-publish-jobs": {
            "task": "app.tasks.scheduler.dispatch_due_publish_jobs",
            "schedule": crontab(minute="*"),
        }
    },
)
