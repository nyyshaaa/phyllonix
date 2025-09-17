


from fastapi import HTTPException
from sqlalchemy import select, text
from backend.schema.full_schema import Product, ProductCategory


async def create_product_with_catgs(session,payload,user_id):

    cat_ids = payload.category_ids or []
    if cat_ids:
        q = await session.execute(select(ProductCategory.id).where(ProductCategory.id.in_(cat_ids)))
        found_ids = {r[0] for r in q.all()}
        missing = [cid for cid in cat_ids if cid not in found_ids]
        if missing:
            raise HTTPException(status_code=404, detail=f"Category ids not found: {missing}")
        cat_ids = [cid for cid in cat_ids if cid in found_ids]
     
    product = Product(
        name=payload.name,
        description=payload.description,
        base_price=payload.base_price,
        stock_qty=payload.stock_qty,
        sku=payload.sku,
        specs=payload.specs,
        owner_id=user_id
    )

    session.add(product)
    await session.flush()
    

    # Bulk insert product_category_link (single statement)
    if cat_ids:
        # Build parameterized VALUES list
        # e.g. VALUES (:p0_prod, :p0_cat), (:p1_prod, :p1_cat), ...
        values_parts = []
        params = {}
        for i, cid in enumerate(cat_ids):
            values_parts.append(f"(:p{i}_prod_id, :p{i}_cat_id)")
            params[f"p{i}_prod_id"] = product.id
            params[f"p{i}_cat_id"] = cid

        values_sql = ", ".join(values_parts)
        insert_sql = f"""
            INSERT INTO product_category_link (product_id, prod_category_id)
            VALUES {values_sql}
            ON CONFLICT (product_id, prod_category_id) DO NOTHING
        """
        await session.execute(text(insert_sql), params)

    # Commit once (atomic)
    await session.commit()
    await session.refresh(product)
    return {
        "public_id": str(product.public_id),
        "name": product.name,
        "base_price": product.base_price,
        "stock_qty": product.stock_qty,
        "sku": product.sku,
        "category_ids": cat_ids,
    }