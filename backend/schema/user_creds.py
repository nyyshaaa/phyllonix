from datetime import datetime
from enum import Enum
from typing import Optional
from sqlalchemy import Column, DateTime, ForeignKey
from sqlmodel import SQLModel, Field, Relationship

from backend.schema.utils import now

class CredentialType(str, Enum):
    PASSWORD = "password"
    OAUTH = "oauth"


class Credential(SQLModel, table=True):
    """Holds password hashes and oauth provider ids. Per-device refresh token hashes live in DeviceSession."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(sa_column=Column(ForeignKey("user.id", ondelete="CASCADE"),
            index=True,nullable=False))
    type: CredentialType = Field(nullable=False) # don't give a default so integrity at db level that user for sure adds password or provider id 
    provider: Optional[str] = None # e.g., 'google'
    provider_user_id: Optional[str] = None
    provider_email: Optional[str] = None
    password_hash: Optional[str] = None
    created_at: datetime = Field(default_factory=now,
        sa_column=Column(DateTime(timezone=True), default=now))
    updated_at: datetime = Field(default_factory=now,
        sa_column=Column(DateTime(timezone=True), default=now, onupdate=now))
    revoked_at: Optional[datetime] = Field(default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True))


    user: "User" = Relationship(back_populates="credentials")  # every credential must be linked to user .