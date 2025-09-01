
from sqlalchemy import select
from backend.schema.full_schema import DeviceSession,Users


async def userid_by_public_id(session,user_pid):
    stmt=select(Users.id).where(Users.public_id==user_pid)
    res=await session.exec(stmt)
    user=res.first()
    return user

async def device_active(session,ds_id):
    stmt=select(DeviceSession.id).where(DeviceSession.id==ds_id,DeviceSession.revoked_at==None)
    res=await session.exec(stmt)
    ds=res.first()
    return ds
    
  
