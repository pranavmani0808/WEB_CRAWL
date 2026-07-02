import uuid
from datetime import datetime
from typing import Optional
from beanie import Document
from pydantic import Field
from pymongo import IndexModel, ASCENDING


class Subdomain(Document):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    domain_id: uuid.UUID

    # Subdomain Info
    subdomain: str
    normalized_url: str

    # Status
    status: str = "pending"

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
        indexes = [
            IndexModel([("normalized_url", ASCENDING)], unique=True),
            IndexModel([("subdomain", ASCENDING)]),
            IndexModel([("status", ASCENDING)]),
        ]
