from datetime import datetime
from enum import Enum
from typing import List, Optional
import uuid
from sqlmodel import SQLModel, Field, Relationship
from backend.db.schema import UserPhone
from backend.schema.user_creds import Credential
from backend.schema.utils import now

class ProductCategory(str, Enum):
    FOOD = "food"
    LADOOS = "ladoos"
    CHOCO = "choco"
    ARTS = "arts"
    OTHER = "other"


# Permissions (app-level, not DB):
# Only users with role = 'admin' or role = 'vendor' and owner_id == user.id may edit/delete.
class Product(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    public_id: str = Field(default_factory=lambda: str(uuid.uuid4()), index=True, unique=True)
    sku: Optional[str] = Field(index=True, nullable=True)
    name: str
    description: Optional[str]
    category: ProductCategory = Field(default=ProductCategory.OTHER)
    base_price: int = 0 # paise
    active: bool = True
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)

    owner_id: Optional[int] = Field(foreign_key="user.id", index=True, nullable=True)
    # created_by/last_updated_by audit fields also useful
    created_by: Optional[int] = Field(foreign_key="user.id", nullable=True)
    updated_by: Optional[int] = Field(foreign_key="user.id", nullable=True)


    images: List["ProductImage"] = Relationship(back_populates="product", sa_relationship_kwargs={"cascade": "all, delete-orphan"})
    # price_options: List["PriceOption"] = Relationship(back_populates="product", sa_relationship_kwargs={"cascade": "all, delete-orphan"})

class ProductImage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id", index=True)
    url: str
    alt_text: Optional[str] = None
    order: int = 0


    product: Product = Relationship(back_populates="images")