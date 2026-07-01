import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import ForeignKey, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base

class CrawlComparison(Base):
    __tablename__ = "crawl_comparison"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    domain_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domains.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Crawls being compared
    previous_crawl_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("crawl_jobs.id", ondelete="SET NULL"), nullable=True)
    current_crawl_job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("crawl_jobs.id", ondelete="CASCADE"), nullable=False)
    
    # Changes
    urls_added: Mapped[int] = mapped_column(Integer, default=0)
    urls_removed: Mapped[int] = mapped_column(Integer, default=0)
    new_broken_urls: Mapped[int] = mapped_column(Integer, default=0)
    fixed_broken_urls: Mapped[int] = mapped_column(Integer, default=0)
    new_redirects: Mapped[int] = mapped_column(Integer, default=0)
    removed_redirects: Mapped[int] = mapped_column(Integer, default=0)
    
    # Health change
    health_score_change: Mapped[int] = mapped_column(Integer, default=0) # difference in health score
    
    # Timestamps
    compared_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    domain = relationship("Domain", back_populates="crawl_comparisons")
    previous_crawl_job = relationship("CrawlJob", foreign_keys=[previous_crawl_job_id])
    current_crawl_job = relationship("CrawlJob", foreign_keys=[current_crawl_job_id])
