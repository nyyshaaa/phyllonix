import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Request, Response , status
from fastapi.params import Cookie
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import  AsyncSession
from backend.auth.constants import REFRESH_TOKEN_TTL_SECONDS
from backend.auth.dependencies import device_session_pid, device_session_plain, refresh_token, signup_validation
from backend.auth.models import SignIn, SignupIn
from backend.auth.services import create_user, issue_auth_tokens, logout_device_session, provide_access_token, validate_refresh_and_fetch_user, validate_refresh_and_update_refresh
from backend.db.dependencies import get_session
from sqlalchemy.exc import InterfaceError,OperationalError
from backend.common.circuit_breaker import db_circuit, guard_with_circuit
from backend.common.retries import retry_async, is_recoverable_exception
from backend.config.admin_config import admin_config

current_env = admin_config.ENV

auth_router = APIRouter()


#* sign in via both mobile or email(only email for now)
@auth_router.post("/login")
@guard_with_circuit(db_circuit)
@retry_async(attempts=4, base_delay=0.2, factor=2.0, max_delay=5.0, if_retryable=is_recoverable_exception)
async def login_user(request:Request,payload:SignIn,device_session_token: Optional[str] = Depends(device_session_plain),
                     session: AsyncSession = Depends(get_session)):
    
    if not device_session_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail="Please pass all required headers including devicesession token")

    access,refresh=await issue_auth_tokens(session,payload,device_session_token)

    resp = {"message":{"access_token":access}}
    if current_env=="dev":
        resp["message"]["refresh_token"]=refresh

    response = JSONResponse(
        content=resp,
        status_code=200
    )

    response.set_cookie("refresh_token", refresh, httponly=True, secure=True, path="/auth/refresh",
                        max_age=REFRESH_TOKEN_TTL_SECONDS, samesite="Lax")

    return response


#* make phone necessary for signup when app grows (not added now because of otp prices)
@auth_router.post("/signup", status_code=status.HTTP_201_CREATED)
@guard_with_circuit(db_circuit)
@retry_async(attempts=4, base_delay=0.2, factor=2.0, max_delay=5.0, if_retryable=is_recoverable_exception)
async def signup_user(payload: SignupIn=Depends(signup_validation), session: AsyncSession = Depends(get_session)):
    
    user_id=await create_user(session,payload)

    #** do email verification via email link 
    
    return {"message": f"User {user_id} created successfully."}


@auth_router.post("/refresh")
@guard_with_circuit(db_circuit)
@retry_async(attempts=4, base_delay=0.2, factor=2.0, max_delay=5.0, if_retryable=is_recoverable_exception)
async def refresh_auth(refresh_token : str = Depends(refresh_token),
                   session=Depends(get_session)):

    
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")

    claims_dict,refresh_plain=await validate_refresh_and_update_refresh(session,refresh_token)
    
    access=await provide_access_token(claims_dict)

    resp = {"message":{"access_token":access}}
    if current_env=="dev":
        resp["message"]["refresh_token"]=refresh_plain

    response = JSONResponse(
        content=resp,
        status_code=200
    )
    response.set_cookie("refresh_token", refresh_plain, httponly=True, secure=True, path="/auth/refresh",
                        max_age=REFRESH_TOKEN_TTL_SECONDS, samesite="Lax")

    return response


@auth_router.post("/auth/logout")
async def logout(device_public_id: str = Depends(device_session_pid), session = Depends(get_session)):
   
    await logout_device_session(session,device_public_id)
 
    res = Response(status_code=status.HTTP_204_NO_CONTENT)
   
    res.delete_cookie(key="refresh", path="/auth/refresh")
    res.delete_cookie(key="session_token", path="/")
    res.delete_cookie(key="device_public_id", path="/")

    return res






# --------------------------------------------------------------------------------------------------------------
@auth_router.get("/health")
@guard_with_circuit(db_circuit)
@retry_async(attempts=1, base_delay=0.2, factor=2.0, max_delay=5.0, if_retryable=is_recoverable_exception)
async def health_check(session:AsyncSession=Depends(get_session)):
    stmt=select(1)
    
    try:
        res=await session.execute(stmt)
        print(res.scalar_one_or_none())
    except Exception as e:
        raise e

    return {"status": "healthy"}



@auth_router.get("/retries_cb_test")
@guard_with_circuit(db_circuit)
@retry_async(attempts=1, base_delay=0.2, factor=2.0, max_delay=5.0, if_retryable=is_recoverable_exception)
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
    
    


