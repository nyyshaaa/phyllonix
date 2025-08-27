from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field, Relationship
from backend.schema.user import User
from backend.schema.utils import now

class Address(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(foreign_key="user.id", index=True, nullable=True)
    userphone_id:Optional[int] = Field(foreign_key="userphone.id", index=True, nullable=True) 
    line1: str
    line2: Optional[str] = None
    city: str
    state: Optional[str] = None
    postal_code: str
    country: Optional[str] = None
    phone: Optional[str] = None
    is_default: bool = Field(default=False)
    created_at: datetime = Field(default_factory=now)
    deleted_at: Optional[datetime] = Field(default=None, nullable=True)

    user: Optional[User] = Relationship(back_populates="addresses")