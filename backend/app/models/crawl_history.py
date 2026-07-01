import uuid
from datetime import datetime
from beanie import Document, Indexed
from pydantic import Field


class CrawlHistory(Document):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    domain_id: uuid.UUID = Indexed()
    crawl_job_id: uuid.UUID

    # Metrics snapshot
    total_urls: int = 0
    successful_urls: int = 0
    broken_urls: int = 0
    redirects: int = 0
    avg_response_time_ms: int = 0
    health_score: int = 0

    # Timing
    crawled_at: datetime = Indexed(default_factory=datetime.utcnow)

    class Settings:
        name = "crawl_history"
