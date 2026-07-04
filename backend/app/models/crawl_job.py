import uuid
from datetime import datetime
from typing import Optional
from beanie import Document
from pydantic import Field


class CrawlJob(Document):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    domain_id: uuid.UUID
    user_id: uuid.UUID

    # Job Status
    status: str = "pending"

    # Pipeline Stages (for timeline UI)
    stage_domain_validation: bool = False
    stage_dns_resolution: bool = False
    stage_ssl_verification: bool = False
    stage_robots_found: bool = False
    stage_sitemap_discovery: bool = False
    stage_parsing_indexes: bool = False
    stage_parsing_sitemaps: bool = False
    stage_url_discovery: bool = False
    stage_http_checking: bool = False

    # Configuration
    max_workers: int = 32
    timeout_seconds: int = 30
    respect_robots_txt: bool = True
    follow_redirects: bool = True

    # Progress (denormalized)
    total_sitemaps_found: int = 0
    total_sitemaps_parsed: int = 0
    total_urls_found: int = 0
    total_urls_checked: int = 0

    # Results (denormalized)
    urls_2xx: int = 0
    urls_3xx: int = 0
    urls_4xx: int = 0
    urls_5xx: int = 0
    urls_timeout: int = 0
    urls_dns_error: int = 0
    urls_ssl_error: int = 0

    # Performance
    avg_response_time_ms: Optional[int] = None
    crawl_speed_urls_per_sec: Optional[float] = None

    # Timing
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    # Heartbeat, refreshed by the engine as the crawl progresses. The Beat
    # reaper fails any running job whose heartbeat goes silent - a worker
    # killed mid-crawl (e.g. OOM SIGKILL) can't mark its own job failed.
    last_activity_at: Optional[datetime] = None

    # Metadata
    meta_data: dict = {}

    class Settings:
        name = "crawl_jobs"
