
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
from tests.save_tokens import token_store
from test_tokens import current_user_payload , current_user2_payload

@pytest.fixture
async def ac_client():
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac

current_user_payload = current_user_payload

@pytest.mark.asyncio
async def test_add_to_cart_user_logged(ac_client):

    user_tokens = token_store.get_user_tokens(current_user_payload["email"])
    # device_headers = {"X-Device-Token": user_tokens["session_token"]}
    headers = {"Authorization" : f"Bearer {user_tokens["access_token"]}"}

    resp = await ac_client.post(f"/api/v1/cart/items/0199a984-e686-71e6-ac75-b6a39394adc9",headers=headers)
    assert resp.status_code == 201, resp.text

    payload = resp.json()
    assert "cart_id" in payload
    assert "item" in payload





# @pytest.mark.asyncio
# async def test_add_to_cart_user_logged(ac_client):

#     only_device_headers = {"X-Device-Token" : plain_device_session_admin}

#     only_auth_headers = {"Authorization" : "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMTk5NTIzYS02NDc5LTdkZWUtOTRkNy02NjdjZTU1Yjg1MmUiLCJpYXQiOjE3NTk1MDI5NzYsImV4cCI6MTc1OTUwNjU3NiwianRpIjoiOTExM2M0MDliMDE0OTVlM2QzZGE4MmNlOWQ3ZjY1ZjkwN2U1Y2FkYjBhNWMzMWQ1ZTg5ODlmMzRlYWU3YzA4OSIsInJvbGVzIjpbNF0sInJvbGVfdmVyc2lvbiI6MH0.MM2mvvUZVLL7E8xhjdi-5pQDXYqDzS04DQfxqsC8-x0"}

#     headers = {"Authorization" : "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMTk5NTIzYS02NDc5LTdkZWUtOTRkNy02NjdjZTU1Yjg1MmUiLCJpYXQiOjE3NTk1MDI5NzYsImV4cCI6MTc1OTUwNjU3NiwianRpIjoiOTExM2M0MDliMDE0OTVlM2QzZGE4MmNlOWQ3ZjY1ZjkwN2U1Y2FkYjBhNWMzMWQ1ZTg5ODlmMzRlYWU3YzA4OSIsInJvbGVzIjpbNF0sInJvbGVfdmVyc2lvbiI6MH0.MM2mvvUZVLL7E8xhjdi-5pQDXYqDzS04DQfxqsC8-x0",
#                "X-Device-Token" : plain_device_session_admin}

#     # 2) call add-to-cart endpoint (device cookie is created by middleware automatically)
#     resp = await ac_client.post(f"/api/v1/cart/items/0199a984-e686-71e6-ac75-b6a39394adc9",headers=only_auth_headers)
#     assert resp.status_code == 201, resp.text

#     payload = resp.json()
#     assert "cart_id" in payload
#     assert "item" in payload
    # assert payload["item"]["quantity"] == 2

    # r2 = await ac_client.post(f"/api/v1/cart/items/0199a984-e686-71e6-ac75-b6a39394adc9")
    # assert r2.status_code == 201
    # payload = r2.json()
    # assert payload["item"]["quantity"] == 16



# python -m pytest tests/test_carts.py
# ================================================================ test session starts ================================================================

# configfile: pytest.ini
# plugins: asyncio-1.2.0, anyio-4.10.0
# asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
# collected 1 item                                                                                                                                    

# tests/test_carts.py .                                                                          [100%]


# @pytest.mark.asyncio
# async def test_add_to_cart_user_not_loggedin(ac_client):

#     only_device_headers = {"X-Device-Token" : plain_device_session_admin}

#     # 2) call add-to-cart endpoint (device cookie is created by middleware automatically)
#     resp = await ac_client.post(f"/api/v1/cart/items/0199a984-e686-71e6-ac75-b6a39394adc9",headers=only_device_headers)
#     assert resp.status_code == 201, resp.text

#     payload = resp.json()
#     assert "cart_id" in payload
#     assert "item" in payload


   