from pydantic_settings import BaseSettings

class Settings(BaseSettings):

    TEST_DB_URL: str

    class Config:
        env_file = ".env"
        extra="ignore"

settings = Settings()