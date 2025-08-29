from datetime import datetime
from enum import Enum
from typing import Optional
from sqlmodel import SQLModel, Field, Relationship

from backend.schema.user import User
from backend.schema.utils import now

class CredentialType(str, Enum):
    PASSWORD = "password"
    OAUTH = "oauth"


class Credential(SQLModel, table=True):
    """Holds password hashes and oauth provider ids. Per-device refresh token hashes live in DeviceSession."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True,nullable=False,ondelete="CASCADE")
    type: CredentialType = Field(nullable=False) # don't give a default so integrity at db level that user for sure adds password or provider id 
    provider: Optional[str] = None # e.g., 'google'
    provider_user_id: Optional[str] = None
    provider_email: Optional[str] = None
    password_hash: Optional[str] = None
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now,onupdate=now)
    revoked_at: Optional[datetime] = Field(default=None, nullable=True)


    user: User = Relationship(back_populates="credentials")  # every credential must be linked to user .