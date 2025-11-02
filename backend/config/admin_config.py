from typing import List, Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ENV: str = "dev"                # "dev" / "staging" / "prod"
    ENABLE_ADMIN: bool = True      # default False -> admin not loaded
    ADMIN_SECRET: Optional[str] = None
    ADMIN_ALLOWLIST_IPS: List[str] = []  # optional
    TEST_ADMIN_ID : str

    class Config:
        env_file = ".env"
        extra="ignore"

admin_config = Settings()