
import time
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import  AsyncSession
from backend.db.dependencies import get_session
from backend.config.admin_config import admin_config
from sqlalchemy.exc import InterfaceError,OperationalError
from backend.common.retries import retry_with_db_circuit

tests_router = APIRouter()


@tests_router.get("/rate-limit-test")
async def rate_limit_test():
     return {"ok": True, "time": int(time.time())}

# -------------------------------------------------------------------------------------------------------------


@tests_router.get("/retries_cb_test")
@retry_with_db_circuit()
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