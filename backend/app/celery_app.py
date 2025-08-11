from celery import Celery
from .core.config import settings

celery = Celery("crawler", broker=settings.REDIS_URL, backend=settings.REDIS_URL)
celery.conf.task_routes = {"app.tasks.*": {"queue": "crawl"}}
celery.conf.worker_max_tasks_per_child = 100
