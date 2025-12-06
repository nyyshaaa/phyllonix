from select import select
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.params import Header
from sqlalchemy.ext.asyncio import  AsyncSession
from backend.auth.services import save_device_state
from backend.common.constants import SESSION_TOKEN_COOKIE_MAX_AGE
from backend.common.retries import retry_async
from backend.common.utils import build_success, json_ok, success_response
from backend.db.dependencies import get_session
from fastapi.responses import JSONResponse
from backend.config.admin_config import admin_config

current_env = admin_config.ENV
secure_flag = False if current_env == "dev" else True

home_router = APIRouter()


@home_router.post("/session/init")
async def session_init(
    request: Request,
    session: AsyncSession = Depends(get_session)
):
    user_id = None # creation device session on first visit, no user yet
    
    _,ds_public_id,ds_token_plain=await save_device_state(session,request,user_id)

    await session.commit()

    resp = {"message": {"device_public_id": str(ds_public_id)}} 
    if current_env=="dev":
        resp["message"]["session_token"]=ds_token_plain


    response = JSONResponse(
        content=resp,
        status_code=200
    )
    response = success_response(resp, 200)
    
    response.set_cookie(
        key="session_token",
        value=ds_token_plain,
        httponly=True,
        secure=secure_flag,
        samesite="Lax",
        path="/",
        max_age=SESSION_TOKEN_COOKIE_MAX_AGE
    )

    # optional: set public id cookie so frontend can read it
    response.set_cookie(
        key="device_public_id",
        value=str(ds_public_id),
        httponly=False,
        secure=True,
        samesite="Lax",
        path="/",
        max_age=SESSION_TOKEN_COOKIE_MAX_AGE
    )

    return response

@home_router.get("/health")
async def health_check(session:AsyncSession=Depends(get_session)):
    stmt=select(1)
    
    try:
        res=await session.execute(stmt)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database connection error")
    
    return {"status": "healthy"}
