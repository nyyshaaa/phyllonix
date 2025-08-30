
from sqlalchemy import select
from backend.schema.user import Users


async def user_by_email(email,session):
    stmt=select(Users.id).where(Users.email==email)
    result=await session.exec(stmt)
    user=result.first()
    return user