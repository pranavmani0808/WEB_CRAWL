import uuid
from datetime import datetime
from typing import Optional, Annotated
from beanie import Document, Indexed
from pydantic import Field


class CrawlLog(Document):
    crawl_job_id: Annotated[uuid.UUID, Indexed()]

    # Log Entry
    timestamp: Indexed(datetime) = Field(default_factory=datetime.utcnow)
    level: str  # info, warning, error
    message: str

    # Context
    event_type: Annotated[Optional[str], Indexed()] = None  # robots_found, sitemap_discovered, etc.
    entity_type: Optional[str] = None  # url, sitemap, domain, worker
    entity_id: Optional[str] = None

    # Details
    details: dict = {}

    class Settings:
        name = "crawl_logs"
