from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "web_crawl_workers",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_config = {
    "task_track_started": True,
    "task_serializer": "json",
    "result_serializer": "json",
    "accept_content": ["json"],
    "timezone": "UTC",
    "enable_utc": True,
}

# Enable SSL/TLS for Upstash Redis (rediss:// protocol)
if settings.CELERY_BROKER_URL.startswith("rediss://"):
    celery_config.update({
        "broker_connection_retry_on_startup": True,
        "redis_backend_use_ssl": {
            "ssl_cert_reqs": "required",
            "ssl_ca_certs": None,
        },
    })

celery_app.conf.update(celery_config)

# Recurring-audit dispatcher, run by the beat service. Checks every ~5
# minutes for CrawlSchedules whose next_run_at has passed - the schedule
# granularity is hourly at the finest, so this cadence is plenty.
celery_app.conf.beat_schedule = {
    "dispatch-due-crawl-schedules": {
        "task": "app.workers.tasks.dispatch_due_schedules",
        "schedule": 300.0,
    },
    # Fail jobs whose worker died without marking them (OOM kill, restart) -
    # see reap_stale_jobs. Offset from the dispatcher so the two Beat tasks
    # don't always hit the DB at the same instant.
    "reap-stale-crawl-jobs": {
        "task": "app.workers.tasks.reap_stale_jobs",
        "schedule": 290.0,
    },
}

# Discover tasks from app.workers.tasks
celery_app.autodiscover_tasks(["app.workers"])
