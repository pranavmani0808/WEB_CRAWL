import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import ForeignKey, String, Boolean, DateTime, Integer, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base

class CrawlJob(Base):
    __tablename__ = "crawl_jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    domain_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domains.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Job Status
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True)
    
    # Pipeline Stages (for timeline UI)
    stage_domain_validation: Mapped[bool] = mapped_column(Boolean, default=False)
    stage_dns_resolution: Mapped[bool] = mapped_column(Boolean, default=False)
    stage_ssl_verification: Mapped[bool] = mapped_column(Boolean, default=False)
    stage_robots_found: Mapped[bool] = mapped_column(Boolean, default=False)
    stage_sitemap_discovery: Mapped[bool] = mapped_column(Boolean, default=False)
    stage_parsing_indexes: Mapped[bool] = mapped_column(Boolean, default=False)
    stage_parsing_sitemaps: Mapped[bool] = mapped_column(Boolean, default=False)
    stage_url_discovery: Mapped[bool] = mapped_column(Boolean, default=False)
    stage_http_checking: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Configuration
    max_workers: Mapped[int] = mapped_column(Integer, default=32)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30)
    respect_robots_txt: Mapped[bool] = mapped_column(Boolean, default=True)
    follow_redirects: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Progress (denormalized)
    total_sitemaps_found: Mapped[int] = mapped_column(Integer, default=0)
    total_sitemaps_parsed: Mapped[int] = mapped_column(Integer, default=0)
    total_urls_found: Mapped[int] = mapped_column(Integer, default=0)
    total_urls_checked: Mapped[int] = mapped_column(Integer, default=0)
    
    # Results (denormalized)
    urls_2xx: Mapped[int] = mapped_column(Integer, default=0)
    urls_3xx: Mapped[int] = mapped_column(Integer, default=0)
    urls_4xx: Mapped[int] = mapped_column(Integer, default=0)
    urls_5xx: Mapped[int] = mapped_column(Integer, default=0)
    urls_timeout: Mapped[int] = mapped_column(Integer, default=0)
    urls_dns_error: Mapped[int] = mapped_column(Integer, default=0)
    urls_ssl_error: Mapped[int] = mapped_column(Integer, default=0)
    
    # Performance
    avg_response_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    crawl_speed_urls_per_sec: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    
    # Timing
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Avoid conflict with SQLAlchemy's metadata attribute
    meta_data: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)

    # Relationships
    domain = relationship("Domain", back_populates="crawl_jobs")
    user = relationship("User", back_populates="crawl_jobs")
    logs = relationship("CrawlLog", back_populates="crawl_job", cascade="all, delete-orphan")
    statistics = relationship("CrawlStatistics", back_populates="crawl_job")
    reports = relationship("Report", back_populates="crawl_job")
    crawl_history = relationship("CrawlHistory", back_populates="crawl_job")
    exports = relationship("Export", back_populates="crawl_job")
