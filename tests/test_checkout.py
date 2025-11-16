
import asyncio
import pytest
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

ORDERS_MODULE = "backend.orders.routes"

url_prefix="/api/v1"

@pytest.fixture
async def ac_client():
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac

# user1 = current_user_payload
user2 = current_user2_payload

# Import the orders module and monkeypatch reserve_inventory in it
import importlib

orders_mod = importlib.import_module(ORDERS_MODULE)


# error is swallowed that is not raised(bubbled up first time) or re raised after catching, 
# but it will cause session in a bad state if not rolled back, so any further code won't execute and will automatically raise some error, 
# and if no further code then it will exit and bad state won't get saved even if we don't use session.rollaback()
@pytest.mark.asyncio
async def test_swallowed_error_without_session_rollback(monkeypatch, ac_client , db_session):

    async def broken_reserve_inventory_bad_type(session, cart_items, cs_id, reserved_until):
        try:
            # Real DB error: division by zero in Postgres
            await session.execute(text("SELECT 1/0"))
            # (if the DB didn't error, we would proceed to insert — but it will)
        except DBAPIError as db_err:
            # Swallowing the real DB error WITHOUT rollback (bad)
            return

    monkeypatch.setattr(orders_mod, "reserve_inventory", broken_reserve_inventory_bad_type)


    user1_tokens = token_store.get_user_tokens(user2["email"])
    user_a_headers = {"Authorization": f"Bearer {user1_tokens['access_token']}"}

    r_a = await ac_client.post(f"{url_prefix}/checkout/initiate", headers=user_a_headers)
    assert r_a.status_code in (200, 201)
    checkout_id = r_a.json().get("data", {}).get("checkout_id") or r_a.json().get("checkout_id")
    assert checkout_id
    print("Initiated checkout:", checkout_id)

    payload = {"payment_method": "UPI"}
    with pytest.raises(DBAPIError):
         await ac_client.post(f"{url_prefix}/checkout/{checkout_id}/order-summary", json=payload, headers=user_a_headers)


    row = await db_session.execute(
        text("SELECT cart_snapshot, selected_payment_method FROM checkoutsession WHERE public_id = :pubid"),
        {"pubid": checkout_id},
    )
    cs = row.first()
    assert cs is not None
    cart_snapshot, selected_payment_method = cs[0], cs[1]

    # Assert that the checkout was NOT updated (preferred behavior)
    assert cart_snapshot is None or cart_snapshot == {}, "Expected no cart_snapshot when reserve swallowed error"
    assert selected_payment_method is None, "Expected no selected_payment_method when reserve swallowed error"

    await db_session.execute(text("DELETE FROM checkoutsession"))
    await db_session.commit()


# again same way error is swallowed but session.rollback() , so it also won't save db state for thye block which caused error , but this way further code will execute without any error
@pytest.mark.asyncio
async def test_swallowed_error(monkeypatch, ac_client , db_session):
    
    async def broken_reserve_inventory_bad_type(session, cart_items, cs_id, reserved_until):
        try:
            await session.execute(text("SELECT 1/0"))
        except DBAPIError as db_err:
            await session.rollback()
            return

    monkeypatch.setattr(orders_mod, "reserve_inventory", broken_reserve_inventory_bad_type)


    user1_tokens = token_store.get_user_tokens(user2["email"])
    user_a_headers = {"Authorization": f"Bearer {user1_tokens['access_token']}"}

    r_a = await ac_client.post(f"{url_prefix}/checkout/initiate", headers=user_a_headers)
    assert r_a.status_code in (200, 201)
    checkout_id = r_a.json().get("data", {}).get("checkout_id") or r_a.json().get("checkout_id")
    assert checkout_id
    print("Initiated checkout:", checkout_id)

    payload = {"payment_method": "UPI"}
    
    order_summary_resp = await ac_client.post(f"{url_prefix}/checkout/{checkout_id}/order-summary", json=payload, headers=user_a_headers)


    print("response status after swallowed Error:", order_summary_resp.status_code, order_summary_resp.text)

    row = await db_session.execute(
        text("SELECT cart_snapshot, selected_payment_method FROM checkoutsession WHERE public_id = :pubid"),
        {"pubid": checkout_id},
    )
    cs = row.first()
    assert cs is not None
    cart_snapshot, selected_payment_method = cs[0], cs[1]

    assert cart_snapshot is not None
    assert selected_payment_method is not None
    await db_session.execute(text("DELETE FROM checkoutsession"))
    await db_session.commit()

@pytest.mark.asyncio
async def test_reserve_inventory_swallowed_error(monkeypatch, ac_client , db_session):
    
    async def broken_reserve_inventory(session,cart_items,cs_id,reserved_until):

        to_insert = []

        for it in cart_items:
            print("cs_id",cs_id)
            row = {
                "product_id": int(it["product_id"]),
                "checkout_id": cs_id,  
                "quantity": int(it["quantity"]),
                "reserved_until": reserved_until,
                "status": InventoryReserveStatus.ACTIVE.value,
                "created_at": now(),
            }
            to_insert.append(row)

        insert_stmt = insert(InventoryReservation).values(to_insert)
        insert_stmt = insert_stmt.on_conflict_do_nothing(index_elements=["product_id","checkout_id"]).returning(InventoryReservation.id)

        res = await session.execute(insert_stmt)

        try:
            res = res.scalar_one_or_none()
            await session.execute(text("SELECT 1/0"))
            await session.commit()   
        except DBAPIError as db_err:
            return
        
        print("inv_id",res)
           
    monkeypatch.setattr(orders_mod, "reserve_inventory", broken_reserve_inventory)


    user1_tokens = token_store.get_user_tokens(user2["email"])
    user_a_headers = {"Authorization": f"Bearer {user1_tokens['access_token']}"}

    r_a = await ac_client.post(f"{url_prefix}/checkout/initiate", headers=user_a_headers)
    assert r_a.status_code in (200, 201)
    checkout_id = r_a.json().get("data", {}).get("checkout_id") or r_a.json().get("checkout_id")
    assert checkout_id
    print("Initiated checkout:", checkout_id)

    payload = {"payment_method": "UPI"}
    
    with pytest.raises(DBAPIError):
        await ac_client.post(f"{url_prefix}/checkout/{checkout_id}/order-summary", json=payload, headers=user_a_headers)
    
    row = await db_session.execute(
        text("SELECT cart_snapshot, selected_payment_method FROM checkoutsession WHERE public_id = :pubid"),
        {"pubid": checkout_id},
    )
    cs = row.first()
    assert cs is not None
    cart_snapshot, selected_payment_method = cs[0], cs[1]

    # Assert that the checkout was NOT updated (preferred behavior)
    assert cart_snapshot is None or cart_snapshot == {}, "Expected no cart_snapshot when reserve swallowed error"
    assert selected_payment_method is None, "Expected no selected_payment_method when reserve swallowed error"

    await db_session.execute(text("DELETE FROM checkoutsession"))
    await db_session.commit()
   

    