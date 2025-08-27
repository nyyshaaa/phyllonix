from datetime import datetime
from enum import Enum
from typing import Optional
from sqlmodel import SQLModel, Field, Relationship

from backend.schema.user import User

class CredentialType(str, Enum):
    PASSWORD = "password"
    OAUTH = "oauth"


class Credential(SQLModel, table=True):
    """Holds password hashes and oauth provider ids. Per-device refresh token hashes live in DeviceSession."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    type: CredentialType = Field(default=None,nullable=True)
    provider: Optional[str] = None # e.g., 'google'
    provider_user_id: Optional[str] = None
    provider_email: Optional[str] = None
    password_hash: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    revoked_at: Optional[datetime] = Field(default=None, nullable=True)


    user: User = Relationship(back_populates="credentials")