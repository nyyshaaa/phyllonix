
import asyncio
from backend.main import app
import pytest
from httpx import ASGITransport, AsyncClient
from asgi_lifespan import LifespanManager
from sqlalchemy.exc import OperationalError
from backend.db import dependencies as db_deps

url_prefix="/api/v1"

@pytest.fixture
async def ac_client():
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac

async def fake_get_session_raise():
    raise OperationalError("DB down", None, None)

@pytest.mark.asyncio
async def test_db_connection_error(ac_client):

    # app.dependency_overrides[db_deps.get_session] = fake_get_session_raise
    
    for i in range(3):
        response = await ac_client.get(f'{url_prefix}/auth/retries_cb_test')
        assert response.status_code == 503
    

    response = await ac_client.get(f'{url_prefix}/auth/retries_cb_test')
    assert response.status_code == 500

    await asyncio.sleep(10)

    response = await ac_client.get(f'{url_prefix}/auth/retries_cb_test')
    assert response.status_code == 503

    response = await ac_client.get(f'{url_prefix}/auth/retries_cb_test')
    assert response.status_code == 500
    

    # app.dependency_overrides.pop(db_deps.get_session, None)