
from fastapi import HTTPException
from sqlalchemy import select, text
from backend.products.repository import add_product_categories, validate_catgs
from backend.schema.full_schema import Product, ProductCategory
from sqlalchemy.exc import IntegrityError


async def create_product_with_catgs(session,payload,user_id):

    cat_ids=await validate_catgs(session,payload.category_ids)
     
    product = Product(
        name=payload.name,
        description=payload.description,
        base_price=payload.base_price,
        stock_qty=payload.stock_qty,
        sku=payload.sku,
        specs=payload.specs,
        owner_id=user_id
    )

    try:
        session.add(product)
        await session.flush()
         
        await add_product_categories(session,product.id, cat_ids)

        await session.commit()
        await session.refresh(product)
    except IntegrityError:
        await session.rollback()
        res = await session.execute(
            select(Product).where(Product.owner_id == user_id, Product.name == payload.name)
        )
        product = res.scalar_one_or_none()
        if product is None:
            raise HTTPException(status_code=500, detail="Product with this name already exists")
        await add_product_categories(session,product.id, cat_ids)
        await session.commit()


    return {
        "public_id": str(product.public_id),
        "name": product.name,
        "base_price": product.base_price,
        "stock_qty": product.stock_qty,
        "sku": product.sku,
        "category_ids": cat_ids,
    }