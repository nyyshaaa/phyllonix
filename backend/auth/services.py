

from fastapi import HTTPException
from backend.auth.repository import user_by_email
from backend.schema.user import Users


async def create_user(payload_dict, session):
    user_id=await user_by_email(payload_dict['email'], session)
    if user_id:
        raise HTTPException(status_code=400, detail="User with email already exists") 
    user = Users(**payload_dict)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user