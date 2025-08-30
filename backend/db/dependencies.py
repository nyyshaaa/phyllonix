from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import  AsyncSession
from backend.db.connection import async_session

async def get_session() -> AsyncGenerator[AsyncSession,None]:
    async with async_session() as session:  # using with context manager opens the session on first execute and closes the async session (sesion) instance at the end of with block
        yield session
        

async def get_session_factory():
    yield async_session