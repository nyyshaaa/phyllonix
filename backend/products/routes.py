
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request,status
from fastapi.params import Query

from backend.cache.cache_get_n_set import cache_get_or_set_product_listings
from backend.cache.cache_prod_details import cache_get_n_set_product_details
from backend.common.utils import build_success, json_ok, success_response
from backend.db.dependencies import get_session
from backend.products.constants import PRODUCT_LIST_TTL
from backend.products.dependency import require_permissions
from backend.products.models import ProductCreateIn, ProductUpdateIn
from sqlalchemy.ext.asyncio import AsyncSession

from backend.products.repository import fetch_prod_details, fetch_prods, find_product_by_pid, patch_product, replace_catgs, validate_catgs
from backend.products.services import create_product_with_catgs
from backend.image_uploads.routes import prod_images_router
from backend.products.utils import decode_cursor, encode_cursor, make_params_key, validate_uuid
from backend.schema.full_schema import Product


prods_public_router=APIRouter()
prods_admin_router=APIRouter()

prods_admin_router.include_router(prod_images_router)

@prods_admin_router.post("/", dependencies=[require_permissions("product:create")])
async def create_product(request:Request,payload: ProductCreateIn, session: AsyncSession = Depends(get_session)):

    user_identifier=request.state.user_identifier
   
    product_res=await create_product_with_catgs(session,payload,user_identifier)
    resp = {"message":"product created","product":product_res}
    return success_response(resp, status_code=status.HTTP_201_CREATED)
    

@prods_admin_router.patch("/{product_public_id}", dependencies=[require_permissions("product:update")])
async def update_product(request:Request,payload: ProductUpdateIn, product_public_id: str,
                          session: AsyncSession = Depends(get_session)):
    validate_uuid(product_public_id)
    cat_ids=await validate_catgs(session,payload.category_ids)

    user_identifier=request.state.user_identifier

    product = await find_product_by_pid(session, product_public_id, user_identifier)

    if product["product_owner_id"] != user_identifier:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update.")

    updates = payload.model_dump(exclude_unset=True)
    updates.pop("category_ids",None)

    product_pid = await patch_product(session, updates, user_identifier, product["product_id"])

    # if cat_ids is not None:
    #     await replace_catgs(session,product_id,cat_ids)
    await session.commit()

    resp =  {"message":f"product {product_pid} updated"}
    return success_response(resp)

#** currently using created at to sort products , later chnage it to use popularity score .
@prods_public_router.get("")
async def get_products(
    limit: int = Query(20, ge=1, le=100),
    cursor: Optional[str] = Query(None, description="Opaque signed cursor token"),
    q: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session)):
    
    token = cursor
    canonical_cursor_key: str = "start"  # first page
    # decode cursor if present
    cursor_vals = None
    if token:
        prod_created_at, last_prod_id = decode_cursor(token, max_age=24*3600)  # optional max_age
        cursor_vals = (prod_created_at, int(last_prod_id))
        canonical_cursor_key = f"{prod_created_at.isoformat()}_{int(last_prod_id)}"

    key_suffix = make_params_key(limit, canonical_cursor_key, q, category)

    print("Cursor values:", cursor_vals)
        
    async def loader():
        rows = await fetch_prods(session,cursor_vals,limit)

        has_more = len(rows) > limit
        page_rows = rows[:limit]

        items_out = []
        for p in page_rows:
            m = p._mapping  # SQLAlchemy Row -> mapping of selected columns
            items_out.append({
                "id": str(m["id"]),
                "public_id": str(m["public_id"]),
                "name": m["name"],
                "price": int(m["base_price"] or 0),
                "created_at": m["created_at"].isoformat()
            })

        next_cursor = None
        if has_more:
            last = page_rows[-1]._mapping
            next_cursor = encode_cursor(last.created_at, last.id, ttl_seconds=3600)

        response = {"items": items_out, "next_cursor": next_cursor, "has_more": has_more}
        return response
    
    results = await cache_get_or_set_product_listings("products_listing", key_suffix, PRODUCT_LIST_TTL, loader)
    return success_response(results, status_code=status.HTTP_200_OK)


@prods_public_router.get("/{product_public_id}")
async def get_product_details(
    request:Request,
    product_public_id: str,
    session: AsyncSession = Depends(get_session)):
   

    product_details = await cache_get_n_set_product_details(session, product_public_id,fetch_prod_details)
    return success_response(product_details, status_code=status.HTTP_200_OK)
     

    

 
