
from backend.config.settings import config_settings
from backend.common.logging_setup import get_logger

logger = get_logger("chlorophyll.auth")

REFRESH_TOKEN_EXPIRE_DAYS = int(config_settings.REFRESH_TOKEN_EXPIRE)

REFRESH_TOKEN_TTL_SECONDS = REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600

ACCESS_TOKEN_TTL_SECONDS = int(config_settings.ACCESS_TOKEN_EXPIRE_MINUTES) * 60

COOKIE_NAME = "__Secure-refresh_token"

ACCESS_COOKIE_NAME = "__Secure-access_token"

