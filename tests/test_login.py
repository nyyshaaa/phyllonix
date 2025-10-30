
from backend.main import app
import pytest
from httpx import ASGITransport, AsyncClient
from asgi_lifespan import LifespanManager
from test_tokens import strong_pass3 , test_user3_email

url_prefix="/api/v1"

@pytest.fixture
async def ac_client():
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac

@pytest.fixture
async def session_client(ac_client):
    """Returns an AsyncClient with an initialized session"""
    resp = await ac_client.post(f"{url_prefix}/session/init")
    assert resp.status_code == 200
    return ac_client

@pytest.mark.asyncio
async def test_login(session_client):

    email = test_user3_email
    password = strong_pass3
    # create a user via signup (or create in DB directly)
    # await create_test_user(ac_client, email=email, password=password)

    # print("Session token before login:", session_client.cookies.get("session_token"))

    cookies = {"session_token": session_client.cookies.get("session_token")}

    # perform login; cookie jar will include session_token automatically
    payload = {"email": email, "password": password}
    resp = await session_client.post(f"{url_prefix}/auth/login", json=payload,cookies=cookies)
    assert resp.status_code == 200

    print("\nResponse status:", resp.status_code)
    print("Response body:", resp.json())
    print("Response headers:", dict(resp.headers))
    print("Client cookies:", dict(session_client.cookies))

    # server should set refresh cookie on login
    refresh_cookie = session_client.cookies.get("refresh")
    assert refresh_cookie is not None

    # access protected API using access token from response body (or cookie)
    body = resp.json()
    access_token = body.get("message", {}).get("access_token")
    assert access_token  # ensure returned


