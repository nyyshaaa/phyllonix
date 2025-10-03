
import asyncio
import pytest
from httpx import AsyncClient
from asgi_lifespan import LifespanManager
from httpx import ASGITransport
from backend.db.dependencies import get_session
from backend.main import app
from sqlmodel import SQLModel, select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.connection import async_session
from backend.schema.full_schema import CartItem, Product
from test_tokens import plain_device_session_admin

@pytest.fixture
async def ac_client():
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac

   

@pytest.mark.asyncio
async def test_add_to_cart_creates_cart_and_item(ac_client):

    # set cookie in the AsyncClient cookie jar (domain must match base_url host)
    # ac_client.cookies.set("px_device", plain_device_session_admin , domain="test")

    headers = {"Authorization" : "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMTk5NTIzYS02NDc5LTdkZWUtOTRkNy02NjdjZTU1Yjg1MmUiLCJpYXQiOjE3NTk0ODczOTksImV4cCI6MTc1OTQ5MDk5OSwianRpIjoiNjk0MDkwM2IxNzNhNGY2YmE0MTM4MzE5MmJmY2MyOWI4OTZkMTVjMTcwYzExZDE0ODBkMjFiYzRkYjMyZmU5YyIsInJvbGVzIjpbNF0sInJvbGVfdmVyc2lvbiI6MH0.OpwFGx-AP8OebdKGBm5dgAuNJhfW2XPSa0jzHANHZYQ"}

    # 2) call add-to-cart endpoint (device cookie is created by middleware automatically)
    resp = await ac_client.post(f"/api/v1/cart/items/0199a984-e686-71e6-ac75-b6a39394adc9",headers=headers)
    assert resp.status_code == 201, resp.text

    payload = resp.json()
    assert "cart_id" in payload
    assert "item" in payload
    assert payload["item"]["quantity"] == 13

    r2 = await ac_client.post(f"/api/v1/cart/items/0199a984-e686-71e6-ac75-b6a39394adc9",headers=headers)
    assert r2.status_code == 201
    payload = r2.json()
    assert payload["item"]["quantity"] == 14


# python -m pytest tests/test_carts.py
# ================================================================ test session starts ================================================================

# configfile: pytest.ini
# plugins: asyncio-1.2.0, anyio-4.10.0
# asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
# collected 1 item                                                                                                                                    

# tests/test_carts.py .                                                                          [100%]
   