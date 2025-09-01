from fastapi import APIRouter, Depends, Request , status
from sqlalchemy.ext.asyncio import  AsyncSession
from backend.auth.dependencies import signup_validation
from backend.auth.models import SignIn, SignupIn
from backend.auth.services import create_user, issue_auth_tokens
from backend.db.dependencies import get_session

auth_router = APIRouter()

#* sign in via both mobile or email(only email for now)
@auth_router.get("/login")
async def login_user(request:Request,payload:SignIn, session: AsyncSession = Depends(get_session)):

    access,refresh=await issue_auth_tokens(session,request,payload)
    return {"message":{"access_token":access,"refresh_token":refresh}}

#* make phone necessary for signup when app grows (not added now because of otp prices)
@auth_router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup_user(payload: SignupIn=Depends(signup_validation), session: AsyncSession = Depends(get_session)):
    
    await create_user(session,payload)

    #* do email verification via email link 
    
    return {"message": "User created successfully."}

