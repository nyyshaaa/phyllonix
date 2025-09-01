from pydantic_settings import BaseSettings

class Settings(BaseSettings):

    TEST_DB_URL: str
    SYNC_TEST_DB:str
    JWT_SECRET = str
    JWT_ALGO = str
    ACCESS_TOKEN_EXPIRE_MINUTES = str
    REFRESH_TOKEN_EXPIRE_DAYS = str
    PASS_HASH_SCHEME:str
    TOKEN_HASH_ALGO:str
    DEFAULT_ROLE:str
    SELF_PROVIDER:str
    DEVICE_SESSION_EXPIRE_DAYS:str

    class Config:
        env_file = ".env"
        extra="ignore"

config_settings = Settings()