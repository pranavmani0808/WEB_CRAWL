import uuid
from datetime import datetime
from sqlalchemy import ForeignKey, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base

class CrawlHistory(Base):
    __tablename__ = "crawl_history"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    domain_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domains.id", ondelete="CASCADE"), nullable=False, index=True)
    crawl_job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("crawl_jobs.id", ondelete="CASCADE"), nullable=False)
    
    # Metrics snapshot
    total_urls: Mapped[int] = mapped_column(Integer, default=0)
    successful_urls: Mapped[int] = mapped_column(Integer, default=0)
    broken_urls: Mapped[int] = mapped_column(Integer, default=0)
    redirects: Mapped[int] = mapped_column(Integer, default=0)
    avg_response_time_ms: Mapped[int] = mapped_column(Integer, default=0)
    health_score: Mapped[int] = mapped_column(Integer, default=0)
    
    # Timing
    crawled_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    domain = relationship("Domain", back_populates="crawl_history")
    crawl_job = relationship("CrawlJob", back_populates="crawl_history")
