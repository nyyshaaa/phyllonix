

import asyncio
import time
import os

import httpx
from sqlalchemy import text
from backend.db.connection import async_session
from backend.main import app
import pytest
from httpx import ASGITransport, AsyncClient
from asgi_lifespan import LifespanManager
from backend.config.media_config import media_settings
from test_users import BASE_IMG_DISK_PATH

url_prefix="/api/v1"

CLOUD_NAME = media_settings.CLOUDINARY_CLOUD_NAME
CLOUD_API_KEY = media_settings.CLOUDINARY_API_KEY
CLOUD_API_SECRET = media_settings.CLOUDINARY_API_SECRET
CLOUD_UPLOAD_URL = f"https://api.cloudinary.com/v1_1/{CLOUD_NAME}/image/upload"

@pytest.fixture
async def ac_client():
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac


@pytest.mark.asyncio
async def test_full_image_upload_flow(ac_client):

    headers = {"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwMTk5NTIzYS02NDc5LTdkZWUtOTRkNy02NjdjZTU1Yjg1MmUiLCJpYXQiOjE3NTkxNDQ2MjgsImV4cCI6MTc1OTE0ODIyOCwianRpIjoiNDMzM2RkZGYwOTY1ZmU0MDg0NGMxNmQ4YzI4ZDQyMzQzOTBlNjllODc3YzNjN2UwM2ZjNzQzNDg0YjIyMTdjMSIsInJvbGVzIjpbNF0sInJvbGVfdmVyc2lvbiI6MH0.q4-SGslnOpNYRS4UBLtlRC3FaxI-8HGd6sZ3muF56zI"}

    payload = {
        "images":[{
            "filename":f"{BASE_IMG_DISK_PATH}/to_moon_1.jpeg",
            "filesize":"395522",
            "content_type":"image/jpeg",
            "sort_order":1},
            {
            "filename":f"{BASE_IMG_DISK_PATH}/to_moon.jpg",
            "filesize":"1517742",
            "content_type":"image/jpg",
            "sort_order":0}
        ]
    }
    
    # Call init endpoint to get upload params
    resp = await ac_client.post(
        "/api/v1/admin/products/01999496-1c8c-7ada-96ea-80748c54a63f/images/init-batch",
        json=payload,
        headers=headers
    )

    assert resp.status_code == 200

    init_json = resp.json()
    assert "items" in init_json and len(init_json["items"]) >= 1
    items = init_json["items"]

    tasks = [upload_to_cloudinary(item) for item in items]
    await asyncio.gather(*tasks)


async def upload_to_cloudinary(item):
    upload_payload = item["upload_params"]
    params = upload_payload["params"]
    file_path =item["filename"]

    file_path = item["filename"]
    # ensure file exists
    assert os.path.exists(file_path), f"file missing: {file_path}"

    data = {}
    for k, v in upload_payload.items():
        if k == "params" and isinstance(v, dict):
            for pk, pv in v.items():
                if isinstance(pv, bool):
                    # Convert bool to lowercase string ("true"/"false")
                    data[pk] = str(pv).lower()
                else:
                    # Convert int, float, or any non-str type to str
                    data[pk] = str(pv)
        else:
            data[k] = v
    
    res=None
    # print(data)
    with open(file_path, "rb") as f:
        files = {"file": (os.path.basename(file_path), f, "application/octet-stream")}
        async with httpx.AsyncClient() as client:
            res = await client.post(CLOUD_UPLOAD_URL, data=data, files=files, timeout=120.0)
            print(res.text)
    assert res.status_code in (200, 201)
    cl_json = res.json()

    
    public_id = cl_json.get("display_name")
    asset_id = cl_json.get("asset_id")
    version = cl_json.get("version")

    assert public_id or asset_id

    # Wait for webhook processing (poll provider_webhook_events)
    # Provider event id we expect to be asset_id or public_id:version
    provider_event_id = asset_id if asset_id else f"{public_id}:{version}"

    # Poll DB for up to 30 seconds
    found = False
    max_wait = 60.0
    interval = 1.0
    start = time.time()
    async with async_session() as session:
        while time.time() - start < max_wait:
            stmt = text("SELECT id, processed_at, payload FROM providerwebhookevent WHERE provider_event_id = :peid")
            r = await session.execute(stmt, {"peid": provider_event_id})
            row = r.first()
            if row:
                found = True
                processed_flag = row[1]
                # if processed flag is not null, break
                if processed_flag:
                    break
            await asyncio.sleep(interval)

    assert found

   
# python -m pytest tests/test_prod_image_uploads.py
# ================================================================ test session starts ================================================================

# configfile: pytest.ini
# plugins: asyncio-1.2.0, anyio-4.10.0
# asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=function, asyncio_default_test_loop_scope=function
# collected 1 item                                                                                                                                    

# tests/test_prod_image_uploads.py .                                       [100%]
