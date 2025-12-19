
from fastapi import HTTPException , status
from sqlalchemy import insert, select
from uuid6 import uuid7
from backend.common.utils import now
from backend.products.repository import add_product_categories
from backend.schema.full_schema import Product
from sqlalchemy.exc import IntegrityError
from backend.products.constants import logger

async def create_product_with_catgs(session, payload, user_id, user_pid):
    values = {
        "public_id": uuid7(),
        "name": payload.name,
        "base_price": payload.base_price,
        "stock_qty": payload.stock_qty,
        "description":payload.description,
        "sku":payload.sku,
        "specs":payload.specs,
        "owner_id": user_id,
        "created_at": now(),
        "updated_at": now(),
    }

    stmt = (
        insert(Product)
        .values(**values)
        .on_conflict_do_nothing(index_elements=[Product.name])
        .returning(Product.id, Product.public_id,Product.name,Product.base_price,Product.stock_qty)
    )

    result = await session.execute(stmt)
    row = result.one_or_none()

    if not row:
        logger.warning(
            "product.duplicate_name",
            extra={"name": payload.name, "user": user_pid},
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product with same name already exists",
        )

    product_id, product_pid, name, base_price, stock_qty = row

    if payload.category_names:
        await add_product_categories(session, product_id, product_pid, payload.category_names)

    return {
            "public_id": str(product_pid),
            "name": name,
            "base_price": base_price,
            "stock_qty": stock_qty
        }



