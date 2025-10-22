
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request,status
from fastapi.params import Query

from backend.db.dependencies import get_session
from backend.products.dependency import require_permissions
from backend.products.models import ProductCreateIn, ProductRead, ProductUpdateIn, ProductsPage
from sqlalchemy.ext.asyncio import AsyncSession

from backend.products.repository import fetch_prods, patch_product, product_by_public_id, replace_catgs, validate_catgs
from backend.products.services import create_product_with_catgs
from backend.image_uploads.routes import prod_images_router
from backend.products.utils import decode_cursor, encode_cursor
from backend.schema.full_schema import Product


prods_public_router=APIRouter()
prods_admin_router=APIRouter()

prods_admin_router.include_router(prod_images_router)

@prods_admin_router.post("/", dependencies=[require_permissions("product:create")])
async def create_product(request:Request,payload: ProductCreateIn, session: AsyncSession = Depends(get_session)):

    user_identifier=request.state.user_identifier
   
    product_res=await create_product_with_catgs(session,payload,user_identifier)
    return {"message":"product created","product":product_res}

#** not tested yet
@prods_admin_router.patch("/{product_public_id}", dependencies=[require_permissions("product:update")])
async def update_product(request:Request,product_public_id: str,
                         payload: ProductUpdateIn, session: AsyncSession = Depends(get_session)):
                         
    cat_ids=await validate_catgs(session,payload.category_ids)
    user_identifier=request.state.user_identifier

    product = await product_by_public_id(session, product_public_id, user_identifier)

    if product.owner_id!=user_identifier:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authorized to update.")

    updates = payload.model_dump(exclude_unset=True)
    updates.pop("category_ids")

    product_id = await patch_product(session, updates, user_identifier,product.id)

    await replace_catgs(session,product_id,cat_ids)

    return {"message":"product updated"}

#** currently using created at to sort products , later chnage it to use popularity score .
@prods_public_router.get("/products", response_model=ProductsPage)
async def get_products(
    limit: int = Query(20, ge=1, le=100),
    cursor: Optional[str] = Query(None, description="Opaque signed cursor token"),
    session: AsyncSession = Depends(get_session)):
    
    token = cursor
    # decode cursor if present
    cursor_vals = None
    if token:
        # errors if any will be raised at decode cursor level 
        prod_created_at, last_prod_id = decode_cursor(token, max_age=24*3600)  # optional max_age
        cursor_vals = (prod_created_at, last_prod_id)
        
    rows = await fetch_prods(session,cursor_vals,limit)

    has_more = len(rows) > limit
    page_rows = rows[:limit]

    items_out = []
    for p in page_rows:
        m = p._mapping  # SQLAlchemy Row -> mapping of selected columns
        items_out.append({
            "id": str(m["id"]),
            "name": m["name"],
            "price": int(m["price"] or 0),
            "created_at": m["created_at"].isoformat()
        })

    next_cursor = None
    if has_more:
        last = page_rows[-1]._mapping
        next_cursor = encode_cursor(last.created_at, last.id, ttl_seconds=3600)
    
    response = {"items": items_out, "next_cursor": next_cursor, "has_more": has_more}
    return response

