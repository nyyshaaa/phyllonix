import pytest
from backend.db.connection import async_session
from sqlalchemy.ext.asyncio import AsyncSession

@pytest.fixture
async def db_session():
   
    async with  async_session() as session:
        yield session