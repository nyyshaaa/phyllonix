from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlmodel import SQLModel, Field
from backend.common.utils import now



# class OTPRequest(SQLModel, table=True):
#     id: Optional[int] = Field(default=None, primary_key=True)
#     phone: str = Field(sa_column=Column(String(20), nullable=False, index=True))  # store E.164 normalized
#     otp_hash: str = Field(sa_column=Column(Text(), nullable=False))  # hashed otp, never store plaintext
#     session_id: Optional[int] = Field(default=None, sa_column=Column(ForeignKey("devicesession.id", ondelete="SET NULL"), index=True, nullable=True))

#     created_at: datetime = Field(default_factory=now, sa_column=Column(DateTime(timezone=True), nullable=False, default=now))
#     expires_at: datetime = Field(default_factory=lambda: now() + timedelta(minutes=5), sa_column=Column(DateTime(timezone=True), nullable=False))
#     attempts: int = Field(default=0, sa_column=Column("attempts", type_=String(), nullable=False))  #* or Integer depending on preference
#     verified: bool = Field(default=False, sa_column=Column("verified", type_=String(), nullable=False))  #* prefer Boolean in migration, as Field for SQLModel compatibility

 