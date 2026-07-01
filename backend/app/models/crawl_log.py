import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import ForeignKey, String, DateTime, Text, BigInteger
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base

class CrawlLog(Base):
    __tablename__ = "crawl_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    crawl_job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("crawl_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Log Entry
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    level: Mapped[str] = mapped_column(String(20)) # info, warning, error
    message: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Context
    event_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True) # robots_found, sitemap_discovered, etc.
    entity_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True) # url, sitemap, domain, worker
    entity_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Details
    details: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Relationships
    crawl_job = relationship("CrawlJob", back_populates="logs")
