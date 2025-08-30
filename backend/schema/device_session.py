
from datetime import datetime
from enum import Enum
from typing import List, Optional
from sqlalchemy import Column,CHAR, ForeignKey,String,DateTime
from sqlalchemy.dialects.postgresql import INET
from sqlmodel import  SQLModel, Field, Relationship
from backend.schema.utils import now

class AuthMethod(str, Enum):
    PASSWORD = "password"
    PHONE = "phone"
    OAUTH = "oauth"


class DeviceSession(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    session_token_hash: str = Field(sa_column=Column(String(64), index=True, nullable=False, unique=True))

    # metadata...
    device_name: Optional[str] = Field(default=None, sa_column=Column(String(128)))
    device_type: Optional[str] = Field(default=None, sa_column=Column(String(64)))
    user_agent_snippet: Optional[str] = Field(default=None, sa_column=Column(String(512)))
    device_fingerprint_hash: Optional[str] = Field(default=None, sa_column=Column(String(64), index=True))
    ip_first_seen: Optional[str] = Field(default=None, sa_column=Column(INET))
    last_seen_ip: Optional[str] = Field(default=None, sa_column=Column(INET))
    last_activity_at: datetime = Field(default_factory=now, nullable=True)
    created_at: datetime = Field(default_factory=now,
        sa_column=Column(DateTime(timezone=True), default=now))

    revoked_at: Optional[datetime] = Field(default=None, nullable=True)
    session_expires_at: Optional[datetime] = Field(default=None, nullable=True)
    # trusted: bool = Field(default=False)

    # relationship to tokens (one-to-many)
    tokens: List["DeviceAuthToken"] = Relationship(back_populates="device_session", sa_relationship_kwargs={"cascade":"all, delete-orphan"},passive_deletes=True)

class DeviceAuthToken(SQLModel, table=True):
    """
    Per-device auth tokens (refresh tokens). One row per issued refresh token.
    Keep history for audit and to allow revocation.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    device_session_id: int = Field(sa_column=Column(
        ForeignKey("devicesession.id", ondelete="CASCADE"),
        index=True,nullable=False))

    # canonical links (nullable)
    user_id: Optional[int] = Field(foreign_key="users.id", index=True, nullable=False)

    token_hash: str = Field(index=True, nullable=False)  #hashed storage 
    issued_at: datetime = Field(default_factory=now,
        sa_column=Column(DateTime(timezone=True), default=now))
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    revoked_by: Optional[str] = Field(default=None, sa_column=Column(String(32)))  # 'user'|'system'|'admin'
    revoked_reason: Optional[str] = None
    auth_method: Optional[AuthMethod] = Field(default=None, nullable=False)
    # user_id_snapshot: Optional[int] = Field(default=None)       # copy of user_id at issuance (for audit)
    # userphone_id_snapshot: Optional[int] = Field(default=None)  # copy of phone-id at issuance

    device_session: "DeviceSession" = Relationship(back_populates="tokens")
    # phone: Optional[UserPhone] = Relationship(back_populates="session_tokens")
    user: "Users" = Relationship(back_populates="session_tokens")