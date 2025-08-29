from datetime import datetime
from typing import List, Optional
import uuid
from sqlmodel import SQLModel, Field, Relationship
from backend.schema.address import Address
from backend.schema.cart import Cart
from backend.schema.device_session import DeviceAuthToken
from backend.schema.user import User
from backend.schema.utils import now
from backend.schema.wishlist import Wishlist


class UserPhone(SQLModel, table=True):
    """Allow only one phone for now and store verification metadata"""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True,ondelete="CASCADE")
    phone: str = Field(index=True)
    is_primary: bool = Field(default=False)
    verified_at: Optional[datetime] = Field(default=None, nullable=True)
    created_at: datetime = Field(default_factory=datetime.now)

    user: User = Relationship(back_populates="phones") 
    session_tokens: List["DeviceAuthToken"] = Relationship(back_populates="phone")
    phone_cart: Cart = Relationship(back_populates="phone")
    phone_wishlist: Wishlist = Relationship(back_populates="phone")
    addresses: List["Address"] = Relationship(back_populates="phone")