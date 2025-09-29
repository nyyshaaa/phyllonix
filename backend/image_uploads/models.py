

from typing import List, Optional
from pydantic import BaseModel


class InitImageItem(BaseModel):
    filename: str
    content_type: str
    filesize: int
    sort_order : Optional[int]

class InitBatchImagesIn(BaseModel):
    images: List[InitImageItem]