
from datetime import datetime
from typing import Optional
from fastapi import HTTPException,status
from sqlalchemy import and_, desc, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import selectinload , load_only
from backend.common.utils import now
from backend.schema.full_schema import Product, ProductCategory, ProductCategoryLink
from backend.products.constants import logger

async def add_product_categories(session, product_id, product_pid, cat_names):

    cat_names = list({name.strip() for name in cat_names})

    stmt = (
        select(ProductCategory.id)
        .where(ProductCategory.name.in_(cat_names))
    )

    result = await session.execute(stmt)
    cat_ids = result.scalars().all()

    if len(cat_ids) != len(set(cat_names)):
        logger.warning(
            "product.category.invalid_names",
            extra={
                "product_pid":product_pid,
                "provided": cat_names,
                "resolved_count": len(cat_ids),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="One or more categories do not exist",
        )

    rows = [
        {"product_id": product_id, "prod_category_id": cid}
        for cid in cat_ids
    ]

    stmt = (
        insert(ProductCategoryLink)
        .values(rows)
        .on_conflict_do_nothing(
            index_elements=[
                ProductCategoryLink.product_id,
                ProductCategoryLink.prod_category_id,
            ]
        )
    )

    await session.execute(stmt)

async def find_product_by_pid(session, product_pid):
    stmt = select(Product.id, Product.owner_id).where(Product.public_id == product_pid,Product.deleted_at.is_(None),)

    res = await session.execute(stmt)
    product = res.one_or_none()

    if not product:
        logger.warning("product.not_found",extra={"product_public_id": product_pid},)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="Product not found")

    return {
        "product_id": product[0],
        "product_owner_id": product[1],
    }


#** images not joined for now .
#** may use postgres specific single query join and aggregate for better perf .
async def fetch_product_details(session, product_public_id: str):
    stmt = (
        select(Product)
        .options(
            load_only(
                Product.id,
                Product.public_id,
                Product.stock_qty,
                Product.name,
                Product.description,
                Product.base_price,
                Product.specs,
                Product.updated_at,
            ),
            selectinload(Product.prod_categories).load_only(
                ProductCategory.id,
                ProductCategory.name,
            ),
        )
        .where(
            Product.public_id == product_public_id,
            Product.deleted_at.is_(None),
        )
    )

    res = await session.execute(stmt)
    product = res.scalar_one_or_none()

    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    return {
        "public_id": str(product.public_id),
        "stock_qty": product.stock_qty,
        "name": product.name,
        "description": product.description,
        "base_price": product.base_price,
        "specs": product.specs,
        "updated_at": product.updated_at,
        "categories": [
            {"id": c.id, "name": c.name}
            for c in product.prod_categories
        ],
    }

async def patch_product(session, updates, user_id, user_pid, product_id):
    stmt = (
        update(Product)
        .where(Product.id == product_id,Product.owner_id == user_id,Product.deleted_at.is_(None),)
        .values(**updates, updated_at=now())
        .returning(Product.public_id)
    )

    res = await session.execute(stmt)
    product_pid = res.scalar_one_or_none()

    if not product_pid:   # check here to account for race between deletes and updates etc , like if any request deletes after we initially did a select check.
        logger.warning(
            "product.update.not_found_or_unauthorized",
            extra={ "user": user_pid},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found ",
        )

    return product_pid


async def validate_categories_by_names(session,category_names: Optional[list[str]],) -> list[int]:
  
    if not category_names:
        return []

    unique_names = list({name.strip() for name in category_names})

    stmt = (
        select(ProductCategory.id, ProductCategory.name)
        .where(ProductCategory.name.in_(unique_names))
    )

    result = await session.execute(stmt)
    rows = result.all()

    found_by_name = {name: cid for cid, name in rows}

    missing = [name for name in unique_names if name not in found_by_name]

    if missing:
        logger.warning(
            "category.not_found",
            extra={"missing_cat_names": missing},
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Categories not found: {missing}",
        )

    return list(found_by_name.values())


async def replace_catgs(session,product_id,cat_ids):
    await session.execute(
        ProductCategoryLink.delete().where(ProductCategoryLink.product_id == product_id)
    )
    
    await add_product_categories(session,product_id, cat_ids)


def keyset_filter(created_at_val: datetime, last_id: str):
    
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

