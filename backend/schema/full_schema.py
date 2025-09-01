import enum
from sqlalchemy import DateTime, Enum, ForeignKey, Text, UniqueConstraint
from uuid6 import uuid7
from datetime import datetime
from typing import List, Optional 
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.dialects.postgresql import INET
from sqlmodel import Column, SQLModel, Field, Relationship, String
from backend.schema.utils import now

# Join tables
class UserRole(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True,nullable=False)
    #* add user_phone id as well later 
    role_id: Optional[int] = Field(default=None, foreign_key="role.id", index=True,nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_role_user_id_role_id"),)


class Users(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)  #* optional just means for the created object before saving in db .
    public_id: uuid7 = Field(
        default_factory=uuid7, 
        sa_column=Column(UUID(as_uuid=True), unique=True, index=True, nullable=False)
    )
    email: Optional[str] = Field(default=None,sa_column=Column(String(320), nullable=True))
    name: Optional[str] = Field(default=None, sa_column=Column(String(128), nullable=True))
    created_at: datetime = Field(default_factory=now,
        sa_column=Column(DateTime(timezone=True), nullable=False,default=now))
    updated_at: datetime = Field(default_factory=now,
        sa_column=Column(DateTime(timezone=True), nullable=False,default=now, onupdate=now))

    deleted_at: Optional[datetime] = Field(default=None,
        sa_column=Column(DateTime(timezone=True)))

    # Simple profile images (with a single predefined size)
    profile_image_url: Optional[str] = Field(default=None, sa_column=Column(String(1024), nullable=True))
    profile_image_thumb_url: Optional[str] = Field(default=None, sa_column=Column(String(1024), nullable=True))




    # relationships
    phones: List["UserPhone"] = Relationship(back_populates="user")   # user->userphone (1 to many)
    credentials: List["Credential"] = Relationship(back_populates="user")
    addresses: List["Address"] = Relationship(back_populates="user")
    session_tokens: List["DeviceAuthToken"] = Relationship(back_populates="user")
    roles: List["Role"] = Relationship(back_populates="user",link_model=UserRole)
    # user_cart: Cart = Relationship(back_populates="user") # user -> cart (1:1)
    # wishlist: Wishlist = Relationship(back_populates="user")
    # orders: List["Order"] = Relationship(back_populates="user")



class RolePermission(SQLModel, table=True):
    id:Optional[int] = Field(default=None, primary_key=True)
    role_id: Optional[int] = Field(default=None, foreign_key="role.id", index=True,nullable=False)
    permission_id: Optional[int] = Field(default=None, foreign_key="permission.id", index=True,nullable=False)

    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permission_role_id_permission_id"),)

# Core tables
class Role(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column(String(length=200), unique=True, nullable=False,default='buyer'))
    description: Optional[str] = None
    user: List["Users"] = Relationship(back_populates="roles",link_model=UserRole)
    permissions: List["Permission"] = Relationship(back_populates="roles", link_model=RolePermission)

class Permission(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column(String, unique=True, nullable=False))
    description: Optional[str] = None
    roles: List["Role"] = Relationship(back_populates="permissions", link_model=RolePermission)

class UserPhone(SQLModel, table=True):
    """Allow only one phone for now and store verification metadata"""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(sa_column=Column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False))
    phone: str = Field(sa_column=Column(String(20),nullable=False,unique=True))
    is_primary: bool = Field(default=False)
    verified_at: Optional[datetime] = Field(default=None,
        sa_column=Column(DateTime(timezone=True), default=now,onupdate=now,nullable=False))
    created_at: datetime = Field(default_factory=now, sa_column=Column(DateTime(timezone=True), nullable=False,default=now))

    user: "Users" = Relationship(back_populates="phones") 

class CredentialType(str, enum.Enum):
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


class Address(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(sa_column=Column(ForeignKey("users.id", ondelete="CASCADE"),
            index=True,
            nullable=False))
    line1: str
    line2: Optional[str] = None
    city: str
    state: Optional[str] = None
    name: Optional[str] = Field(sa_column=Column(String(128), nullable=True))
    postal_code: str
    country: str = Field(default="IN",nullable=False)
    phone: str = Field(nullable=False)
    is_default: bool = Field(default=False)
    created_at: datetime = Field(default_factory=now,
        sa_column=Column(DateTime(timezone=True), default=now))
    updated_at: datetime = Field(default_factory=now,
        sa_column=Column(DateTime(timezone=True), default=now, onupdate=now))
    deleted_at: Optional[datetime] = Field(default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True))

    user: "Users" = Relationship(back_populates="addresses")
    # phone: Optional["UserPhone"] = Relationship(back_populates="addresses")

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
