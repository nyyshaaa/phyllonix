
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker,AsyncSession
from backend.config.settings import config_settings
from backend.db.utils import _normalize_db_url

TEST_DATABASE_URL=_normalize_db_url(config_settings.TEST_DB_URL)

async_engine=create_async_engine(TEST_DATABASE_URL,echo=False)

async_session=async_sessionmaker(bind=async_engine,class_=AsyncSession,expire_on_commit=False)