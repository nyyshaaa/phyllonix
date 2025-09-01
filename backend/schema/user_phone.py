# from datetime import datetime
# from typing import List, Optional
# import uuid
# from sqlalchemy import Column, DateTime, ForeignKey, String
# from sqlmodel import SQLModel, Field, Relationship

# from backend.schema.utils import now



# class UserPhone(SQLModel, table=True):
#     """Allow only one phone for now and store verification metadata"""
#     id: Optional[int] = Field(default=None, primary_key=True)
#     user_id: int = Field(sa_column=Column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False))
#     phone: str = Field(sa_column=Column(String(20),nullable=False,unique=True))
#     is_primary: bool = Field(default=False)
#     verified_at: Optional[datetime] = Field(default=None,
#         sa_column=Column(DateTime(timezone=True), default=now,onupdate=now,nullable=False))
#     created_at: datetime = Field(default_factory=now, sa_column=Column(DateTime(timezone=True), nullable=False,default=now))

#     user: "Users" = Relationship(back_populates="phones") 
#     # session_tokens: List["DeviceAuthToken"] = Relationship(back_populates="phone")
#     # phone_cart: Cart = Relationship(back_populates="phone")
#     # phone_wishlist: Wishlist = Relationship(back_populates="phone")
#     # addresses: List["Address"] = Relationship(back_populates="phone")
