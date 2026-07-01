import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import ForeignKey, String, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base

class Subdomain(Base):
    __tablename__ = "subdomains"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    domain_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domains.id", ondelete="CASCADE"), nullable=False)
    
    # Subdomain Info
    subdomain: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    normalized_url: Mapped[str] = mapped_column(String(2048), unique=True, nullable=False)
    
    # Status
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True)
    
    # Counts
    total_sitemaps: Mapped[int] = mapped_column(Integer, default=0)
    total_urls: Mapped[int] = mapped_column(Integer, default=0)
    crawled_urls: Mapped[int] = mapped_column(Integer, default=0)
    
    # Health
    health_score: Mapped[int] = mapped_column(Integer, default=100)
    crawled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # Relationships
    domain = relationship("Domain", back_populates="subdomains")
    sitemaps = relationship("Sitemap", back_populates="subdomain", cascade="all, delete-orphan")
    urls = relationship("URL", back_populates="subdomain", cascade="all, delete-orphan")
