
from typing import Optional
from sqlalchemy import Tuple, insert, select, text, update
from uuid6 import uuid7
from backend.auth.utils import verify_password
from fastapi import HTTPException,status
from backend.common.utils import now
from backend.schema.full_schema import Credential,CredentialType,Role, UserRole,Users,DeviceAuthToken,AuthMethod,DeviceSession
from datetime import datetime, timedelta, timezone
from backend.auth.utils import REFRESH_TOKEN_EXPIRE, hash_token, make_refresh_plain, verify_password
from backend.auth.constants import logger
from backend.config.settings import config_settings
from sqlalchemy.exc import IntegrityError

async def user_by_email(session,email):
    stmt=select(Users.id,Users.public_id,Users.role_version).where(Users.email==email,Users.deleted_at.is_(None))
    result=await session.execute(stmt)
    user=result.first()
    if not user:
        logger.warning("auth.user.not_found", extra={"email": email})
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
    
    if not pwd_hash or not verify_password(password, pwd_hash):
        logger.warning("auth.user.invalid_credentials", extra={"email": email, "user_public_id": str(user.public_id)})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    
    return user

async def create_credential(session,user_id: int,password_hash: str):
   
    provider = config_settings.SELF_PROVIDER

    values = {
        "user_id": user_id,
        "type": CredentialType.PASSWORD ,
        "provider": provider,
        "password_hash": password_hash,
        "created_at": now(),
        "updated_at": now(),
    }

    stmt = (
        insert(Credential)
        .values(**values)
        .on_conflict_do_nothing(index_elements=[Credential.user_id, Credential.provider])
        .returning(Credential.id)
    )

    try:
        result = await session.execute(stmt)
        cred_id = result.scalar_one_or_none()
        if cred_id:
            logger.debug("credential.created", extra={"cred_id": cred_id, "user_id": user_id, "provider": provider})
            return cred_id

        res = await session.execute(
            select(Credential.user_id).where(
                Credential.user_id == user_id,
                Credential.provider == provider,
            )
        )
        existing = res.scalar_one_or_none()
        if existing:
            logger.debug("credential.already_exists", extra={"user_id": user_id, "provider": provider})
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Credentials exist already for the current provider")

        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Credential conflict — please retry")

    except IntegrityError as exc:
        await session.rollback()
        logger.warning("credential.integrity_error.other")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unexpected DB Integrity error")

async def create_n_get_user(session,email,name):
   
    user_values = {
        "public_id": uuid7(),
        "email": email ,
        "name": name ,
        "created_at": now(),
        "updated_at": now(),
    }

    user_insert = (
        insert(Users)
        .values(**user_values)
        .on_conflict_do_nothing(index_elements=[Users.email])
        .returning(Users.id, Users.public_id)
    )

    try:
        result = await session.execute(user_insert)
        row = result.one_or_none()
        if row:
            user_pid = row[1]
            logger.info("user.inserted", extra={"user_id": user_pid, "email": email})
            return {"id":row[0],"public_id":row[1]}
        else:
            res = await session.execute(
                select(Users.email).where(Users.email == email)
            )
            existing = res.scalar_one_or_none()
            if existing:
                logger.info("user.duplicate.email", extra={"email": existing})
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"User with email {existing} already exists")
            
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User creation conflict , unexpected , retry")
    except IntegrityError as exc:
        await session.rollback()
        logger.warning("create_user.integrity_error.other")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Integrity error while creating user")

async def revoke_all_tokens_per_user(session,user_id,revoked_by):
    now = datetime.now(timezone.utc)
    await session.execute(
        update(DeviceAuthToken)
        .where(
            DeviceAuthToken.user_id == user_id,
            DeviceAuthToken.revoked_at.is_(None)
        )
        .values(revoked_at = now, revoked_by = revoked_by)
    )


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
    
    return refresh_plain

async def get_user_role_ids(session,user_id):
    stmt=select(Role.id).join(UserRole,Role.id==UserRole.role_id).where(UserRole.user_id==user_id)
    result = await session.execute(stmt)
    return result.scalars().all()

async def identify_device_session(session,device_session):
    device_session_hash=hash_token(device_session)
    stmt=select(DeviceSession.id,DeviceSession.revoked_at,DeviceSession.user_id,DeviceSession.public_id
                ).where(DeviceSession.session_token_hash==device_session_hash).with_for_update()
    res= await session.execute(stmt)
    res = res.one_or_none()
    return {"id":res[0],"revoked_at":res[1],"user_id":res[2],"public_id":res[3]}

async def get_device_session_by_pid(session,session_pid,user_id):
    stmt=select(DeviceSession.id,DeviceSession.revoked_at,DeviceSession.session_expires_at
                ).where(DeviceSession.public_id==session_pid,DeviceSession.user_id==user_id)
    res= await session.execute(stmt)
    res = res.one_or_none()
    return {"id":res[0],"revoked_at":res[1],"session_expires_at":res[2]}

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
    rows=res.all()

    first=rows[0]

    if not rows:
        logger.warning("auth.user.claims_not_found")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,detail="User not found")
    
    
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