from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery = Celery(
    "omniposter",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.workers.generation",
        "app.workers.publish",
        "app.workers.scheduler",
        "app.workers.voice_preview",
        "app.workers.voice_operations",
    ],
)

celery.conf.update(
    task_default_queue="default",
    # NOTE: include= lists app.workers.* modules (where task implementations live), but the
    # name= strings on @celery.task decorators intentionally retain the original app.tasks.*
    # namespace for wire-protocol backward compatibility — any tasks already in production
    # queues reference the old names.  task_routes, task_annotations, and beat_schedule all
    # use the registered task name strings, not module paths.
    task_routes={
        "app.tasks.generation.process_generation_job": {"queue": "generation"},
        "app.tasks.generation.reconcile_stale_generation_jobs": {"queue": "generation"},
        "app.tasks.publish.process_publish_job": {"queue": "publish"},
        "app.tasks.scheduler.dispatch_due_publish_jobs": {"queue": "publish"},
        "app.tasks.voice_preview.process_voice_lab_preview": {"queue": "voice_preview"},
        "app.tasks.voice_preview.reconcile_stale_voice_preview_jobs": {"queue": "voice_preview"},
        "app.tasks.voice_operations.process_voice_operation_job": {"queue": "voice_preview"},
        "app.tasks.voice_operations.process_voice_calibration_batch": {"queue": "voice_preview"},
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
        "app.tasks.generation.process_generation_job": {
            "soft_time_limit": settings.CELERY_GENERATION_TASK_SOFT_TIME_LIMIT_SECONDS,
            "time_limit": settings.CELERY_GENERATION_TASK_HARD_TIME_LIMIT_SECONDS,
        },
        "app.tasks.voice_preview.process_voice_lab_preview": {
            "soft_time_limit": 240,
            "time_limit": 300,
            "acks_late": False,
            "reject_on_worker_lost": False,
        },
        "app.tasks.voice_operations.process_voice_operation_job": {
            "soft_time_limit": 840,
            "time_limit": 900,
            "acks_late": False,
            "reject_on_worker_lost": False,
        },
        "app.tasks.voice_operations.process_voice_calibration_batch": {
            "soft_time_limit": 840,
            "time_limit": 900,
            "acks_late": False,
            "reject_on_worker_lost": False,
        },
    },
    beat_schedule={
        "reconcile-stale-generation-jobs": {
            "task": "app.tasks.generation.reconcile_stale_generation_jobs",
            "schedule": crontab(minute="*"),
        },
        "reconcile-stale-voice-preview-jobs": {
            "task": "app.tasks.voice_preview.reconcile_stale_voice_preview_jobs",
            "schedule": crontab(minute="*"),
        },
        "dispatch-due-publish-jobs": {
            "task": "app.tasks.scheduler.dispatch_due_publish_jobs",
            "schedule": crontab(minute="*"),
        }
    },
)
