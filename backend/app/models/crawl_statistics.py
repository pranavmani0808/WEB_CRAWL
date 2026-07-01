import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import ForeignKey, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base

class CrawlStatistics(Base):
    __tablename__ = "crawl_statistics"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    domain_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domains.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    crawl_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("crawl_jobs.id", ondelete="SET NULL"), nullable=True)
    
    # Counts
    total_urls: Mapped[int] = mapped_column(Integer, default=0)
    successful_urls: Mapped[int] = mapped_column(Integer, default=0)
    redirects: Mapped[int] = mapped_column(Integer, default=0)
    client_errors_4xx: Mapped[int] = mapped_column(Integer, default=0)
    server_errors_5xx: Mapped[int] = mapped_column(Integer, default=0)
    timeouts: Mapped[int] = mapped_column(Integer, default=0)
    dns_errors: Mapped[int] = mapped_column(Integer, default=0)
    ssl_errors: Mapped[int] = mapped_column(Integer, default=0)
    network_errors: Mapped[int] = mapped_column(Integer, default=0)
    
    # Performance
    avg_response_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    min_response_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_response_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    p95_response_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    p99_response_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Health
    health_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    broken_links_count: Mapped[int] = mapped_column(Integer, default=0)
    redirect_chains_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Content Types
    html_urls: Mapped[int] = mapped_column(Integer, default=0)
    css_urls: Mapped[int] = mapped_column(Integer, default=0)
    js_urls: Mapped[int] = mapped_column(Integer, default=0)
    json_urls: Mapped[int] = mapped_column(Integer, default=0)
    xml_urls: Mapped[int] = mapped_column(Integer, default=0)
    image_urls: Mapped[int] = mapped_column(Integer, default=0)
    pdf_urls: Mapped[int] = mapped_column(Integer, default=0)
    video_urls: Mapped[int] = mapped_column(Integer, default=0)
    other_urls: Mapped[int] = mapped_column(Integer, default=0)
    
    # Timing
    crawl_start_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    crawl_end_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    crawl_duration_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # Relationships
    domain = relationship("Domain", back_populates="crawl_statistics")
    crawl_job = relationship("CrawlJob", back_populates="statistics")
