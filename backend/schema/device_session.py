
from datetime import datetime
import enum
from typing import List, Optional
from sqlalchemy import Column,CHAR, Enum, ForeignKey,String,DateTime
from sqlalchemy.dialects.postgresql import INET
from sqlmodel import  SQLModel, Field, Relationship
from backend.schema.utils import now

class AuthMethod(str, enum.Enum):
    PASSWORD = "password"
    PHONE = "phone"
    OAUTH = "oauth"


class DeviceSession(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    # hashed session token (e.g., sha256 hex = 64 chars) - unique so no duplicate tokens
    session_token_hash: str = Field(sa_column=Column(String(128), nullable=False, unique=True, index=True))

    # metadata...
    device_name: Optional[str] = Field(default=None, sa_column=Column(String(128)))
    device_type: Optional[str] = Field(default=None, sa_column=Column(String(64)))
    user_agent_snippet: Optional[str] = Field(default=None, sa_column=Column(String(512)))
    device_fingerprint_hash: Optional[str] = Field(default=None, sa_column=Column(String(128), nullable=True))

    ip_first_seen: Optional[str] = Field(default=None, sa_column=Column(INET, nullable=True))
    last_seen_ip: Optional[str] = Field(default=None, sa_column=Column(INET, nullable=True))

    last_activity_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    created_at: datetime = Field(default_factory=now, sa_column=Column(DateTime(timezone=True), nullable=False, default=now))

    revoked_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    session_expires_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))

    # relationship to tokens (one-to-many)
    tokens: List["DeviceAuthToken"] = Relationship(back_populates="device_session",
                                                  sa_relationship_kwargs={"cascade": "all, delete-orphan"},
                                                  passive_deletes=True)


class DeviceAuthToken(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    device_session_id: int = Field(sa_column=Column(ForeignKey("devicesession.id", ondelete="CASCADE"), index=True, nullable=False))

    # canonical link to user 
    user_id: int = Field(sa_column=Column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False))

    # hashed refresh token
    token_hash: str = Field(sa_column=Column(String(200), nullable=False, unique=True, index=True))

    issued_at: datetime = Field(default_factory=now, sa_column=Column(DateTime(timezone=True), nullable=False, default=now))
    expires_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    revoked_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))

    revoked_by: Optional[str] = Field(default=None, sa_column=Column(String(32), nullable=True))  # 'user'|'system'|'admin'
    revoked_reason: Optional[str] = Field(default=None, sa_column=Column(String(256), nullable=True))

    # auth_method stored as an enum column
    auth_method: AuthMethod = Field(sa_column=Column(Enum(AuthMethod, create_type=False), nullable=False))

    device_session: "DeviceSession" = Relationship(back_populates="tokens")
    user: "Users" = Relationship(back_populates="session_tokens")
