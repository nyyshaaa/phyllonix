
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    MEDIA_ROOT:str
    PROFILE_IMG_PATH:str
    THUMBNAIL_IMG_PATH:str
    FILE_SECRET_KEY:str
    HASH_ALGO:str

    CLOUDINARY_API_SECRET:str
    CLOUDINARY_API_KEY :str
    CLOUDINARY_CLOUD_NAME :str
    CLOUDINARY_CALLBACK_ROUTE :str
    CLOUDINARY_UPLOAD_URL : str

    class Config:
        env_file = ".env"
        extra="ignore"

media_settings = Settings()