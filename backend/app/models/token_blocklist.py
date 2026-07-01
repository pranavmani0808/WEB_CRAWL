import uuid
from datetime import datetime
from beanie import Document, Indexed
from pydantic import Field


class TokenBlocklist(Document):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    token: str = Indexed(unique=True)
    blacklisted_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime

    class Settings:
        name = "token_blocklist"
