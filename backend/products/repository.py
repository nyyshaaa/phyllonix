
from fastapi import HTTPException,status
from sqlalchemy import select, text, update

from backend.common.utils import now
from backend.schema.full_schema import Product, ProductCategory, ProductCategoryLink


async def add_product_categories(session,product_id, cat_ids):
    # Bulk insert product_category_link (single statement)
    if cat_ids:
        # Build parameterized VALUES list
        # e.g. VALUES (:p0_prod, :p0_cat), (:p1_prod, :p1_cat), ...
        values_parts = []
        params = {}
        for i, cid in enumerate(cat_ids):
            values_parts.append(f"(:p{i}_prod_id, :p{i}_cat_id)")
            params[f"p{i}_prod_id"] = product_id
            params[f"p{i}_cat_id"] = cid

        values_sql = ", ".join(values_parts)
        insert_sql = f"""
            INSERT INTO productcategorylink (product_id, prod_category_id)
            VALUES {values_sql}
            ON CONFLICT (product_id, prod_category_id) DO NOTHING
        """
        await session.execute(text(insert_sql), params)


async def product_by_public_id(session,product_pid,user_id):
    stmt=select(Product.id,Product.owner_id).where(Product.public_id==product_pid,Product.deleted_at.is_(None))
    res=await session.execute(stmt)
    product=res.one_or_none()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product

async def patch_product(session,updates,product_id):
    stmt = (
    update(Product)
    .where(Product.id == product_id)
    .values(**updates, updated_at=now)
    .returning(Product.id)  
    )

    res = await session.execute(stmt)
    res = res.one_or_none()
    if not res:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return res.id

async def validate_catgs(session,category_ids):
    cat_ids = category_ids or []
    if cat_ids:
        q = await session.execute(select(ProductCategory.id).where(ProductCategory.id.in_(cat_ids)))
        found_ids = {r[0] for r in q.all()}
        missing = [cid for cid in cat_ids if cid not in found_ids]
        if missing:
            raise HTTPException(status_code=404, detail=f"Category ids not found: {missing}")
        cat_ids = [cid for cid in cat_ids if cid in found_ids]
    return cat_ids



async def replace_catgs(session,product_id,cat_ids):
    await session.execute(
        ProductCategoryLink.delete().where(ProductCategoryLink.product_id == product_id)
    )
    
    await add_product_categories(session,product_id, cat_ids)
    
