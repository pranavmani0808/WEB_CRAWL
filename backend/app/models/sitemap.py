import uuid
from datetime import datetime, date, timezone
from typing import Optional
from sqlalchemy import ForeignKey, String, Boolean, DateTime, Integer, Date, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base

class Sitemap(Base):
    __tablename__ = "sitemaps"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    domain_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domains.id", ondelete="CASCADE"), nullable=False)
    subdomain_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("subdomains.id", ondelete="CASCADE"), nullable=True)
    
    # Sitemap Details
    sitemap_url: Mapped[str] = mapped_column(String(2048), unique=True, nullable=False)
    
    # Type & Hierarchy
    is_index: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    parent_sitemap_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("sitemaps.id", ondelete="CASCADE"), nullable=True)
    
    # Discovery Source
    discovered_from: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Status
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True)
    
    # Content
    url_count: Mapped[int] = mapped_column(Integer, default=0)
    last_modified: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    response_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Timing
    fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    parsed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    fetch_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Error Handling
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
    
    # Avoid conflict with SQLAlchemy's metadata attribute
    meta_data: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)

    # Relationships
    domain = relationship("Domain", back_populates="sitemaps")
    subdomain = relationship("Subdomain", back_populates="sitemaps")
    parent_sitemap = relationship("Sitemap", remote_side=[id], back_populates="child_sitemaps")
    child_sitemaps = relationship("Sitemap", back_populates="parent_sitemap", cascade="all, delete-orphan")
    urls = relationship("URL", back_populates="sitemap", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("sitemap_url", "domain_id", name="idx_sitemaps_url_unique"),
    )
