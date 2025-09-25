

from typing import List
from pydantic import BaseModel


class InitImageItem(BaseModel):
    filename: str
    content_type: str
    filesize: int

class InitBatchImagesIn(BaseModel):
    images: List[InitImageItem]