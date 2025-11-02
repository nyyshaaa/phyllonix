import asyncio
import pytest
from httpx import AsyncClient
from asgi_lifespan import LifespanManager
from httpx import ASGITransport
from backend.main import app

@pytest.fixture
async def ac_client():
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac

token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMTk5NTIzYS02NDc5LTdkZWUtOTRkNy02NjdjZTU1Yjg1MmUiLCJpYXQiOjE3NjE1ODE3NjEsImV4cCI6MTc2MTU4NTM2MSwianRpIjoiNzUwYmI3ODdlNTVlMGRhZWRhNGI1Y2VlYWViYTkxYjQ5YzJmYWI3MjBkN2U0NjMxNzYxNjgwOWJhZWU3YTdiZiIsInJvbGVzIjpbNF0sInJvbGVfdmVyc2lvbiI6MH0.UPpQws1cVnXoDgLYe6fypszZTo_UplcX0c-8xhDl3kQ"
headers = {"Authorization": f"Bearer {token}"}

@pytest.mark.asyncio
async def test_patch_product(ac_client):

    product_publid_id =  "0199a984-e686-71e6-ac75-b6a39394adc9"

    payload = {"base_price": 500}
    resp = await ac_client.patch(f"/api/v1/admin/products/{product_publid_id}", json=payload, headers=headers)
    assert resp.status_code == 200



# @pytest.mark.asyncio
# async def test_patch_product_not_found(ac_client):
  
#     public_id = "0199a984-e686-71e6-ac75-b"

#     payload = {"base_price": 2500}

#     resp = await ac_client.patch(f"/api/v1/admin/products/{public_id}", json=payload, headers=headers)
#     assert resp.status_code == 404

headers_diff_user = {"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMTk5MDY3Yy00YmZmLTczZjEtYWY5OC05YmZmMThlOGE5YmYiLCJpYXQiOjE3NjE1ODQ2MTQsImV4cCI6MTc2MTU4ODIxNCwianRpIjoiYmM3MGI3ZGEyYjA1ZDE3YmY3OTJmMzg3OGE2ZDcxMjRiZmRjNGY3ZDVjMzExNzkzYWNjMGQzOGM2NzcyYjIzNiIsInJvbGVzIjpbM10sInJvbGVfdmVyc2lvbiI6MH0.WsLwnbVfnssnEGpr4b1XRj5orwHIo2xO-R5R9Q4P9h8"}

# @pytest.mark.asyncio
# async def test_patch_product_not_owner_unauthorized(ac_client):
  
#     product_publid_id =  "0199a984-e686-71e6-ac75-b6a39394adc9"
#     headers = headers_diff_user
#     payload = {"base_price": 2600}

#     resp = await ac_client.patch(f"/api/v1/admin/products/{product_publid_id}", json=payload, headers=headers)
 
#     assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_patch_product_missing_permission(ac_client):
   
    payload = {"base_price": 150}
    product_public_id =  "0199a984-e686-71e6-ac75-b6a39394adc9"
    headers = headers_diff_user

    resp = await ac_client.patch(f"/api/v1/admin/products/{product_public_id}", json=payload, headers=headers)
    assert resp.status_code in (401, 403)
    
   
# configfile: pytest.ini
# plugins: asyncio-1.2.0, anyio-4.10.0
# asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
# collected 2 items                                                                                                                                                                

# tests/test_update_product.py ..                                                                                                     [100%]