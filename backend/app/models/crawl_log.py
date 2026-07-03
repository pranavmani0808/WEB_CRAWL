import uuid
from datetime import datetime
from typing import Optional
from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel


class CrawlLog(Document):
    crawl_job_id: uuid.UUID

    # Log Entry
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    level: str  # info, warning, error
    message: str

    # Context
    event_type: Optional[str] = None  # robots_found, sitemap_discovered, etc.
    entity_type: Optional[str] = None  # url, sitemap, domain, worker
    entity_id: Optional[str] = None

    # Details
    details: dict = {}

    class Settings:
        name = "crawl_logs"
        indexes = [
            # crawl_logs grows unboundedly across all jobs, and the job
            # detail endpoint filters on crawl_job_id on every UI poll -
            # without this index each poll was a full collection scan.
            IndexModel([("crawl_job_id", ASCENDING), ("timestamp", DESCENDING)]),
        ]
