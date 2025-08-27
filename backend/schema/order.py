
from datetime import datetime
from enum import Enum
from typing import List, Optional
import uuid
from sqlmodel import SQLModel, Field, Relationship
from backend.schema.payment import Payment
from backend.schema.utils import now

class OrderStatus(str, Enum):
    CREATED = "created"
    PENDING_PAYMENT = "pending_payment"
    PAID = "paid"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    FULFILLED = "fulfilled"


class Order(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    public_id: str = Field(default_factory=lambda: str(uuid.uuid4()), index=True, unique=True)
    user_id: Optional[int] = Field(foreign_key="user.id", index=True, nullable=True)
    session_id: Optional[int] = Field(foreign_key="devicesession.id", index=True, nullable=True)
    userphone_id:Optional[int] = Field(foreign_key="userphone.id", index=True, nullable=True) 

    # totals
    total_amount: int = Field(default=0) # paise
    shipping_amount: int = Field(default=0)
    status: OrderStatus = Field(default=OrderStatus.CREATED)

    # snapshot contact & address (immutable for this order)
    shipping_name: Optional[str]
    shipping_phone: Optional[str]
    shipping_email: Optional[str]
    shipping_address_text: Optional[str]
    shipping_address_id: Optional[int] = Field(foreign_key="address.id", index=True, nullable=True) # optional reference for convenience; do NOT rely on it alone

    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


    order_items: List["OrderItem"] = Relationship(back_populates="order", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    payments: List["Payment"] = Relationship(back_populates="order", sa_relationship_kwargs={"cascade": "all, delete-orphan"})


class OrderItem(SQLModel, table=True):
    """We keep FKs for traceability, but also snapshot name/price/labels because products & price options change over time."""
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id", index=True)
    product_id: int = Field(foreign_key="product.id", index=True)
    price_option_id: Optional[int] = Field(foreign_key="priceoption.id", nullable=True)


    # immutable snapshots
    product_name: str
    # price_option_label: Optional[str] = None
    unit_price: int = Field(default=0) # paise snapshot
    quantity: int = Field(default=1)
    
    order: "Order" = Relationship(back_populates="order_items")