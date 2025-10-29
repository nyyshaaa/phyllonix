
from typing import  Optional
from pydantic import BaseModel, Field


class SignupIn(BaseModel):
    email: str = Field(..., example="user@example.com")
    password: str = Field(..., example="StrongPassword")
    name: Optional[str] = Field(None, example="Full Name")

class SignIn(BaseModel):
    email: str = Field(...)
    password: str = Field(...)
    device_name: Optional[str] = None
    device_type: Optional[str] = Field(default="browser")
    device_id: Optional[str] = None  # client-persistent id (localStorage)






