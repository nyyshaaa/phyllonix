

from backend.config.settings import config_settings

REFRESH_TOKEN_EXPIRE_HOURS = int(config_settings.REFRESH_TOKEN_EXPIRE_HOURS)

REFRESH_TOKEN_TTL_SECONDS = REFRESH_TOKEN_EXPIRE_HOURS * 3600