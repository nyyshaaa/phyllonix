
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.dependencies import get_session

carts_router=APIRouter()


@carts_router.post("/items")
async def add_to_cart(request:Request,session:AsyncSession=Depends(get_session)):
    pass
