
from datetime import datetime
from typing import List, Optional
from sqlmodel import SQLModel, Field, Relationship
from backend.schema.user import User
from backend.schema.user_phone import UserPhone
from backend.schema.utils import now


class DeviceSession(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    session_token_hash: str = Field(index=True, nullable=False, unique=True) 

    # metadata...
    device_name: Optional[str] = None
    device_type: Optional[str] = None
    user_agent_snippet: Optional[str] = None
    device_fingerprint_hash: Optional[str] = Field(index=True, default=None)
    ip_first_seen: Optional[str] = None
    last_seen_ip: Optional[str] = None
    last_activity_at: datetime = Field(default_factory=now)
    created_at: datetime = Field(default_factory=now)
    revoked_at: Optional[datetime] = Field(default=None, nullable=True)
    # trusted: bool = Field(default=False)

    # relationship to tokens (one-to-many)
    tokens: List["DeviceAuthToken"] = Relationship(back_populates="device_session", sa_relationship_kwargs={"cascade":"all, delete-orphan"})

class DeviceAuthToken(SQLModel, table=True):
    """
    Per-device auth tokens (refresh tokens). One row per issued refresh token.
    Keep history for audit and to allow revocation.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    device_session_id: int = Field(foreign_key="devicesession.id", index=True, nullable=False)

    # canonical links (nullable)
    user_id: Optional[int] = Field(foreign_key="user.id", index=True, nullable=True)
    userphone_id: Optional[int] = Field(foreign_key="userphone.id", index=True, nullable=True)

    refresh_token: str = Field(index=True, nullable=False)  #hashed storage 
    issued_at: datetime = Field(default_factory=now)
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    revoked_by: Optional[str] = None   # 'user'|'system'|'admin'
    revoked_reason: Optional[str] = None
    auth_method: Optional[str] = None  # 'phone'|'password'|'oauth'
    # user_id_snapshot: Optional[int] = Field(default=None)       # copy of user_id at issuance (for audit)
    # userphone_id_snapshot: Optional[int] = Field(default=None)  # copy of phone-id at issuance

    device_session: DeviceSession = Relationship(back_populates="tokens")
    phone: Optional[UserPhone] = Relationship(back_populates="session_tokens")
    user: Optional[User] = Relationship(back_populates="session_tokens")