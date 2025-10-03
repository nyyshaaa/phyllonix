


from fastapi import HTTPException,status
from sqlalchemy import insert, select, update
from backend.schema.full_schema import Cart, CartItem, Product
from sqlalchemy.exc import IntegrityError


async def get_or_create_cart(session,user_id,session_id):
    if user_id is not None:
       
        stmt = select(Cart.id).where(Cart.user_id == user_id)
        res = await session.execute(stmt)
        cart_id = res.scalar_one_or_none()
        if cart_id:
            return cart_id

        # create cart 
        cart = Cart(user_id=user_id)
        session.add(cart)
        try:
            await session.commit()
            await session.refresh(cart)
            return cart.id
        except IntegrityError:
            await session.rollback()
            stmt = select(Cart.id).where(Cart.user_id == user_id).limit(1)
            res = await session.execute(stmt)
            cart_id = res.scalar_one_or_none()
            return cart_id

    # fallback: session (guest) cart
    if session_id is not None:
        stmt = select(Cart.id).where(Cart.session_id == session_id).limit(1)
        res = await session.execute(stmt)
        cart_id = res.scalar_one_or_none()
        if cart_id is not None:
            return cart_id

        cart = Cart(session_id=session_id)
        session.add(cart)
        try:
            await session.commit()
            await session.refresh(cart)
            return cart.id
        except IntegrityError:
            await session.rollback()
            stmt = select(Cart.id).where(Cart.session_id == session_id).limit(1)
            res = await session.execute(stmt)
            cart_id = res.scalar_one_or_none()
            return cart_id


async def get_product_data(session,product_pid):
    stmt = select(Product.id,Product.base_price,Product.stock_qty).where(Product.public_id == product_pid)
    res = await session.execute(stmt)
    row = res.one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    product = {"id": row[0], "base_price": row[1], "stock_qty": row[2]}
    return product


async def add_item_to_cart(session,cart_id,product_data,max_item_qty=1000):
    stmt = (
            select(CartItem.id,CartItem.quantity)
            .where(CartItem.cart_id == cart_id, CartItem.product_id == product_data["id"])
            .with_for_update()
            .limit(1)
        )
    res = await session.execute(stmt)
    row = res.one_or_none()

    if row:
        existing_id, existing_qty = row[0], row[1], row[2]
        if product_data["stock_qty"]==0:  # if concurrent requests and the addd to cart was not disabled before requests arrive at backend 
            new_qty = existing_qty   # simply don't increase qty , later client will disbale ui 
        new_qty = existing_qty + 1
        if new_qty > max_item_qty :
            new_qty = max_item_qty
            
        upd = (
                update(CartItem)
                .where(CartItem.id == existing_id)
                .values(quantity=new_qty)
                .returning(CartItem.id, CartItem.quantity)
            )
        upd_res = await session.execute(upd)
        updated_row = upd_res.one() 
        return (
            {
                "id": int(updated_row[0]),
                "quantity": int(updated_row[1]),
                "unit_price_snapshot": int(updated_row[2]),
            },
            False,
        )
        
    ins = (
        insert(CartItem)
        .values(
            cart_id=cart_id,
            product_id=product_data["id"],
            unit_price_snapshot=product_data["base_price"],
        )
        .returning(CartItem.id, CartItem.quantity, CartItem.unit_price_snapshot)
    )
    ins_res = await session.execute(ins)
    inserted_row = ins_res.one()
    return (
        {
            "id": int(inserted_row[0]),
            "quantity": int(inserted_row[1]),
            "unit_price_snapshot": int(inserted_row[2]),
        },
        True,
    )





