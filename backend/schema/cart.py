from datetime import datetime
from typing import List, Optional
from sqlmodel import SQLModel, Field, Relationship
from backend.schema.user import User
from backend.schema.user_phone import UserPhone
from backend.schema.utils import now


# CARTS — Persist carts server-side (DB/Redis) so they survive page reloads and can merge on login
# user / userphone to cart (1:1)
# hard delete cart items after some retention window 
class Cart(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(foreign_key="user.id", index=True, nullable=True,ondelete="CASCADE")
    session_id: Optional[int] = Field(foreign_key="devicesession.id", index=True, nullable=True)
    userphone_id:Optional[int] = Field(foreign_key="userphone.id", index=True, nullable=True,ondelete="CASCADE")
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)

    user: Optional[User] = Relationship(back_populates="user_cart")
    phone: Optional[UserPhone] = Relationship(back_populates="phone_cart")
    cart_items: List["CartItem"] = Relationship(back_populates="cart")

# set deleted_at when item is added to order or user removes item , hard delete after some time .
class CartItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    cart_id: int = Field(foreign_key="cart.id", index=True,ondelete="CASCADE")
    product_id: int = Field(foreign_key="product.id", index=True)
    # price_option_id: Optional[int] = Field(foreign_key="priceoption.id", nullable=True)
    quantity: int = Field(default=1)
    unit_price_snapshot: Optional[int] = None # paise
    created_at: datetime = Field(default_factory=now)
    deleted_at: Optional[datetime] = Field(default=None, nullable=True)


    cart: Cart = Relationship(back_populates="cart_items")