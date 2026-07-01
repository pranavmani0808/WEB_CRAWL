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

# Discover tasks from app.workers.tasks
celery_app.autodiscover_tasks(["app.workers"])
