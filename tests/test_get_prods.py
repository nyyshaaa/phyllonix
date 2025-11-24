
import asyncio
import pytest
from httpx import AsyncClient
from asgi_lifespan import LifespanManager
from httpx import ASGITransport
from backend.db.dependencies import get_session
from backend.main import app
from sqlmodel import SQLModel, select

import backend.products.routes as products_module

@pytest.fixture
async def ac_client():
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac

@pytest.fixture(autouse=True)
async def clear_redis():
    from backend.cache._cache import redis_client
    await redis_client.flushdb()



@pytest.mark.asyncio
async def test_products_cache_lock_thundering_herd(ac_client, monkeypatch):

    call_count = {"count": 0}
    original_fetch_prods = products_module.fetch_prods

    async def slow_fetch_prods(session, cursor_vals, limit):
        call_count["count"] += 1
        # simulate slow DB
        await asyncio.sleep(0.1)
        return await original_fetch_prods(session, cursor_vals, limit)

    monkeypatch.setattr(products_module, "fetch_prods", slow_fetch_prods)

    async def do_request():
        resp = await ac_client.get("/api/v1/products?limit=10")
        assert resp.status_code == 200, resp.text
        return resp.json()

    # 5 concurrent requests with same params
    results = await asyncio.gather(*[do_request() for _ in range(5)])

    # all responses should be structurally same
    first_items = results[0]["data"]["items"]
    for r in results[1:]:
        assert r["data"]["items"] == first_items

    assert call_count["count"] == 1
