
# from sqlalchemy import Boolean, DateTime, Text
# from uuid6 import uuid7
# from datetime import datetime
# from typing import List, Optional
# from sqlalchemy.dialects.postgresql import UUID
# from sqlmodel import Column, SQLModel, Field, Relationship, String
# from backend.schema.utils import now


# Seller / payout model
# class Seller(SQLModel, table=True):
#     id: Optional[int] = Field(default=None, primary_key=True)
#     user_id: int = Field(foreign_key="users.id", index=True, nullable=False)
#     display_name: str = Field(sa_column=Column(String, nullable=False))


#     # Preferred: store only the PSP token/connected account id
#     payout_provider: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
#     payout_account_id: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))


#     # If you must store bank details locally, store ciphertext + encrypted_data_key (envelope encryption)
#     bank_account_ciphertext: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
#     bank_key_ciphertext: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))


#     kyc_completed: bool = Field(default=False, sa_column=Column(Boolean, nullable=False, default=False))
#     created_at: datetime = Field(default_factory=now, sa_column=Column(DateTime(timezone=True), nullable=False))