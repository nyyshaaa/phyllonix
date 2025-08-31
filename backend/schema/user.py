
from sqlalchemy import DateTime
from uuid6 import uuid7
from datetime import datetime
from typing import List, Optional
from sqlalchemy.dialects.postgresql import UUID
from sqlmodel import Column, SQLModel, Field, Relationship, String
from backend.schema.utils import now

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
    roles: List["Role"] = Relationship(back_populates="user")
    # user_cart: Cart = Relationship(back_populates="user") # user -> cart (1:1)
    # wishlist: Wishlist = Relationship(back_populates="user")
    # orders: List["Order"] = Relationship(back_populates="user")
    