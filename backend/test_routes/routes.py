


import time
from fastapi import APIRouter


tests_router = APIRouter()


@tests_router.get("/rate-limit-test")
async def rate_limit_test():
     return {"ok": True, "time": int(time.time())}