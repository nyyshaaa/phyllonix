from datetime import date
from typing import List, Optional, Union
from pydantic import BaseModel, Field, field_validator ,HttpUrl


class UserSignup(BaseModel):
    email: str = Field(..., example="user@example.com")
    password: str = Field(..., min_length=8, example="strongpassword")
    name: Optional[str] = Field(..., example="Full Name")
