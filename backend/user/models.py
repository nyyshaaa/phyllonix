

from typing import List
from pydantic import BaseModel, Field


class PromoteIn(BaseModel):
    role_name: List[str]
    reason: str | None = None

class ChangePasswordIn(BaseModel):
    current_password: str = Field(..., example="CurrentStrongPassword")
    new_password: str = Field(..., example="NewStrongPassword")