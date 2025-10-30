

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


# @pytest.mark.asyncio
# async def test_session_init_and_use(ac_client: AsyncClient):

#     resp = await ac_client.post(f"{url_prefix}/session/init")
#     assert resp.status_code == 200

#     session_token = resp.cookies.get("session_token")
#     device_public_id = resp.cookies.get("device_public_id")

#     assert session_token is not None
#     print("Session Token:", session_token)
#     assert device_public_id is not None
#     print("Device Public ID:", device_public_id)


# @pytest.mark.asyncio
# async def test_signup(ac_client):
#     payload = {"email": test_user3_email, "password": strong_pass3, "name": "testuser3"}
#     resp = await ac_client.post(f"{url_prefix}/auth/signup", json=payload)
#     assert resp.status_code in (200, 201)
#     data = resp.json()
#     assert "User" in data.get("message", "") or resp.status_code in (200,201)
#     # device cookies should not be created by signup endpoint (unless you choose to)
#     assert ac_client.cookies.get("session_token") is None


# backends/phyllonix$ python -m pytest "tests/tests_signup.py"
# ================================================================== test session starts ===================================================================
# platform linux -- Python 3.12.3, pytest-8.4.2, pluggy-1.6.0
# rootdir: /home/nisha/Desktop/backends/phyllonix
# configfile: pytest.ini
# plugins: asyncio-1.2.0, anyio-4.10.0
# asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
# collected 2 items                                                                                                                                        

# tests/tests_signup.py ..                                                 [100%]


@pytest.mark.asyncio
async def test_login(ac_client):
    # ensure a session exists (server sets cookie)
    # await ac_client.post("/session/init")
    assert ac_client.cookies.get("session_token") is not None

    
    email = test_user3_email
    password = strong_pass3
    # create a user via signup (or create in DB directly)
    # await create_test_user(ac_client, email=email, password=password)

    # perform login; cookie jar will include session_token automatically
    login_payload = {"email": email, "password": password}
    resp = await ac_client.post("/auth/login", json=login_payload)
    assert resp.status_code == 200

    # server should set refresh cookie on login
    refresh_cookie = ac_client.cookies.get("refresh")
    assert refresh_cookie is not None

    # access protected API using access token from response body (or cookie)
    body = resp.json()
    access_token = body.get("message", {}).get("access_token")
    assert access_token  # ensure returned