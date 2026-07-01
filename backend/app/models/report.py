import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import ForeignKey, String, DateTime, Text, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base

class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    domain_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domains.id", ondelete="CASCADE"), nullable=False, index=True)
    crawl_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("crawl_jobs.id", ondelete="SET NULL"), nullable=True)
    
    # Report Type
    report_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False) # broken_pages, redirect_chains, etc.
    
    # Content
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    data: Mapped[dict] = mapped_column(JSONB, default=dict) # Report-specific data
    
    # Counts
    issues_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Timing
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    domain = relationship("Domain", back_populates="reports")
    crawl_job = relationship("CrawlJob", back_populates="reports")
