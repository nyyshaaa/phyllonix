

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.dependencies import get_session
from backend.schema.full_schema import Permission, Role, RolePermission


def require_permissions(perm:str):
    async def _checker(request: Request,
        session: AsyncSession = Depends(get_session),):
        user_roles=set(request.state.user_roles)
        
        # check if the required permisssion belongs to any user roles .
        stmt=(
            select(RolePermission.id)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .where(Permission.name == perm,RolePermission.role_id.in_(list(user_roles))).limit(1)
        )
        
        res=await session.execute(stmt)
        res=res.scalar_one_or_none()

        if not res:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail="User doesn't have any permissions")
        
        return True
        
    return Depends(_checker)



