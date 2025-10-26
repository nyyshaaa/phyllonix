
from datetime import datetime
from fastapi import HTTPException,status
from sqlalchemy import and_, desc, or_, select, text, update
from sqlalchemy.orm import selectinload , load_only
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


async def get_product_ids_by_pid(session,product_pid,user_id):
    stmt=select(Product.id,Product.owner_id).where(Product.public_id==product_pid,Product.deleted_at.is_(None))
    res=await session.execute(stmt)
    product=res.one_or_none()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return {"product_id":product[0],"product_owner_id":product[1]}


#** images not joined for now .
#** may use postgres specific single query join and aggregate for better perf .
async def get_prod_details_imgs_ncats(session, product_id: int):
    q = (
        select(Product)
        .options(
            # load only these columns for Product (SQLAlchemy will still include PK)
            load_only(
                Product.public_id,
                Product.stock_qty,
                Product.name,
                Product.description,
                Product.base_price,
                Product.specs,
            ),
            # fetch categories in a second query
            selectinload(Product.categories).load_only(
                ProductCategory.id,
                ProductCategory.name,
            ),
            # fetch images in a second query
        )
        .where(Product.id == product_id)
    )

    res = await session.execute(q)
    product = res.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    return {
        "public_id": product.public_id,
        "stock_qty": product.stock_qty,
        "name": product.name,
        "description": product.description,
        "base_price": product.base_price,
        "specs": product.specs,
        "categories": [{"id": c.id, "name": c.name} for c in product.categories],
    }

async def get_public_id_by_pid(session,product_pid):
    stmt = select(Product.id).where(Product.public_id==product_pid,Product.deleted_at.is_(None))
    res = await session.execute(stmt)
    return res.scalar_one_or_none()

async def patch_product(session,updates,user_id,product_id):
    stmt = (
    update(Product)
    .where(Product.id == product_id,Product.owner_id==user_id)
    .values(**updates, updated_at=now())
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


def keyset_filter(created_at_val: datetime, last_id: str):
    # ordering: created_at DESC (newest first), id ASC as tiebreaker
    # For rows AFTER the page cursor (i.e., older items), we want:
    #   (created_at < cursor_created_at) OR (created_at = cursor_created_at AND id > last_id)
    return or_(
        Product.created_at < created_at_val,
        and_(Product.created_at == created_at_val, Product.id > last_id)
    )
    

async def fetch_prods(session,cursor_vals,limit):
    stmt = select(Product.id,Product.public_id, Product.name, Product.base_price, Product.created_at)
    if cursor_vals:
        created_at_val, last_id = cursor_vals
        stmt = stmt.where(keyset_filter(created_at_val, last_id))
    # ordering: newest first
    stmt = stmt.order_by(desc(Product.created_at), Product.id).limit(limit + 1)  # fetch one extra to detect has_more

    result = await session.execute(stmt)
    rows = result.all()
    return rows 