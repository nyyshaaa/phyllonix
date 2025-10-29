from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Request , status
from fastapi.params import Cookie
from sqlalchemy import select
from sqlalchemy.ext.asyncio import  AsyncSession
from backend.auth.dependencies import device_session_plain, signup_validation
from backend.auth.models import SignIn, SignupIn
from backend.auth.services import create_user, issue_auth_tokens, provide_access_token, validate_refresh_and_fetch_user, validate_refresh_and_update_refresh
from backend.auth.utils import create_access_token
from backend.db.dependencies import get_session
from sqlalchemy.exc import InterfaceError,OperationalError

from backend.common.circuit_breaker import db_circuit, guard_with_circuit
from backend.common.retries import retry_async, is_recoverable_exception

auth_router = APIRouter()

#* sign in via both mobile or email(only email for now)
@auth_router.post("/login")
@guard_with_circuit(db_circuit)
@retry_async(attempts=4, base_delay=0.2, factor=2.0, max_delay=5.0, if_retryable=is_recoverable_exception)
async def login_user(request:Request,payload:SignIn, device_session_token: Optional[str] = Depends(device_session_plain),
                     session: AsyncSession = Depends(get_session)):
    
    access,refresh,session_token=await issue_auth_tokens(session,request,payload,device_session_token)

    # In production: set RT as HttpOnly Secure SameSite cookie.
    # response.set_cookie("refresh", raw_refresh, httponly=True, secure=True, samesite="Lax",
    #                     path="/auth/refresh", max_age=int(REFRESH_TOKEN_SESSION_TTL.total_seconds()))
    return {"message":{"access_token":access,"refresh_token":refresh,"session_token":session_token}}

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
async def refresh(refresh_token: Optional[str] = Header(None, alias="X-Refresh-Token"),
                   session=Depends(get_session)):
    
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")
    
    claims_dict=await validate_refresh_and_fetch_user(session,refresh_token)

    print(claims_dict)

    access=await provide_access_token(claims_dict)

    return {"message":{"access_token":access}}


@auth_router.post("/refresh")
@guard_with_circuit(db_circuit)
@retry_async(attempts=4, base_delay=0.2, factor=2.0, max_delay=5.0, if_retryable=is_recoverable_exception)
async def refresh(request:Request,refresh_cookie: Optional[str] = Cookie(None),
                  refresh_header: Optional[str] = Header(None, alias="X-Refresh-Token"),
                   session=Depends(get_session)):
    
    user_identifier=request.state.user_identifier

    refresh_token = refresh_cookie or refresh_header
    
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")

    claims_dict=await validate_refresh_and_update_refresh(session,refresh_token,user_identifier)
    
    access=await provide_access_token(claims_dict)

    return {"message":{"access_token":access}}


# @auth_router.post("/auth/logout")
# async def logout(device_public_id: str, session = Depends(get_session)):
#     """
#     Revoke a single device session and all its tokens.
#     Clears cookies client-side (cookie clearing done by client or Set-Cookie with Max-Age=0).
#     """
#     now = datetime.now(timezone.utc)

#     # find ds
#     stmt = select(DeviceSession).where(DeviceSession.public_id == device_public_id)
#     res = await session.execute(stmt)
#     ds = res.scalars().first()
#     if not ds:
#         # idempotent: treat missing as success
#         return Response(status_code=status.HTTP_204_NO_CONTENT)

#     async with session.begin():
#         ds.revoked_at = now
#         session.add(ds)
#         # revoke tokens atomically
#         await session.execute(
#             DeviceAuthToken.__table__.update()
#             .where(DeviceAuthToken.device_session_id == ds.id)
#             .values(revoked_at=now, revoked_by="user", revoked_reason="logout")
#         )

#     # invalidate caches (add when integrating Redis)
#     # await redis.delete(f"device:{device_public_id}")
#     # optionally clear refresh cookie: Set-Cookie header from the client or server response

#     return Response(status_code=status.HTTP_204_NO_CONTENT)


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


@auth_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    refresh_token: Optional[str] = Header(None, alias="X-Refresh-Token"),   #** to be retrieved from cookies for real use cases in browsers
    session: AsyncSession = Depends(get_session),
):
    
    user_identifier=request.state.user_identifier

    pass


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
    
    


