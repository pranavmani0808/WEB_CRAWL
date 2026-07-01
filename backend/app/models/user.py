import uuid
from datetime import datetime
from typing import Optional, List
from beanie import Document, Indexed, BackLink
from pydantic import Field


class User(Document):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    email: str = Indexed(unique=True)
    username: str = Indexed(unique=True)
    password_hash: str
    is_active: bool = True
    is_admin: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "users"
