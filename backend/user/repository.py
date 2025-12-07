
from typing import List
from fastapi import HTTPException,status
from sqlalchemy import delete, select, update
from backend.auth.utils import hash_token
from backend.common.utils import now
from backend.schema.full_schema import Credential, CredentialType, DeviceSession, Role, RoleAudit, UserMedia, UserRole,Users
from sqlalchemy.exc import IntegrityError


async def userid_by_public_id(session,user_pid):
    stmt=select(Users.id).where(Users.public_id==user_pid)
    res=await session.execute(stmt)
    user=res.first()
    return user[0] if user else None


async def check_user_roles_version(session,identifier,role_version):
    stmt=select(Users.role_version).where(Users.id==identifier,Users.role_version==role_version)
    res=await session.execute(stmt)
    user=res.first()
    return user[0] if user else None

async def device_active(session,ds_id):
    stmt=select(DeviceSession.id).where(DeviceSession.id==ds_id,DeviceSession.revoked_at==None)
    res=await session.execute(stmt)
    ds=res.first()
    return ds[0] if ds else None

# for now only profile image exists for 1 user . there is a unique constraint on user_id fkey in user_media
#*WARN update added in same endpoint as of post just for faster testing of queue system.
async def save_user_avatar(session, user_id: int, image_path: str,final_path:str):
    new=UserMedia(user_id=user_id, profile_img_path=image_path)
    session.add(new)
    try:
        # flush sends INSERT to DB so new.id is populated (but not committed)
        await session.flush()
        media_id = new.id
        await session.commit()
        return media_id
    except IntegrityError:    #**** just for testing remove update from post endpoint  
        print("integrity here")
        await session.rollback()
        stmt = (
            update(UserMedia)
            .where(UserMedia.user_id == user_id)    # since one user has only one profile allowed and user id fkey is unique .
            .values(
                profile_image_url=image_path,
                profile_image_thumb_url=None
            ).returning(UserMedia.id)
        )
        res=await session.execute(stmt)
        res=res.first()[0]
        await session.commit()
        print(res)
        return res
    except Exception as e:
        print("save error",e)
        final_path.unlink(missing_ok=True)
        await session.rollback()
        #log e 
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save avatar")



async def user_n_ds_by_public_id(session,user_pid,ds_token):
    if not ds_token:
        stmt=select(Users.id).where(Users.public_id==user_pid,Users.deleted_at==None)
        res=await session.execute(stmt)
        user=res.first()
        user= {"user_id":user[0],"sid":None,"revoked":None}
        return user

    ds_token__hash=hash_token(ds_token)
    stmt=select(Users.id,DeviceSession.id,DeviceSession.revoked_at).join(DeviceSession,DeviceSession.user_id==Users.id
                               ).where(Users.public_id==user_pid,Users.deleted_at==None,
                                       DeviceSession.session_token_hash==ds_token__hash)
    res=await session.execute(stmt)
    user=res.first()
    user= {"user_id":user[0],"sid":user[1],"revoked":user[2]}
    return user


async def identify_user_by_pid(session,user_pid):
   
    stmt=select(Users.id).where(Users.public_id==user_pid,Users.deleted_at==None)
    res=await session.execute(stmt)
    user_id=res.scalar_one_or_none()
    return user_id

async def get_password_credential(session,user_id):
    stmt=select(Credential.password_hash,Credential.revoked_at).where(
        Credential.user_id==user_id,Credential.type==CredentialType.PASSWORD)
    res=await session.execute(stmt)
    res=res.one_or_none()
    if not res:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unexpected,No credential found for user")  # emit events to deal with this
    if res[1] is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User password credential revoked")
    
    return res[0]

async def update_password(session, user_id, new_hash):
    stmt=(
        update(Credential)
        .where(
            Credential.user_id==user_id,
            Credential.type==CredentialType.PASSWORD,
            Credential.revoked_at==None
        )
        .values(
            password_hash=new_hash,
            updated_at=now()
        ).returning(Credential.id)
    )
    res = await session.execute(stmt)
    cred_id = res.scalar_one_or_none()
    return cred_id

async def get_role_ids_by_names(session, role_names: List[str]):
    """Get role IDs from role names"""
    stmt = select(Role.id, Role.name).where(Role.name.in_(role_names))
    result = await session.execute(stmt)
    roles = result.scalars().all()
    if not roles or len(roles) != len(role_names):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"One or more role names are invalid"
        )
    role_map = {name: role_id for role_id, name in roles}
    return role_map


async def change_user_roles(session, user_id: int, cur_role_ids,new_role_names: List[str], actor_user_id: int, reason: str | None = None):
    """Change user roles and create audit entry"""
    new_role_names_ids_map = await get_role_ids_by_names(session, new_role_names)
    if cur_role_ids:
        delete_stmt = delete(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.role_id.in_(cur_role_ids)
        )
        await session.execute(delete_stmt)
    
    # Add new roles
    for role_name in new_role_names:
        role_id = new_role_names_ids_map[role_name]
        new_user_role = UserRole(user_id=user_id, role_id=role_id)
        session.add(new_user_role)
    
    # Increment role_version
    update_stmt = (
        update(Users)
        .where(Users.id == user_id)
        .values(role_version=Users.role_version + 1, updated_at=now())
    )
    await session.execute(update_stmt)
    
    await session.flush()



    



