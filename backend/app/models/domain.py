import uuid
from datetime import datetime
from typing import Optional, List
from beanie import Document, Indexed
from pydantic import Field


class Domain(Document):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    user_id: uuid.UUID

    # Input & Normalization
    original_url: str
    normalized_url: str = Indexed(unique=True)
    domain: str = Indexed()

    # Domain Info
    ip_address: Optional[str] = None
    ssl_valid: Optional[bool] = None
    ssl_expires_at: Optional[datetime] = None
    server_header: Optional[str] = None

    # Robots.txt
    robots_txt_url: Optional[str] = None
    robots_txt_content: Optional[str] = None
    robots_txt_fetched_at: Optional[datetime] = None
    robots_disallow: bool = False

    # Status
    status: str = Indexed(default="pending")

    # Counts
    total_subdomains: int = 0
    total_sitemaps: int = 0
    total_urls: int = 0
    crawled_urls: int = 0

    # Timestamps
    first_crawl_at: Optional[datetime] = None
    last_crawl_at: Optional[datetime] = Indexed(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Metadata & Custom properties
    labels: List[str] = []
    notes: Optional[str] = None
    meta_data: dict = {}

    class Settings:
        name = "domains"
