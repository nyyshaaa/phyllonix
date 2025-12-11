import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Request, Response , status
from fastapi.params import Cookie
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import  AsyncSession
from backend.auth.constants import ACCESS_COOKIE_NAME, ACCESS_TOKEN_TTL_SECONDS, COOKIE_NAME, REFRESH_TOKEN_TTL_SECONDS
from backend.auth.dependencies import device_session_pid, device_session_plain, refresh_token, signup_validation
from backend.auth.models import SignIn, SignupIn
from backend.auth.services import create_user, issue_auth_tokens, logout_device_session, provide_access_token, validate_refresh_and_fetch_user, validate_refresh_and_update_refresh
from backend.common.utils import success_response
from backend.db.dependencies import get_session, get_session_factory
from sqlalchemy.exc import InterfaceError,OperationalError
# from backend.common.circuit_breaker import db_circuit, guard_with_circuit
from backend.common.retries import retry_async, is_recoverable_exception
from backend.config.admin_config import admin_config
from backend.auth.constants import logger

current_env = admin_config.ENV
secure_flag = False if current_env == "dev" else True

auth_router = APIRouter()


#* sign in via both mobile or email(only email for now)
@auth_router.post("/login")
async def login_user(request:Request,payload:SignIn,device_session_token: Optional[str] = Depends(device_session_plain),
                     session: AsyncSession = Depends(get_session),session_maker = Depends(get_session_factory)):
    
    logger.info("login.attempt", extra={"email": payload.email})
    
    if not device_session_token:
        logger.warning("login.failed", extra={"reason": "missing_device_session_token", "email": payload.email})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Device session token is required for login")

    access,refresh=await issue_auth_tokens(session,session_maker,payload,device_session_token)

    resp = {"message":{"access_token":access}}
    if current_env=="dev":
        resp["message"]["refresh_token"]=refresh

    response = success_response(resp, 200)

    response.set_cookie(COOKIE_NAME, refresh, httponly=True, secure=secure_flag, path="/auth/refresh",
                        max_age=int(REFRESH_TOKEN_TTL_SECONDS), samesite="Lax")


    logger.info("login.success", extra={"email": payload.email})
    return response


#* make phone necessary for signup when app grows (not added now because of otp prices)
@auth_router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup_user(payload: SignupIn=Depends(signup_validation), session: AsyncSession = Depends(get_session)):
    
    logger.info("signup.attempt", extra={"email": payload.get("email")})
    
    user_id=await create_user(session,payload)
    logger.info("signup.success", extra={"email": payload.get("email")})
    return success_response({"message": f"User created successfully."}, 201)
 

@auth_router.post("/refresh")
async def refresh_auth(refresh_token : str = Depends(refresh_token),
                   session=Depends(get_session)):

    logger.info("refresh.attempt")
    
    if not refresh_token:
        logger.warning("refresh.failed", extra={"reason": "missing_refresh_token"})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")

    
    claims_dict,refresh_plain=await validate_refresh_and_update_refresh(session,refresh_token)
    
    access=await provide_access_token(claims_dict)

    resp = {"message":{"access_token":access}}
    if current_env=="dev":
        resp["message"]["refresh_token"]=refresh_plain

    response = success_response(resp, 200)
    
    response.set_cookie(COOKIE_NAME, refresh_plain, httponly=True, secure=True, path="/auth/refresh",
                        max_age=REFRESH_TOKEN_TTL_SECONDS, samesite="Lax")

    logger.info("refresh.success", extra={"user_public_id": claims_dict.get("user_public_id")})
    return response



@auth_router.post("/logout")
async def logout(device_public_id: str = Depends(device_session_pid), session = Depends(get_session)):
   
    logger.info("logout.attempt", extra={"device_public_id": device_public_id})
    
    await logout_device_session(session,device_public_id)
    
    res = success_response({"message": "Logged out successfully."}, 200)
    
    res.delete_cookie(key=COOKIE_NAME, path="/auth/refresh")
    res.delete_cookie(key="device_public_id", path="/")

    logger.info("logout.success", extra={"device_public_id": device_public_id})
    return res
  

# -------------------------------------------------------------------------------------------------------------

@auth_router.get("/retries_cb_test")
async def health_check(session:AsyncSession=Depends(get_session)):
    stmt=select(1)
    
    try:
        res=await session.execute(stmt)
        print(res.scalar_one_or_none())
        print("heya")
        raise OperationalError("DB Error",None,None)

    except (OperationalError, InterfaceError):
        print("neya")
        raise 
    
    


