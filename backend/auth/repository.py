
from sqlalchemy import select
from backend.auth.utils import verify_password
from fastapi import HTTPException,status
from backend.schema.full_schema import Credential,CredentialType,Role, UserRole,Users,DeviceAuthToken,AuthMethod
from datetime import datetime, timedelta, timezone
from backend.auth.utils import REFRESH_TOKEN_EXPIRE_DAYS, hash_token, make_refresh_plain, verify_password


#* update it as per partial index
async def user_by_email(session,email):
    stmt=select(Users.id,Users.public_id).where(Users.email==email)
    result=await session.execute(stmt)
    user=result.first()
    return user

async def user_id_by_email(session,email):
    stmt=select(Users.id).where(Users.email==email)
    result=await session.execute(stmt)
    user=result.first()
    return user

async def identify_user(session,email,password):
    email = email.strip().lower()
    user=await user_by_email(session,email )

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email provided is not valid")
    
    stmt= select(Credential.password_hash).where(Credential.user_id == user.id, Credential.type == CredentialType.PASSWORD)
    pwd_hash = (await session.execute(stmt)).first()[0]
    print("pwd_hash",pwd_hash)
    
    if not pwd_hash or not verify_password(password, pwd_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    
    return user

async def save_refresh_token(session,ds_id,user_id):
    # create hashed refresh token (rotation pattern)
    refresh_plain = make_refresh_plain()
    refresh_hash = hash_token(refresh_plain)
    now = datetime.now(timezone.utc)
    refresh_row = DeviceAuthToken(
        device_session_id=ds_id,
        user_id=user_id,
        auth_method=AuthMethod.PASSWORD,
        token_hash=refresh_hash,
        issued_at=now,
        expires_at=now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        revoked_at=None
    )
    session.add(refresh_row)
    return refresh_plain

async def get_user_role_names(session,user_id):
    stmt=select(Role.name).join(UserRole,Role.id==UserRole.role_id).where(UserRole.user_id==user_id)
    result = await session.execute(stmt)
    return result.scalars().all()


