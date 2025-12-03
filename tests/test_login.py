
from backend.auth.constants import COOKIE_NAME
from backend.main import app
import pytest
import os
from dotenv import load_dotenv
from httpx import ASGITransport, AsyncClient
from asgi_lifespan import LifespanManager
from test_tokens import current_user_payload,current_user2_payload
from tests.save_tokens import token_store

load_dotenv()

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

url_prefix="/api/v1"

@pytest.fixture
async def ac_client():
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac

# @pytest.fixture
# async def ac_client(ac_client):
#     """Returns an AsyncClient with an initialized session"""
#     resp = await ac_client.post(f"{url_prefix}/session/init")
#     assert resp.status_code == 200
#     return ac_client

current_user_payload = current_user2_payload
current_user_payload = {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}

@pytest.mark.asyncio
async def test_login(ac_client):

    email = current_user_payload["email"]
    password = current_user_payload["password"]
   
    user_tokens = token_store.get_user_tokens(email)
    headers = {"X-Device-Token": user_tokens["session_token"]}

    # perform login; cookie jar will include session_token automatically
    payload = {"email": email, "password": password}
    resp = await ac_client.post(f"{url_prefix}/auth/login", json=payload,headers=headers)
    assert resp.status_code == 200

    print("\nResponse status:", resp.status_code)
    print("Response body:", resp.json())
    print("Response headers:", dict(resp.headers))
    print("Client cookies:", dict(ac_client.cookies))

    # server should set refresh cookie on login
    refresh_cookie = ac_client.cookies.get(COOKIE_NAME)
    print("Refresh Token Cookie:", refresh_cookie)
    assert refresh_cookie is not None

    # access protected API using access token from response body (or cookie)
    body = resp.json()["data"]
    access_token = body.get("message", {}).get("access_token")
    refresh_token = body.get("message", {}).get("refresh_token")

    user_tokens.update({
        "refresh_token": refresh_token,
        "access_token" : access_token
    })
    token_store.store_user_tokens(current_user_payload["email"], user_tokens)

    assert access_token  # ensure returned
    assert refresh_token  # ensure returned in dev env
    print("Access Token:", access_token)
    print("Refresh Token:", refresh_token)
