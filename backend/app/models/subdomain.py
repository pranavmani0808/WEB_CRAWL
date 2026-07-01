import uuid
from datetime import datetime
from typing import Optional
from beanie import Document, Indexed
from pydantic import Field


class Subdomain(Document):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    domain_id: uuid.UUID

    # Subdomain Info
    subdomain: str = Indexed()
    normalized_url: str = Indexed(unique=True)

    # Status
    status: str = Indexed(default="pending")

    # Counts
    total_sitemaps: int = 0
    total_urls: int = 0
    crawled_urls: int = 0

    # Health
    health_score: int = 100
    crawled_at: Optional[datetime] = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "subdomains"
