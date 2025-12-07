from pydantic_settings import BaseSettings

class Settings(BaseSettings):

    TEST_DB_URL: str
    SYNC_TEST_DB:str
    JWT_SECRET :str
    JWT_ALGO : str
    ACCESS_TOKEN_EXPIRE_MINUTES : str
    REFRESH_TOKEN_EXPIRE : str
    PASS_HASH_SCHEME:str
    TOKEN_HASH_ALGO:str
    DEFAULT_ROLE:str
    SELF_PROVIDER:str
    DEVICE_SESSION_EXPIRE_DAYS:str
    RZPAY_KEY:str
    RZPAY_SECRET:str
    RZPAY_GATEWAY_URL:str
    RAZORPAY_WEBHOOK_SECRET:str
    REDIS_HOST : str
    REDIS_PORT : int
    REDIS_DB : int
    RZPAY_WEBHOOK_PATH : str
    PHYL_CURSOR_SECRET : str
    SEED_PASSWORD_TEMPLATE : str
    ADMIN_DEPLOY_TEST_PASSWORD : str
    ADMIN_DEPLOY_TEST_EMAIL : str
    DATABASE_URL : str | None = None

    class Config:
        env_file = ".env"
        extra="ignore"

config_settings = Settings()