from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import  AsyncSession
from backend.auth.models import UserSignup
from backend.auth.repository import user_by_email
from backend.auth.services import create_user
from backend.db.dependencies import get_session

auth_router = APIRouter()

@auth_router.post("/signup")
async def user_signup(payload: UserSignup, session: AsyncSession = Depends(get_session)):
    payload_dict = payload.model_dump()
    user=await create_user(payload_dict,session)
    return user

@auth_router.get("/login")
async def user_login(email: str, password: str, session: AsyncSession = Depends(get_session)):
    user = await user_by_email(email, session)
    if not user or not user.verify_password(password):
        return {"error": "Invalid email or password"}
    return {"message": "Login successful"}