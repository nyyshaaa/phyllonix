
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    MEDIA_ROOT:str
    PROFILE_IMG_PATH:str
    THUMBNAIL_IMG_PATH:str
    FILE_SECRET_KEY:str
    HASH_ALGO:str

    class Config:
        env_file = ".env"
        extra="ignore"

media_settings = Settings()