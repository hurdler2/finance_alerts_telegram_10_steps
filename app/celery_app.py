from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "finance_alerts",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.ingest",
        "app.tasks.process",
        "app.tasks.notify",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Queue routing
    task_routes={
        "app.tasks.ingest.*": {"queue": "ingest"},
        "app.tasks.notify.*": {"queue": "notify"},
        "app.tasks.process.*": {"queue": "default"},
    },
    # Beat schedule
    beat_schedule={
        "fetch-all-sources": {
            "task": "app.tasks.ingest.fetch_all_sources",
            "schedule": 300.0,  # every 5 minutes
        },
        "retry-failed-deliveries": {
            "task": "app.tasks.notify.retry_failed_deliveries",
            "schedule": 600.0,  # every 10 minutes
        },
        "cleanup-old-articles": {
            "task": "app.tasks.process.cleanup_old_articles",
            "schedule": crontab(hour=3, minute=0),  # daily 03:00 UTC
        },
    },
)
