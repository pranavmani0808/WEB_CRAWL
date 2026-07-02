import uuid
from datetime import datetime
from typing import Optional, List
from beanie import Document, BackLink
from pydantic import Field
from pymongo import IndexModel, ASCENDING


class User(Document):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    email: str
    username: str
    password_hash: str
    is_active: bool = True
    is_admin: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "users"
        indexes = [
            IndexModel([("email", ASCENDING)], unique=True),
            IndexModel([("username", ASCENDING)], unique=True),
        ]
