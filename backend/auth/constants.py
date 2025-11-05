

from backend.config.settings import config_settings

REFRESH_TOKEN_EXPIRE_DAYS = int(config_settings.REFRESH_TOKEN_EXPIRE)

REFRESH_TOKEN_TTL_SECONDS = REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600