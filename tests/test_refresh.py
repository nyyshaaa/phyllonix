
from backend.main import app
import asyncio
import pytest
from httpx import ASGITransport, AsyncClient
from asgi_lifespan import LifespanManager
from test_tokens import refresh_token_user3 , access_token_user3
from tests.save_tokens import token_store

url_prefix="/api/v1"

@pytest.fixture
async def ac_client():
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac

current_user = ""

@pytest.mark.asyncio
async def test_refresh(ac_client):
    
    user_tokens = token_store.get_user_tokens(current_user["email"])

    res = await ac_client.post(f"{url_prefix}/auth/refresh", headers={"X-Refresh-Token": user_tokens["refresh_token"],
                                                "Authorization": f"Bearer {user_tokens["access_token"]}"})

    assert res.status_code == 200 
    body = res.json()
    access_token = body.get("message", {}).get("access_token")
    refresh_token = body.get("message", {}).get("refresh_token")

    user_tokens.update({
        "refresh_token": refresh_token,
        "access_token" : access_token
    })

    token_store.store_user_tokens(current_user["email"], user_tokens)

# tested and verified , commented to not run for every file run 
# @pytest.mark.asyncio
# async def test_concurrent_refresh_allows_benign_revoked(ac_client):
   
#     # fire concurrent refresh requests
#     async def do_refresh():
#         return await ac_client.post(f"{url_prefix}/auth/refresh", headers={"X-Refresh-Token": refresh_token_user3,
#                                                 "Authorization": f"Bearer {access_token_user3}"})

#     tasks = [asyncio.create_task(do_refresh()) for _ in range(3)]
#     results = await asyncio.gather(*tasks)

#     # all should be 200
#     assert all(r.status_code == 200 for r in results)






