

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ProductCreateIn(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    base_price: int = Field(..., ge=0, description="Price in paise")
    stock_qty: int = Field(0, ge=0)
    sku: Optional[str] = None
    specs: Optional[Dict[str, Any]] = None
    category_ids: Optional[List[int]] = None  # attach categories by id (optional)


class ProductUpdateIn(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    base_price: Optional[int] = Field(None, ge=0)
    stock_qty: Optional[int] = Field(None, ge=0)
    sku: Optional[str] = None
    specs: Optional[Dict[str, Any]] = None
    category_ids: Optional[List[int]] = None  

    class ConfigDict:
        json_schema_extra = "forbid"

class ProductRead(BaseModel):
    id: str
    name: str
    price: int
    created_at: datetime
    # add fields you care about

class ProductsPage(BaseModel):
    items: List[ProductRead]
    next_cursor: Optional[str]
    has_more: bool

