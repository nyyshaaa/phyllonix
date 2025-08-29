
import uuid
from datetime import datetime
from typing import List, Optional
from sqlalchemy import UUID
from sqlalchemy.dialects.postgresql import ULID
from sqlmodel import Column, SQLModel, Field, Relationship, String
from backend.db.schema import  UserPhone, Wishlist
from backend.schema.address import Address
from backend.schema.cart import Cart
from backend.schema.device_session import DeviceAuthToken
from backend.schema.order import Order
from backend.schema.user_creds import Credential
from backend.schema.utils import now

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)  #* optional just means for the created object before saving in db .
    public_id: uuid.UUID = Field(
        default_factory=uuid.uuid7,
        sa_column=Column(UUID(as_uuid=True), unique=True, index=True, nullable=False)
    )
    email: Optional[str] = Field(nullable=True,unique=True)
    is_admin: bool = Field(default=False)
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now,onupdate=now)
    deleted_at: Optional[datetime] = Field(default=None, nullable=True)

    # Simple profile images (with a single predefined size)
    profile_image_url: Optional[str] = Field(default=None, nullable=True)            # canonical/original
    profile_image_thumb_url: Optional[str] = Field(default=None, nullable=True)     # small/thumbnail



    # relationships
    # phones: List["UserPhone"] = Relationship(back_populates="user")   # user->userphone (1 to many)
    credentials: List["Credential"] = Relationship(back_populates="user")
    addresses: List["Address"] = Relationship(back_populates="user")
    session_tokens: List["DeviceAuthToken"] = Relationship(back_populates="user")
    # user_cart: Cart = Relationship(back_populates="user") # user -> cart (1:1)
    # wishlist: Wishlist = Relationship(back_populates="user")
    # orders: List["Order"] = Relationship(back_populates="user")
    