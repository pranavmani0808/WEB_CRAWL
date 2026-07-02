import uuid
from datetime import datetime, date
from typing import Optional
from beanie import Document
from pydantic import Field
from pymongo import IndexModel, ASCENDING


class Sitemap(Document):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    domain_id: uuid.UUID
    subdomain_id: Optional[uuid.UUID] = None

    # Sitemap Details
    sitemap_url: str

    # Type & Hierarchy
    is_index: bool = False
    parent_sitemap_id: Optional[uuid.UUID] = None

    # Discovery Source
    discovered_from: Optional[str] = None

    # Status
    status: str = "pending"

    # Content
    url_count: int = 0
    last_modified: Optional[date] = None
    response_code: Optional[int] = None

    # Timing
    fetched_at: Optional[datetime] = None
    parsed_at: Optional[datetime] = None
    fetch_time_ms: Optional[int] = None

    # Error Handling
    error_message: Optional[str] = None
    retry_count: int = 0

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Metadata
    meta_data: dict = {}

    class Settings:
        name = "sitemaps"
        indexes = [
            IndexModel([("sitemap_url", ASCENDING)], unique=True),
            IndexModel([("status", ASCENDING)]),
        ]
