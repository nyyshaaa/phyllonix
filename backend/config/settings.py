from pydantic_settings import BaseSettings

class Settings(BaseSettings):

    TEST_DB_URL: str
    SYNC_TEST_DB:str

    class Config:
        env_file = ".env"
        extra="ignore"

config_settings = Settings()