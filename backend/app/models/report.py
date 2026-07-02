import uuid
from datetime import datetime
from typing import Optional
from beanie import Document
from pydantic import Field


class Report(Document):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    domain_id: uuid.UUID
    crawl_job_id: Optional[uuid.UUID] = None

    # Report Type
    report_type: str  # broken_pages, redirect_chains, etc.

    # Content
    title: str
    description: Optional[str] = None
    data: dict = {}  # Report-specific data

    # Counts
    issues_count: int = 0

    # Timing
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "reports"
