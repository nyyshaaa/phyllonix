from datetime import datetime
from typing import Optional
from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlmodel import SQLModel, Field, Relationship
from backend.schema.utils import now

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