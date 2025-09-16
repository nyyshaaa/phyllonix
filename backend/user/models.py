

from typing import List
from pydantic import BaseModel


class PromoteIn(BaseModel):
    role_name: List[str]
    reason: str | None = None