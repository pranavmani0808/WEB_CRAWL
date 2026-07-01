import uuid
from datetime import datetime, date
from typing import Optional, List
from beanie import Document, Indexed
from pydantic import Field


class URL(Document):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    domain_id: uuid.UUID
    subdomain_id: Optional[uuid.UUID] = None
    sitemap_id: uuid.UUID

    # URL Info
    url: str
    url_hash: str = Indexed(unique=True)

    # Sitemap Data
    sitemap_last_modified: Optional[date] = None
    sitemap_change_frequency: Optional[str] = None
    sitemap_priority: Optional[float] = None

    # HTTP Status
    status_code: Optional[int] = Indexed(default=None)
    status_category: Optional[str] = Indexed(default=None)

    # Redirect Tracking
    final_url: Optional[str] = None
    redirect_chain: List[str] = []

    # Response Details
    response_time_ms: Optional[int] = Indexed(default=None)
    content_type: Optional[str] = None
    content_length: Optional[int] = None

    # SEO/Content
    canonical_url: Optional[str] = None
    robots_meta: Optional[str] = None
    is_indexable: Optional[bool] = None

    # Crawl Status
    crawl_status: str = Indexed(default="pending")
    crawl_attempt: int = 0

    # Timestamps
    discovered_at: datetime = Field(default_factory=datetime.utcnow)
    last_checked_at: Optional[datetime] = Indexed(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Error Details
    error_details: Optional[str] = None

    # Metadata
    meta_data: dict = {}

    class Settings:
        name = "urls"
