from datetime import datetime
from typing import List, Optional
from sqlmodel import SQLModel, Field, Relationship

from backend.schema.user import User
from backend.schema.user_phone import UserPhone
from backend.common.utils import now


# WISHLISTS — Persisted like carts; typically no TTL
class Wishlist(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(foreign_key="user.id", index=True, nullable=True,ondelete="CASCADE")
    session_id: Optional[int] = Field(foreign_key="devicesession.id", index=True, nullable=True)
    userphone_id:Optional[int] = Field(foreign_key="userphone.id", index=True, nullable=True,ondelete="CASCADE")
    name: Optional[str] = Field(default="Default")
    created_at: datetime = Field(default_factory=now)


    user: User = Relationship(back_populates="user_wishlist")
    phone: UserPhone = Relationship(back_populates="phone_wishlist")
    wish_items: List["WishlistItem"] = Relationship(back_populates="wishlist")

class WishlistItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    wishlist_id: int = Field(foreign_key="wishlist.id", index=True,ondelete="CASCADE")
    product_id: int = Field(foreign_key="product.id", index=True)
    created_at: datetime = Field(default_factory=now)
    deleted_at: Optional[datetime] = Field(default=None, nullable=True)


    wishlist: Wishlist = Relationship(back_populates="wish_items")