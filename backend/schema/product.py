from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from uuid6 import uuid7
from sqlmodel import Column, SQLModel, Field, Relationship
from backend.common.utils import now
from sqlalchemy.dialects.postgresql import JSONB,UUID

# class ProductCategory(str, Enum):
#     FOOD = "food"
#     SNACKS = "snacks"
#     LADOOS = "ladoos"
#     CHOCO = "choco"
#     ARTS = "arts"
#     GADGETS = "gadgets"
#     OTHER = "other"

# class ImageUploadStatus(str, Enum):
#     PENDING_UPLOADED = "pending_uploaded"
#     UPLOADED = "uploaded"
#     PROCESSING = "processing"
#     READY = "ready"
#     FAILED = "failed"

# class ProductCategoryLink(SQLModel, table=True):
   
#     id: Optional[int] = Field(default=None, primary_key=True)
#     product_id: int = Field(sa_column=Column(ForeignKey("product.id", ondelete="CASCADE"), index=True, nullable=False))
#     prod_category_id: int = Field(sa_column=Column(ForeignKey("productcategory.id", ondelete="CASCADE"), index=True, nullable=False))

#     # unique constraint to avoid duplicate links
#     __table_args__ = (
#         UniqueConstraint("product_id", "prod_category_id", name="uq_product_category"),
#     )


# class Product(SQLModel, table=True):
#     id: Optional[int] = Field(default=None, primary_key=True)
#     public_id: uuid7 = Field(
#         default_factory=uuid7, 
#         sa_column=Column(UUID(as_uuid=True), unique=True, index=True, nullable=False)
#     )
#     stock_qty:int=Field(sa_column=Column(Integer(), nullable=False))
#     sku: Optional[str] = Field(default=None, sa_column=Column(String(128), nullable=True)) # keep nullable for now , later when necessary create index 
#     name: str = Field(sa_column=Column(String(255), nullable=False))
#     description: Optional[str] = Field(default=None, sa_column=Column(Text(), nullable=True))
#     base_price: int = Field(default=0,description="Price in paise (int)")

#     specs: Optional[Dict[str, Any]] = Field(
#         default=None,
#         sa_column=Column(JSONB, nullable=True),
#         description="Flexible product specs JSON (e.g. { 'weight_g': 500, 'flavor': 'saffron' })",
#     )

#     owner_id: Optional[int] = Field(sa_column=Column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True))
#     # audit fields(in case admin creates  a product on behalf of sa seller)
#     # created_by: Optional[int] = Field(foreign_key="user.id", nullable=True)
#     # updated_by: Optional[int] = Field(foreign_key="user.id", nullable=True)

#     created_at: datetime = Field(default_factory=now,
#         sa_column=Column(DateTime(timezone=True), nullable=False,default=now))
#     updated_at: datetime = Field(default_factory=now,
#         sa_column=Column(DateTime(timezone=True), nullable=False,default=now, onupdate=now))

#     deleted_at: Optional[datetime] = Field(default=None,
#         sa_column=Column(DateTime(timezone=True)))


#     images: List["ProductImage"] = Relationship(back_populates="product", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
#     prod_categories: List["ProductCategory"] = Relationship(back_populates="products", link_model=ProductCategoryLink)

#     # price_options: List["PriceOption"] = Relationship(back_populates="product", sa_relationship_kwargs={"cascade": "all, delete-orphan"})


# class ProductImage(SQLModel, table=True):

#     id: Optional[int] = Field(default=None, primary_key=True)
#     product_id: int = Field(sa_column=Column(ForeignKey("product.id", ondelete="CASCADE"), nullable=False, index=True))
    
#     public_id: uuid7 = Field(default_factory=uuid7, sa_column=Column(UUID(as_uuid=True), unique=True, index=True, nullable=False))
#     storage_key: str = Field(sa_column=Column(String(1024), nullable=False), description="bucket key (not public URL)")
#     # provider: str = Field(default="r2", sa_column=Column(String(32), nullable=False))
#     bucket: Optional[str] = Field(default=None, sa_column=Column(String(255), nullable=True))
#     mime_type: Optional[str] = Field(default=None, sa_column=Column(String(128), nullable=True))
#     file_size: Optional[int] = Field(default=None, sa_column=Column(BigInteger, nullable=True))
#     checksum: Optional[str] = Field(default=None, sa_column=Column(String(128), nullable=True))  # sha256 hex
#     variants: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSONB, nullable=True))
#     status: ImageUploadStatus = Field(sa_column=Column(Enum(ImageUploadStatus, create_type=False),default=ImageUploadStatus.PENDING_UPLOADED,nullable=False))
#     orig_filename: Optional[str] = Field(default=None, sa_column=Column(String(255), nullable=True))
#     sort_order: int = Field(default=0, sa_column=Column(Integer, nullable=False))
#     alt_text: Optional[str] = Field(default=None, sa_column=Column(String(255), nullable=True))

#     created_at: datetime = Field(default_factory=now, sa_column=Column(DateTime(timezone=True), nullable=False, default=now))
#     updated_at: datetime = Field(default_factory=now,sa_column=Column(DateTime(timezone=True), nullable=False,default=now, onupdate=now))

#     # uploaded_by: Optional[int] = Field(foreign_key="user.id", nullable=True)

#     product: "Product" = Relationship(back_populates="images")


# class ProductCategory(SQLModel, table=True):
   
#     id: Optional[int] = Field(default=None, primary_key=True)
#     name: str = Field(sa_column=Column(String(200), unique=True, nullable=False))
#     description: Optional[str] = Field(default=None, sa_column=Column(String(1000), nullable=True))
#     created_at: datetime = Field(default_factory=now, sa_column=Column(DateTime(timezone=True), nullable=False, default=now))
#     updated_at: datetime = Field(default_factory=now, sa_column=Column(DateTime(timezone=True), nullable=False, default=now, onupdate=now))

#     products: List["Product"] = Relationship(back_populates="prod_categories", link_model=ProductCategoryLink)

