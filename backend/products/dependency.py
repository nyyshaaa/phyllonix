
import select
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.dependencies import get_session
from backend.schema.full_schema import Permission, Role, RolePermission


async def require_permissions(perm:str):
    async def _checker(request: Request,
        session: AsyncSession = Depends(get_session),):
        user_roles=set(request.state.user_roles)
        
        # check if the required permisssion belongs to any user roles .
        stmt=select(Role.id
            ).join(RolePermission.permission_id==Permission.id
            ).join(Role.id==RolePermission.role_id
            ).where(Permission.name==perm,Role.name.in_(user_roles)).limit(1) 
        
        res=await session.execute(stmt)
        res=res.scalar_one_or_none()

        if not res:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail="User doesn't have any permissions")
        
        return True
        
    return Depends(_checker)



