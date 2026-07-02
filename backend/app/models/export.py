import uuid
from datetime import datetime
from typing import Optional, Annotated
from beanie import Document, Indexed
from pydantic import Field


class Export(Document):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    user_id: Annotated[uuid.UUID, Indexed()]
    crawl_job_id: Optional[uuid.UUID] = None

    # Export Details
    export_type: str  # csv, json, excel, sql
    filename: str
    s3_key: Optional[str] = None  # For S3/R2 storage

    # Filters Applied
    filters: dict = {}  # Status codes, status categories, etc.

    # Size
    file_size_bytes: Optional[int] = None

    # Status
    status: str = "pending"  # pending, completed, failed
    download_count: int = 0

    # Timestamps
    created_at: Indexed(datetime) = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None  # For temporary exports

    class Settings:
        name = "exports"
