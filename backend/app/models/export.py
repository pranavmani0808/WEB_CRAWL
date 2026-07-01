import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import ForeignKey, String, DateTime, Integer, BigInteger
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base

class Export(Base):
    __tablename__ = "exports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    crawl_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("crawl_jobs.id", ondelete="SET NULL"), nullable=True)
    
    # Export Details
    export_type: Mapped[str] = mapped_column(String(50)) # csv, json, excel, sql
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    s3_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True) # For S3/R2 storage
    
    # Filters Applied
    filters: Mapped[dict] = mapped_column(JSONB, default=dict) # Status codes, status categories, etc.
    
    # Size
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    
    # Status
    status: Mapped[str] = mapped_column(String(50), default="pending") # pending, completed, failed
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True) # For temporary exports

    # Relationships
    user = relationship("User", back_populates="exports")
    crawl_job = relationship("CrawlJob", back_populates="exports")
