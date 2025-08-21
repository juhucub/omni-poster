from celery import Celery
from celery.schedules import crontab

"""
Purpose: Central Celery application config that defines the celery app, broker/result backends, routing, 
         worker lifecycle settings, and periodic schedules (Celery Beat) that enqueue crawl jobs by
         creator tier (T0, T1, T2).

Interactions: 
    * Uses Redis as the Celery broker and result backend
    * Dispatches tasks to the "crawl" queue and calls task functions under app.tasks.*
        - mainly app.tasks.scheduler.enqueue_tier which fan out crawl jobs to service-specific workers
    *Consumed by worker processes started bia 'celery -A app.celery_app.celery worker ...' and scheduler
    via 'celery -A app.celery_app.celery beat ...'

Easy Remember Chart FIXME:
    - Security: In production, the Redis URLs should be provided via environment variables and 
    secured with auth and TLS (e.g., rediss://). Avoid embedding secrets in source code.
    - Reliability: Consider setting time limits, acks_late, retry policies, and idempotency keys 
    in task modules to handle worker crashes and duplicate deliveries.
    - Performance: Use isolated queues per concern (e.g., "crawl", "video", "webhook"), tune 
    prefetch (worker_prefetch_multiplier), and worker_max_tasks_per_child to mitigate leaks.
    - Scheduling: Celery Beat runs on a single node; ensure only one beat is active or use a 
    distributed scheduler/leader election to avoid duplicate enqueues. Cron uses server time 
    (ideally UTC); align with external API quotas and local compliance windows.
    - Observability: Expose metrics (Prometheus) and use Flower or equivalent for monitoring 
    queue depths, task throughput, and failures
"""
celery = Celery("crawler")

# Global Celery configuration
# - broker_url: Message broker for task queues (Redis in dev)
# - result_backend: Where task metadata/results are stored (Redis in dev)
# - task_routes: Route all tasks matching "app.tasks.*" to the "crawl" queue
# - worker_max_tasks_per_child: Recycle worker processes after N tasks to avoid memory leaks
# - beat_schedule: Periodic tasks (cron-like) that enqueue crawl jobs by tier
# NOTE: For prod, prefer environment-driven config (e.g., CELERY_BROKER_URL, CELERY_RESULT_BACKEND)
celery.conf.update(
    broker_url="redis://localhost:6379/0",  # DEV ONLY; use env + TLS (rediss://) + auth in prod
    result_backend="redis://localhost:6379/0",  # DEV ONLY; separate backend/DB recommended in prod
    task_routes={"app.tasks.*": {"queue": "crawl"}},  # Route all app tasks to a dedicated "crawl" queue
    worker_max_tasks_per_child=200,  # Recycle workers periodically (mitigates mem fragmentation/leaks)
    beat_schedule={
        # Periodic schedule: enqueue Tier-0 (highest priority) creators every 2 hours on the hour.
        # Calls app.tasks.scheduler.enqueue_tier("T0"), which should:
        # - Determine which creators belong to T0
        # - Enqueue per-platform fetch tasks (YouTube/TikTok/Instagram) respecting quotas/rate limits
        # - Maintain idempotency so repeated schedules don't duplicate work
        "enqueue-t0": {
            "task": "app.tasks.scheduler.enqueue_tier",
            "schedule": crontab(minute=0, hour="*/2"),  # Every 2 hours at :00
            "args": ["T0"],
        },
        # Periodic schedule: enqueue Tier-1 creators every 6 hours on the hour.
        # Useful for medium-priority accounts with lower freshness needs or stricter API quotas.
        "enqueue-t1": {
            "task": "app.tasks.scheduler.enqueue_tier",
            "schedule": crontab(minute=0, hour="*/6"),  # Every 6 hours at :00
            "args": ["T1"],
        },
        # Periodic schedule: enqueue Tier-2 creators daily at 03:15.
        # Off-peak timing can help avoid API rate contention and align with daily quotas.
        "enqueue-t2": {
            "task": "app.tasks.scheduler.enqueue_tier",
            "schedule": crontab(minute=15, hour="3"),  # Daily at 03:15
            "args": ["T2"],
        },
    },
)


# Additional recommended (but optional) settings to consider (set in env/config module):
# - timezone="UTC" and enable_utc=True to standardize schedules across environments
# - task_acks_late=True and worker_prefetch_multiplier=1 for fair dispatch under long-running tasks
# - task_time_limit / task_soft_time_limit to prevent runaway jobs
# - broker_transport_options={"visibility_timeout": ...} when using Redis as broker for long tasks
# - result_expires to bound backend storage growth