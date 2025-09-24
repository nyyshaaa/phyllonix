
from backend.main import app
import pytest
from httpx import ASGITransport, AsyncClient
from asgi_lifespan import LifespanManager
from unittest.mock import patch
from sqlalchemy.exc import OperationalError
from test_users import user1_email,user1_pass

url_prefix="/api/v1"

@pytest.mark.anyio
async def test_login_db_connection_error():
    # Patch get_session to always raise OperationalError
    async def fake_get_session(*args, **kwargs):
        raise OperationalError("DB down", None, None)

    # Patch the dependency in the router
    # with patch("backend.db.dependencies.get_session", fake_get_session):
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            payload = {"email": user1_email, "password": user1_pass}
            response = await ac.get(f"{url_prefix}/auth/health")
            assert response.status_code in (500, 503)