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
        "app.tasks.publish.process_publish_job": {"queue": "publish"},
        "app.tasks.scheduler.dispatch_due_publish_jobs": {"queue": "publish"},
    },
    worker_max_tasks_per_child=200,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    enable_utc=True,
    timezone="UTC",
    beat_schedule={
        "dispatch-due-publish-jobs": {
            "task": "app.tasks.scheduler.dispatch_due_publish_jobs",
            "schedule": crontab(minute="*"),
        }
    },
)
