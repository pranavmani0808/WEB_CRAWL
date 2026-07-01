import uuid
from datetime import datetime, date, timezone
from typing import Optional
from sqlalchemy import ForeignKey, String, Boolean, DateTime, Integer, Date, Text, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base

class URL(Base):
    __tablename__ = "urls"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    domain_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domains.id", ondelete="CASCADE"), nullable=False)
    subdomain_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("subdomains.id", ondelete="CASCADE"), nullable=True)
    sitemap_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sitemaps.id", ondelete="CASCADE"), nullable=False)
    
    # URL Info
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    url_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    
    # Sitemap Data
    sitemap_last_modified: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    sitemap_change_frequency: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    sitemap_priority: Mapped[Optional[float]] = mapped_column(Numeric(3, 2), nullable=True)
    
    # HTTP Status
    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    status_category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    
    # Redirect Tracking
    final_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    redirect_chain: Mapped[list] = mapped_column(JSONB, default=list) # Array of redirect URLs
    
    # Response Details
    response_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    content_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    content_length: Mapped[Optional[int]] = mapped_column(Integer, nullable=True) # Map to INT, BIGINT in DB migration
    
    # SEO/Content
    canonical_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    robots_meta: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_indexable: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    
    # Crawl Status
    crawl_status: Mapped[str] = mapped_column(String(50), default="pending", index=True)
    crawl_attempt: Mapped[int] = mapped_column(Integer, default=0)
    
    # Timestamps
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
    
    # Error Details
    error_details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Avoid conflict with SQLAlchemy's metadata attribute
    meta_data: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)

    # Relationships
    domain = relationship("Domain", back_populates="urls")
    subdomain = relationship("Subdomain", back_populates="urls")
    sitemap = relationship("Sitemap", back_populates="urls")
