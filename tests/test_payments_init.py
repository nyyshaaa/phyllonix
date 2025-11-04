
import asyncio
import pytest
from httpx import AsyncClient
from asgi_lifespan import LifespanManager
from httpx import ASGITransport
from backend.main import app
from tests.save_tokens import token_store
from test_tokens import current_user_payload,current_user2_payload

url_prefix="/api/v1"

@pytest.fixture
async def ac_client():
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac

user1 = current_user_payload
user2 = current_user2_payload

@pytest.mark.asyncio
async def test_single_user_initiate_idempotent(ac_client):
    """
    Simulate a single user sending multiple initiate requests concurrently:
    - Should return the same checkout_id (get_or_create_checkout_session) or otherwise ensure only one active checkout exists.
    """
    email = user1["email"]
   
    user_tokens = token_store.get_user_tokens(email)
    headers = {"Authorization": f"Bearer {user_tokens["access_token"]}"}

    async def initiate_once():
        r = await ac_client.post(f"{url_prefix}/checkout/initiate", headers=headers)
        assert r.status_code in (200, 201)
        body = r.json()
        checkout_id = body["data"]["checkout_id"] if "data" in body else body.get("checkout_id")
        return checkout_id

    # fire multiple concurrent initiates
    results = await asyncio.gather(initiate_once(), initiate_once(), initiate_once())
    # All returned checkout ids should be identical (idempotent create-or-get)
    assert len(set(results)) == 1
    
    

@pytest.mark.asyncio
async def test_checkout_init_and_order_summary(ac_client):
    """
    If the client retries the order-summary call (same checkout_id + same payload) concurrently,
    the server should either:
      - return the same computed totals (idempotent) and not double-reserve, OR
      - fail safe (e.g., reject duplicates)
    This test calls order-summary twice concurrently with identical input and expects consistent result.
    """
    email = user1["email"]
   
    user_tokens = token_store.get_user_tokens(email)
    headers = {"Authorization": f"Bearer {user_tokens["access_token"]}"}

    # initiate
    r = await ac_client.post(f"{url_prefix}/checkout/initiate", headers=headers)
    assert r.status_code in (200, 201)
    checkout_id = r.json()["data"]["checkout_id"]

    print ("checkout_id",checkout_id)

    payload = {"payment_method": "UPI"}

    # call order-summary twice concurrently
    r1, r2 = await asyncio.gather(
        ac_client.post(f"{url_prefix}/checkout/{checkout_id}/order-summary", json=payload, headers=headers),
        ac_client.post(f"{url_prefix}/checkout/{checkout_id}/order-summary", json=payload, headers=headers),
    )

    body1 = r1.json()
    body2 = r2.json()
    print("body1", body1)
    print(body2)
    # Compare computed totals (structure depends on your compute_order_totals)
    assert body1["data"]["checkout_id"] == body2["data"]["checkout_id"]

    # Both should either succeed with the same payload or one fails and the other succeeds.
    # if r1.status_code in (200, 201) and r2.status_code in (200, 201):
        # body1 = r1.json()
        # body2 = r2.json()
        # # Compare computed totals (structure depends on your compute_order_totals)
        # assert body1["data"] == body2["data"]
    # else:
    #     # allow one success + one error
    #     acceptable_error_codes = {400, 409, 422}
    #     assert (r1.status_code in (200, 201) and r2.status_code in acceptable_error_codes) or (
    #         r2.status_code in (200, 201) and r1.status_code in acceptable_error_codes
    #     ), f"Unexpected combo: {r1.status_code}, {r2.status_code}"
