
import asyncio
import httpx
import pytest
import importlib
from httpx import AsyncClient
from asgi_lifespan import LifespanManager
from httpx import ASGITransport
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert 
from backend.common.utils import now
from backend.main import app
from backend.schema.full_schema import InventoryReservation, InventoryReserveStatus
from tests.save_tokens import token_store
from test_tokens import current_user_payload,current_user2_payload
from sqlalchemy.exc import DBAPIError ,IntegrityError
from tests.conftest import db_session
from uuid6 import uuid7

ORDERS_MODULE = "backend.orders.services"

url_prefix="/api/v1"

@pytest.fixture
async def ac_client():
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac

user = current_user2_payload


SECURE_CONFIRM_PATH = f"{url_prefix}/checkout/{{checkout_id}}/secure-confirm"

@pytest.mark.asyncio
async def test_place_order_upi_with_transient_psp_failure_then_success(monkeypatch, ac_client, db_session):

    orders_mod = importlib.import_module(ORDERS_MODULE)
   
    tokens = token_store.get_user_tokens(user["email"])
    ikey = str(uuid7())
    headers = {"Authorization": f"Bearer {tokens['access_token']}", "Idempotency-Key": ikey}

    r_a = await ac_client.post(f"{url_prefix}/checkout/initiate", headers=headers)
    assert r_a.status_code in (200, 201)
    checkout_id = r_a.json().get("data", {}).get("checkout_id") or r_a.json().get("checkout_id")
    assert checkout_id
    print("Initiated checkout:", checkout_id)

    payload = {"payment_method": "UPI"}
    
    order_summary_resp = await ac_client.post(f"{url_prefix}/checkout/{checkout_id}/order-summary", json=payload, headers=headers)

    print("order summary response", order_summary_resp.status_code, order_summary_resp.text)


    orig_retry = orders_mod.retry_payments
    orig_create = orders_mod.create_psp_order

    # call_state to track how many times the underlying func was called
    call_state = {"calls": 0}

    # decorator that wraps the real PSP function so first invocation fails, subsequent calls delegate to original
    def fail_first_wrapper_factory(func):
        async def wrapped(*args, **kwargs):
            call_state["calls"] += 1
            if call_state["calls"] == 1:
                # Simulate a transient network error on first attempt
                raise httpx.ConnectError("simulated connect error (test-first-call)")
            # Delegate to the real implementation afterwards (real network call)
            return await func(*args, **kwargs)
        return wrapped

    # Now create a fake retry_payments which wraps the provided func with our fail-first wrapper,
    # then delegates to the original retry_payments so all DB bookkeeping remains intact.
    def fake_retry_payments(func, payment_id, session):
        # wrap the incoming func so it fails first then delegates to func
        wrapped_func = fail_first_wrapper_factory(func)
        # call the original retry_payments with the wrapped func
        # keep the same defaults — pass through max_retries/backoff_base if provided
        return orig_retry(wrapped_func, payment_id, session)

    # Patch retry_payments *before* the endpoint runs
    monkeypatch.setattr(orders_mod, "retry_payments", fake_retry_payments, raising=True)
        

    resp = await ac_client.post(f"{url_prefix}/checkout/{checkout_id}/secure-confirm", headers=headers)
    # You expect a success if PSP sandbox responds
    assert resp.status_code == 200, f"expected 200 after retry; got {resp.status_code}: {resp.text}"
    # assert call_state["calls"] >= 2, "PSP post should have been called at least twice"
    # optionally inspect response body
    print("response:", resp.json())
    
    res = await db_session.execute(text("SELECT id, response_code, response_body FROM idempotencykey WHERE key = :k"), {"k": ikey})
    ik_row = res.one_or_none()
    assert ik_row[2] is not None, "idempotency record should be present"
    

    # await db_session.execute(text("DELETE FROM checkoutsession"))
    # await db_session.execute(text("DELETE FROM idempotencykey WHERE key = :k"), {"k": ikey})
    # await db_session.execute(text("DELETE FROM paymentattempt"))
    # await db_session.execute(text("DELETE FROM orders"))
    # await db_session.execute(text("DELETE FROM inventoryreservation"))
    # await db_session.execute(text("DELETE FROM payment"))
    # await db_session.commit()

   