
from fastapi import APIRouter, Depends, Request , status
from sqlalchemy.ext.asyncio import  AsyncSession
from backend.db.dependencies import get_session

user_router = APIRouter()

#* only admin can see other user's public details
# accessible only to same user 
@user_router.get("/me")
async def get_user_profile(request:Request, session: AsyncSession = Depends(get_session)):
    return {"message":request.state.user_identifier}




