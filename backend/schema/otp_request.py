from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field
from backend.schema.utils import now

class OTPRequest(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    phone: str = Field(index=True)
    otp_hash: str  # store only hashed OTP
    session_id: Optional[int] = Field(foreign_key="devicesession.id", index=True, nullable=True)
    created_at: datetime = Field(default_factory=now)
    expires_at: datetime = Field(default_factory=lambda: now + datetime.timedelta(minutes=5))
    attempts: int = Field(default=0)
    verified: bool = Field(default=False)