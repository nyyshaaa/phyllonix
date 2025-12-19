

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
    category_names: Optional[List[str]] = None 


class ProductUpdateIn(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    base_price: Optional[int] = Field(None, ge=0)
    stock_qty: Optional[int] = Field(None, ge=0)
    sku: Optional[str] = None
    specs: Optional[Dict[str, Any]] = None
    category_names: Optional[List[str]] = None  

    model_config = {"extra": "forbid"}   # for any extra input fields in model raise 422 at pydantic level

