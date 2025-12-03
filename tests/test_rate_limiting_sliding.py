
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
async def test_sliding_window_sequential_and_reset(monkeypatch):

    limit = 4
    window = 3
    # app.state.rate_limit = {"limit": limit, "window": window}
    # app.state.rate_limit_strategy = "sliding_window"
    monkeypatch.setattr(app.state, "rate_limit", {"limit": limit, "window": window}, raising=False)
    monkeypatch.setattr(app.state, "rate_limit_strategy", "sliding_window", raising=False)
    
   
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # make `limit` quick requests -> allowed
            allowed = []
            for i in range(limit):
                r = await client.get(f"{url_prefix}/admin/tests/rate-limit-test",headers=headers)
                allowed.append(r.status_code == 200)
                await asyncio.sleep(0.05)
            assert all(allowed)

            # one immediate extra -> should be rate limited
            r = await client.get(f"{url_prefix}/admin/tests/rate-limit-test",headers=headers)
            print(r.status_code)
            assert r.status_code == 429

            # read Retry-After and wait
            retry = int(r.headers.get("Retry-After", "1"))
            await asyncio.sleep(retry + 0.8)

            # now should allow
            r2 = await client.get(f"{url_prefix}/admin/tests/rate-limit-test",headers=headers)
            assert r2.status_code == 200
    
    # delattr(app.state, "rate_limit")


@pytest.mark.asyncio
async def test_sliding_window_concurrent(monkeypatch):
   
    limit = 4
    window = 3
    # app.state.rate_limit = {"limit": limit, "window": window}
    # app.state.rate_limit_strategy = "sliding_window"
    monkeypatch.setattr(app.state, "rate_limit", {"limit": limit, "window": window}, raising=False)
    monkeypatch.setattr(app.state, "rate_limit_strategy", "sliding_window", raising=False)
  
    
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            async def do_get():
                return await client.get(f"{url_prefix}/admin/tests/rate-limit-test", headers=headers)

            tasks = [asyncio.create_task(do_get()) for _ in range(10)]
            resps = await asyncio.gather(*tasks)

            success = [r for r in resps if r.status_code == 200]
            fail = [r for r in resps if r.status_code == 429]
            assert len(success) <= limit
            assert len(success) + len(fail) == 10
  
    # delattr(app.state, "rate_limit")