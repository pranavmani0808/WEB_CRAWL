import uuid
from datetime import datetime
from typing import Optional
from beanie import Document, Indexed
from pydantic import Field


class CrawlComparison(Document):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    domain_id: uuid.UUID = Indexed()

    # Crawls being compared
    previous_crawl_job_id: Optional[uuid.UUID] = None
    current_crawl_job_id: uuid.UUID

    # Changes
    urls_added: int = 0
    urls_removed: int = 0
    new_broken_urls: int = 0
    fixed_broken_urls: int = 0
    new_redirects: int = 0
    removed_redirects: int = 0

    # Health change
    health_score_change: int = 0  # difference in health score

    # Timestamps
    compared_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "crawl_comparison"
