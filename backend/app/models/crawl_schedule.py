import uuid
from datetime import datetime
from typing import Optional
from beanie import Document
from pydantic import Field
from pymongo import IndexModel, ASCENDING


class CrawlSchedule(Document):
    """A recurring audit: Celery Beat re-crawls the domain on this cadence.

    One schedule per (user, domain) - creating again just updates the
    frequency. The Beat dispatcher (app.workers.tasks.dispatch_due_schedules)
    picks up schedules whose next_run_at has passed, starts a normal crawl
    job for them, and advances next_run_at by the frequency interval.
    """
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    domain_id: uuid.UUID
    user_id: uuid.UUID

    frequency: str  # hourly | daily | weekly
    enabled: bool = True

    next_run_at: datetime
    last_run_at: Optional[datetime] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "crawl_schedules"
        indexes = [
            IndexModel([("next_run_at", ASCENDING)]),
            IndexModel([("user_id", ASCENDING)]),
            IndexModel([("domain_id", ASCENDING), ("user_id", ASCENDING)], unique=True),
        ]
