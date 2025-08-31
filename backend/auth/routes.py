from fastapi import APIRouter, Depends , status
from sqlalchemy.ext.asyncio import  AsyncSession
from backend.auth.dependencies import signup_validation
from backend.auth.models import SignIn, SignupIn, UserSignup
from backend.auth.repository import user_by_email
from backend.auth.services import create_user, get_user_token
from backend.db.dependencies import get_session

auth_router = APIRouter()

#* sign in via both mobile or email(only email for now)
@auth_router.get("/login")
async def login_user(payload:SignIn, session: AsyncSession = Depends(get_session)):
    payload_dict = payload.model_dump()

    await get_user_token(payload_dict,session)

#* make phone necessary for signup when app grows (not added now because of otp prices)
#** check to pass payload in signup_validation
@auth_router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup_user(payload: SignupIn=Depends(signup_validation), session: AsyncSession = Depends(get_session)):
    payload_dict = payload.model_dump()
    await create_user(session,payload_dict)

    #* do email verification via email link 
    
    return {"message": "User created successfully."}

