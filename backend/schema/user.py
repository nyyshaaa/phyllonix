
from datetime import datetime
from typing import List, Optional
import uuid
from sqlmodel import SQLModel, Field, Relationship
from backend.db.schema import Address, UserPhone, Wishlist
from backend.schema.cart import Cart
from backend.schema.device_session import DeviceAuthToken
from backend.schema.order import Order
from backend.schema.user_creds import Credential
from backend.schema.utils import now

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    public_id: str = Field(default_factory=lambda: str(uuid.uuid4()), index=True, unique=True)
    name: Optional[str] = Field(nullable=True)
    email: Optional[str] = Field(nullable=True)
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)
    deleted_at: Optional[datetime] = Field(default=None, nullable=True)


    # relationships
    phones: List["UserPhone"] = Relationship(back_populates="user")   # user->userphone (1 to many)
    credentials: List["Credential"] = Relationship(back_populates="user")
    addresses: List["Address"] = Relationship(back_populates="user")
    session_tokens: List["DeviceAuthToken"] = Relationship(back_populates="user")
    user_cart: Cart = Relationship(back_populates="user") # user -> cart (1:1)
    wishlist: Wishlist = Relationship(back_populates="user")
    orders: List["Order"] = Relationship(back_populates="user")
    