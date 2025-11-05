
from sqlalchemy import select, text, update
from backend.auth.utils import verify_password
from fastapi import HTTPException,status
from backend.schema.full_schema import Credential,CredentialType,Role, UserRole,Users,DeviceAuthToken,AuthMethod,DeviceSession
from datetime import datetime, timedelta, timezone
from backend.auth.utils import REFRESH_TOKEN_EXPIRE, hash_token, make_refresh_plain, verify_password


async def user_by_email(session,email):
    stmt=select(Users.id,Users.public_id,Users.role_version).where(Users.email==email,Users.deleted_at.is_(None))
    result=await session.execute(stmt)
    user=result.first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email provided is not valid")
    return user


async def user_id_by_email(session,email):
    stmt=select(Users.id).where(Users.email==email,Users.deleted_at.is_(None))
    result=await session.execute(stmt)
    user=result.first()
    return user

async def identify_user(session,email,password):
    email = email.strip().lower()
    user=await user_by_email(session,email)

    stmt= select(Credential.password_hash).where(Credential.user_id == user.id, Credential.type == CredentialType.PASSWORD)
    pwd_hash = (await session.execute(stmt)).first()[0]
    print("pwd_hash",pwd_hash)
    
    if not pwd_hash or not verify_password(password, pwd_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    
    return user

async def save_refresh_token(session,ds_id,user_id,revoked_by):
    now = datetime.now(timezone.utc)
    await session.execute(
        update(DeviceAuthToken)
        .where(
            DeviceAuthToken.device_session_id == ds_id,
            DeviceAuthToken.user_id == user_id,
            DeviceAuthToken.revoked_at.is_(None)
        )
        .values(revoked_at = now, revoked_by = revoked_by)
    )

    # create hashed refresh token , Insert new refresh token
    refresh_plain = make_refresh_plain()
    refresh_hash = hash_token(refresh_plain)
    
    refresh_row = DeviceAuthToken(
        device_session_id=ds_id,
        user_id=user_id,
        auth_method=AuthMethod.PASSWORD,
        token_hash=refresh_hash,
        issued_at=now,
        expires_at=now + timedelta(days=REFRESH_TOKEN_EXPIRE),
        revoked_at=None
    )
    session.add(refresh_row)
    
    print("refresh plain",refresh_plain)
    return refresh_plain

async def get_user_role_ids(session,user_id):
    stmt=select(Role.id).join(UserRole,Role.id==UserRole.role_id).where(UserRole.user_id==user_id)
    result = await session.execute(stmt)
    return result.scalars().all()

async def identify_device_session(session,device_session):
    device_session_hash=hash_token(device_session)
    stmt=select(DeviceSession.id,DeviceSession.revoked_at,DeviceSession.user_id
                ).where(DeviceSession.session_token_hash==device_session_hash).with_for_update()
    res= await session.execute(stmt)
    res = res.one_or_none()
    return {"id":res[0],"revoked_at":res[1],"user_id":res[2]}

async def get_device_session(session,device_session,user_id):
    device_session_hash=hash_token(device_session)
    stmt=select(DeviceSession.id,DeviceSession.revoked_at,DeviceSession.session_expires_at
                ).where(DeviceSession.session_token_hash==device_session_hash,DeviceSession.user_id==user_id)
    res= await session.execute(stmt)
    res = res.one_or_none()
    return {"id":res[0],"revoked_at":res[1],"expires_at":res[2]}

async def link_user_device(session,ds_id,user_id):
    stmt = update(DeviceSession).where(DeviceSession.id==ds_id
                                       ).values(user_id=user_id,last_activity_at=datetime.now(timezone.utc))
    res= await session.execute(stmt)

async def get_device_auth(session, token_hash,take_lock: bool = False):
    
    if take_lock:
        stmt = select(DeviceAuthToken).where(DeviceAuthToken.token_hash == token_hash
                                         ).with_for_update()
    else:
        stmt = select(DeviceAuthToken).where(DeviceAuthToken.token_hash == token_hash)
    res = await session.execute(stmt)
    row = res.scalar_one_or_none()
    if not row:
        return None

    return row

async def get_device_session_fields(session, user_id, ds_id):

    stmt = (
        select(
            DeviceSession.id,
            DeviceSession.public_id,
            DeviceSession.user_id,
            DeviceSession.revoked_at,
            DeviceSession.session_expires_at,
            DeviceSession.last_activity_at,
        )
        .where(DeviceSession.id == ds_id,DeviceSession.user_id==user_id)
        .with_for_update()
    )
    res = await session.execute(stmt)
    row = res.first()
    if not row:
        return None
    return {
        "id": row[0],
        "public_id": row[1],
        "user_id": row[2],
        "revoked_at": row[3],
        "session_expires_at": row[4],
        "last_activity_at": row[5],
    }


async def update_device_session_last_activity(session, ds_id: int, now: datetime):
    stmt = (
        update(DeviceSession)
        .where(DeviceSession.id == ds_id)
        .values(last_activity_at=now)
    )
    await session.execute(stmt)

async def fetch_user_claims(session,user_id):
    stmt = (select(
            Users.public_id.label("public_id"),
            Users.role_version,
            UserRole.role_id.label("role_id")
        )
        .select_from(Users)
        .join(UserRole, UserRole.user_id == Users.id)
        .where(
            Users.id==user_id
        ))
    
    res=await session.execute(stmt)
    print("res",res)
    rows=res.all()
    print("rows",rows)

    if not rows:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail="User not found")
    
    first=rows[0]
    role_ids=[r[2] for r in rows]
    
    return {
        "user_public_id": first.public_id,
        "role_version":first.role_version,
        "role_ids": role_ids
    }

async def rotate_refresh_token_value(session,locked_device_auth,now):
    locked_device_auth.revoked_at = now
    locked_device_auth.revoked_by = "rotated"
    locked_device_auth.revoked_reason = "rotation"
    session.add(locked_device_auth)

async def revoke_device_nget_id(session, device_public_id):
    stmt = update(DeviceSession).where(DeviceSession.public_id == device_public_id
                                       ).values(revoked_at=datetime.now(timezone.utc)).returning(DeviceSession.id)
    res = await session.execute(stmt)
    ds_id = res.scalar.one_or_none()
    return ds_id

async def revoke_device_ref_tokens(session,ds_id):
    stmt =  update(DeviceAuthToken
                   ).where(DeviceAuthToken.device_session_id == ds_id
                   ).values(revoked_at=datetime.now(timezone.utc), revoked_by="logout")
    await session.execute(stmt)


async def revoke_device_and_tokens(session, ds_id: int, revoked_by):
    now = datetime.now(timezone.utc)
    await session.execute(
        update(DeviceAuthToken)
        .where(DeviceAuthToken.device_session_id == ds_id,
               DeviceAuthToken.revoked_at.is_(None))
        .values(revoked_at = now, revoked_by = revoked_by)
    )
    await session.execute(
        update(DeviceSession)
        .where(DeviceSession.id == ds_id)
        .values(revoked_at = now)
    )