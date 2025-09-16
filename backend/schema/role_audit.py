# from datetime import datetime
# from typing import List, Optional

# from sqlalchemy import Column, DateTime, ForeignKey, String
# from sqlmodel import Field, SQLModel

# from backend.schema.utils import now


# class RoleAudit(SQLModel, table=True):
#     id: Optional[int] = Field(default=None, primary_key=True)
#     actor_user_id:int = Field(sa_column=Column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
#     target_user_id: int = Field(sa_column=Column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
#     old_roles: List[str] = Field(default_factory=list)
#     new_roles: List[str] = Field(default_factory=list)
#     reason: Optional[str] = Field(default=None, sa_column=Column(String(1000), nullable=True))
#     created_at: datetime = Field(default_factory=now, sa_column=Column(DateTime(timezone=True), nullable=False, default=now))
#     updated_at: datetime = Field(default_factory=now,sa_column=Column(DateTime(timezone=True), nullable=False,default=now, onupdate=now))

