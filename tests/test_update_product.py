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

headers = {"Authorization": "Bearer "}

@pytest.mark.asyncio
async def test_patch_product(ac_client):

    product_publid_id =  "0199a984-e686-71e6-ac75-b6a39394adc9"

    payload = {"base_price": 500}
    resp = await ac_client.patch(f"/api/v1/admin/products/{product_publid_id}", json=payload, headers=headers)
    assert resp.status_code == 200



@pytest.mark.asyncio
async def test_patch_product_not_found(ac_client):
  
    public_id = "0199a984-e686-71e6-ac75-b6a3939"

    payload = {"base_price": 2500}

    resp = await ac_client.patch(f"/api/v1/admin/products/{public_id}", json=payload, headers=headers)
    assert resp.status_code == 404

headers_diff_user = {"Authorization": "Bearer "}

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
    
   
    