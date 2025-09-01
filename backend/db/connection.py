
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker,AsyncSession
from backend.config.settings import config_settings

async_engine=create_async_engine(config_settings.TEST_DB_URL,echo=True)

async_session=async_sessionmaker(bind=async_engine,class_=AsyncSession,expire_on_commit=False)