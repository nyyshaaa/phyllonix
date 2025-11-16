
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

# .with_for_update(of=Product, nowait=False)  add and remove this in capture cart snapshot to take direct xclusive lock or don't 

@pytest.mark.asyncio
async def test_two_users_concurrent_order_summary_reservation(ac_client):
    """
    Two different users try to reserve the same product concurrently.
    Product total qty = 6. User A requests 3 units, User B requests 6 units.
    Exactly one should succeed (reservation wins), the other must fail due to insufficient stock.
    """

        
    user1_tokens = token_store.get_user_tokens(user1["email"])
    user2_tokens = token_store.get_user_tokens(user2["email"])
    user_a_headers = {"Authorization": f"Bearer {user1_tokens['access_token']}"}
    user_b_headers = {"Authorization": f"Bearer {user2_tokens['access_token']}"}

    # Each user initiates checkout (separate checkouts)
    r_a = await ac_client.post(f"{url_prefix}/checkout/initiate", headers=user_a_headers)
    r_b = await ac_client.post(f"{url_prefix}/checkout/initiate", headers=user_b_headers)
    assert r_a.status_code in (200, 201)
    assert r_b.status_code in (200, 201)

    checkout_a = r_a.json().get("data", {}).get("checkout_id") or r_a.json().get("checkout_id")
    checkout_b = r_b.json().get("data", {}).get("checkout_id") or r_b.json().get("checkout_id")
    assert checkout_a
    assert checkout_b
    print("Initiated checkouts:", checkout_a, checkout_b)

    payload = {"payment_method": "UPI"}

    # Call order-summary for both users concurrently to create the real contention window.
    #    We intentionally do not await the first before calling the second.
    coro_a = ac_client.post(f"{url_prefix}/checkout/{checkout_a}/order-summary", json=payload, headers=user_a_headers)
    coro_b = ac_client.post(f"{url_prefix}/checkout/{checkout_b}/order-summary", json=payload, headers=user_b_headers)

    res_a, res_b = await asyncio.gather(coro_a, coro_b)
    print("Order-summary responses codes:", res_a.status_code, res_b.status_code)
    print("User-a body:", res_a.text)
    print("User-b body:", res_b.text)

    # Evaluate results: ensure exactly one success and one failure.
    success_codes = {200, 201}
    error_codes_expected = {400,409}  # adapt depending on your implementation

    a_ok = res_a.status_code in success_codes
    b_ok = res_b.status_code in success_codes

    assert not (a_ok and b_ok), "Both users succeeded but product stock should prevent this (6 total, requests 3 & 6)"
    assert a_ok or b_ok, "Neither user succeeded - unexpected (one should succeed given stock=6)"

    # Ensure the failing response is a meaningful error (insufficient stock / conflict)
    if a_ok:
        assert res_b.status_code in error_codes_expected
        print("user-a succeeded, user-b failed as expected")
    else:
        assert res_a.status_code in error_codes_expected
        print("user-b succeeded, user-a failed as expected")


# user_authdata {'user_id': 19, 'sid': None, 'revoked': None}
# [3]
# user_identifier 19
# user_authdata {'user_id': 18, 'sid': None, 'revoked': None}
# [3]
# user_identifier 18
# cs_id 74
# cs_id 74
# in update checkout part  74
# req 19 reserved items for checkout 019a54e6-565c-74bf-be97-828b763ef0a5 with payment method UPI
# Order-summary responses codes: 200 409
# User-a body: {"status":"ok","data":{"checkout_id":"019a54e6-565c-74bf-be97-828b763ef0a5","selected_payment_method":"UPI","items":[{"cart_item_id":13,"product_id":25,"quantity":5,"prod_base_price":500,"product_stock":1000},{"cart_item_id":15,"product_id":530,"quantity":5,"prod_base_price":500,"product_stock":6}],"summary":{"subtotal":5000,"tax":100,"shipping":50,"cod_fee":0,"discount":0,"total":5150}},"error":null,"trace_id":null}
# User-b body: {"detail":{"errors":[{"detail":"Not enough stock for product 530: requested=5, available=1"}]}}
# user-a succeeded, user-b failed as expected



# --------------------------------------------------------
# >       assert not (a_ok and b_ok), "Both users succeeded but product stock should prevent this (6 total, requests 3 & 6)"
# E       AssertionError: Both users succeeded but product stock should prevent this (6 total, requests 3 & 6)
# E       assert not (True and True)
