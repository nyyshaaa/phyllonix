
import asyncio
import os
from dotenv import load_dotenv
import math
import time
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from asgi_lifespan import LifespanManager
from fastapi import FastAPI, Depends
from backend.cache._cache import redis_client
from backend.rate_limiting.dependencies import rate_limit_dependency
from backend.main import app
from tests.save_tokens import token_store

load_dotenv()

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")

url_prefix="/api/v1"

# @pytest_asyncio.fixture()
# async def redis_client():
#     r = redis_client
#     # flush DB for a clean slate before tests
#     await r.flushdb()
#     yield r
#     # cleanup
#     await r.flushdb()
#     await r.close()

@pytest_asyncio.fixture(autouse=True)
async def clear_and_close_redis():
    # ensure clean slate
    await redis_client.flushdb()
    try:
        yield
    finally:
        # flush and close connection so it doesn't try to operate after loop closed
        await redis_client.flushdb()
        await redis_client.aclose()

current_user_payload = {"email": ADMIN_EMAIL}

user_tokens = token_store.get_user_tokens(current_user_payload["email"])
headers = {"Authorization" : f"Bearer {user_tokens["access_token"]}"}


@pytest.mark.asyncio
async def test_fixed_window_sequential_and_reset():
    """
    Sequential test: ensure the first `limit` requests succeed, subsequent fail until reset.
    """
    
    # fire sequential requests
    allowed = []
    limit = 4
    window = 3
    app.state.rate_limit = {"limit": limit, "window": window}


    async with LifespanManager(app=app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac_client:
            for i in range(limit + 2):  # 2 requests beyond limit
                resp = await ac_client.get(f"{url_prefix}/admin/tests/rate-limit-test",headers=headers)
                allowed.append(resp.status_code == 200)
            
                await asyncio.sleep(0.05)

            assert sum(1 for a in allowed if a) == limit

            # read Retry-After header from a failing response
            resp = await ac_client.get(f"{url_prefix}/admin/tests/rate-limit-test",headers=headers)
            if resp.status_code == 429:
                retry = int(resp.headers.get("Retry-After", "1"))
                print("retry",retry)
            else:
                retry = 0

            # wait until reset + small buffer
            await asyncio.sleep(retry + 1)

            # now request should succeed again
            resp2 = await ac_client.get(f"{url_prefix}/admin/tests/rate-limit-test",headers=headers)
            assert resp2.status_code == 200

    # cleanup to avoid leaking to other tests
    delattr(app.state, "rate_limit")

@pytest.mark.asyncio
async def test_fixed_window_concurrent():

    limit = 4
    window = 3
    app.state.rate_limit = {"limit": limit, "window": window}

    
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # coroutine that performs the GET
            async def do_get():
                return await client.get(f"{url_prefix}/admin/tests/rate-limit-test",headers=headers)

            # launch many concurrent
            tasks = [asyncio.create_task(do_get()) for _ in range(12)]
            resps = await asyncio.gather(*tasks)

            # resps = await asyncio.gather(*(do_get() for _ in range(12)))

            success = [r for r in resps if r.status_code == 200]
            fail = [r for r in resps if r.status_code == 429]
            # only up to limit should be successful
            assert len(success) <= limit
            assert len(success) + len(fail) == 12

    delattr(app.state, "rate_limit")






