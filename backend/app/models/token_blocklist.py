import uuid
from datetime import datetime
from beanie import Document
from pydantic import Field
from pymongo import IndexModel, ASCENDING


class TokenBlocklist(Document):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    token: str
    blacklisted_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime

    class Settings:
        name = "token_blocklist"
        indexes = [
            IndexModel([("token", ASCENDING)], unique=True),
        ]
