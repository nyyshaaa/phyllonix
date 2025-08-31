from datetime import date
from typing import List, Optional, Union
from pydantic import BaseModel, Field, field_validator ,HttpUrl


class SignupIn(BaseModel):
    email: str = Field(..., example="user@example.com")
    password: str = Field(..., example="StrongPassw0rd!")
    name: Optional[str] = Field(None, example="Full Name")

class SignIn(BaseModel):
    email: str = Field(...)
    password: str = Field(...)






