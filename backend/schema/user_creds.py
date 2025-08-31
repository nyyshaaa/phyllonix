from datetime import datetime
from enum import Enum
from typing import Optional
from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlmodel import SQLModel, Field, Relationship

from backend.schema.utils import now

class CredentialType(str, Enum):
    PASSWORD = "password"
    OAUTH = "oauth"


class Credential(SQLModel, table=True):
    """Holds password hashes and oauth provider ids. Per-device refresh token hashes live in DeviceSession."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(sa_column=Column(ForeignKey("users.id", ondelete="CASCADE"),
            index=True,nullable=False))
    type: CredentialType = Field(nullable=False) 
    provider: Optional[str] = Field(sa_column=Column(String(64), default=None, nullable=True))
    provider_user_id: Optional[str] = Field(default=None,sa_column=Column(String(255), nullable=True))
    provider_email: Optional[str] = Field(default=None,sa_column=Column(String(320), nullable=True))
    password_hash: Optional[str] = Field(sa_column=Column(Text(),nullable=True))
    created_at: datetime = Field(default_factory=now,
        sa_column=Column(DateTime(timezone=True), default=now,nullable=False))
    updated_at: datetime = Field(default_factory=now,
        sa_column=Column(DateTime(timezone=True), default=now,nullable=False, onupdate=now))
    revoked_at: Optional[datetime] = Field(default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True))


    user: "Users" = Relationship(back_populates="credentials")  # every credential must be linked to user .