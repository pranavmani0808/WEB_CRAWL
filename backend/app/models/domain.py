import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import ForeignKey, String, Boolean, DateTime, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base

class Domain(Base):
    __tablename__ = "domains"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Input & Normalization
    original_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    normalized_url: Mapped[str] = mapped_column(String(2048), unique=True, nullable=False)
    domain: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    
    # Domain Info
    ip_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True) # Stored as string for flexibility
    ssl_valid: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    ssl_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    server_header: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Robots.txt
    robots_txt_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    robots_txt_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    robots_txt_fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    robots_disallow: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Status
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True)
    
    # Counts
    total_subdomains: Mapped[int] = mapped_column(Integer, default=0)
    total_sitemaps: Mapped[int] = mapped_column(Integer, default=0)
    total_urls: Mapped[int] = mapped_column(Integer, default=0)
    crawled_urls: Mapped[int] = mapped_column(Integer, default=0)
    
    # Timestamps
    first_crawl_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_crawl_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
    
    # Metadata & Custom properties
    labels: Mapped[list] = mapped_column(JSONB, default=list)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Avoid conflict with SQLAlchemy's metadata attribute by mapping attribute name to metadata column
    meta_data: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)

    # Relationships
    user = relationship("User", back_populates="domains")
    subdomains = relationship("Subdomain", back_populates="domain", cascade="all, delete-orphan")
    sitemaps = relationship("Sitemap", back_populates="domain", cascade="all, delete-orphan")
    urls = relationship("URL", back_populates="domain", cascade="all, delete-orphan")
    crawl_jobs = relationship("CrawlJob", back_populates="domain", cascade="all, delete-orphan")
    crawl_statistics = relationship("CrawlStatistics", uselist=False, back_populates="domain", cascade="all, delete-orphan")
    reports = relationship("Report", back_populates="domain", cascade="all, delete-orphan")
    crawl_history = relationship("CrawlHistory", back_populates="domain", cascade="all, delete-orphan")
    crawl_comparisons = relationship("CrawlComparison", back_populates="domain", cascade="all, delete-orphan")
