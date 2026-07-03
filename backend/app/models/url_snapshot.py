import uuid
from datetime import datetime
from typing import Optional, List
from beanie import Document
from pydantic import Field
from pymongo import IndexModel, ASCENDING


class UrlSnapshot(Document):
    """A frozen copy of a URL's result at the moment one specific crawl job
    finished.

    URL documents are stored per-domain and get overwritten on every
    re-crawl, so there's no way to look back at what an older job actually
    saw once a newer crawl has run. Snapshots are written once, at job
    completion, purely so two jobs can be diffed later (see the /compare
    endpoint) without depending on data that's since been overwritten.
    """
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    crawl_job_id: uuid.UUID
    domain_id: uuid.UUID

    url: str
    url_hash: str
    status_code: Optional[int] = None
    status_category: Optional[str] = None
    response_time_ms: Optional[int] = None
    is_indexable: Optional[bool] = None
    seo_issues: List[dict] = []

    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "url_snapshots"
        indexes = [
            IndexModel([("crawl_job_id", ASCENDING), ("url_hash", ASCENDING)]),
            IndexModel([("domain_id", ASCENDING)]),
        ]
