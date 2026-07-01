import uuid
from datetime import datetime
from typing import Optional
from beanie import Document, Indexed
from pydantic import Field


class CrawlStatistics(Document):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    domain_id: uuid.UUID = Indexed(unique=True)
    crawl_job_id: Optional[uuid.UUID] = None

    # Counts
    total_urls: int = 0
    successful_urls: int = 0
    redirects: int = 0
    client_errors_4xx: int = 0
    server_errors_5xx: int = 0
    timeouts: int = 0
    dns_errors: int = 0
    ssl_errors: int = 0
    network_errors: int = 0

    # Performance
    avg_response_time_ms: Optional[int] = None
    min_response_time_ms: Optional[int] = None
    max_response_time_ms: Optional[int] = None
    p95_response_time_ms: Optional[int] = None
    p99_response_time_ms: Optional[int] = None

    # Health
    health_score: Optional[int] = Indexed(default=None)
    broken_links_count: int = 0
    redirect_chains_count: int = 0

    # Content Types
    html_urls: int = 0
    css_urls: int = 0
    js_urls: int = 0
    json_urls: int = 0
    xml_urls: int = 0
    image_urls: int = 0
    pdf_urls: int = 0
    video_urls: int = 0
    other_urls: int = 0

    # Timing
    crawl_start_time: Optional[datetime] = None
    crawl_end_time: Optional[datetime] = None
    crawl_duration_minutes: Optional[int] = None

    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "crawl_statistics"
