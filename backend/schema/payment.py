# from datetime import datetime
# from typing import Optional
# from sqlalchemy import Enum
# from sqlmodel import Relationship, SQLModel, Field
# from backend.schema.order import Order
# from backend.common.utils import now

# class PaymentStatus(str, Enum):
#     INIT = "init"
#     SUCCESS = "success"
#     FAILED = "failed"
#     REFUNDED = "refunded"

# order -> payment (1 to many)
#* update this and related tables properly 
# class Payment(SQLModel, table=True):
#     id: Optional[int] = Field(default=None, primary_key=True)
#     order_id: int = Field(foreign_key="order.id", index=True)
#     gateway: str
#     gateway_transaction_id: Optional[str] = Field(index=True, nullable=True)
#     amount: int = Field(default=0)
#     status: PaymentStatus = Field(default=PaymentStatus.INIT)
#     raw_payload: Optional[str] = None
#     created_at: datetime = Field(default_factory=now)
#     updated_at: datetime = Field(default_factory=now)

#     order: Order = Relationship(back_populates="payments")