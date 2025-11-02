
from asyncio import Lock
import redis.asyncio as redis ,weakref
from backend.config.settings import config_settings

redis_client = redis.Redis(
    host=config_settings.REDIS_HOST, port=config_settings.REDIS_PORT, db=config_settings.REDIS_DB, 
    decode_responses=False)

REDIS_LOCK_TIMEOUT = 5   # seconds