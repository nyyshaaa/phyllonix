from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from fastapi import HTTPException,status
from uuid6 import uuid7
from backend.auth.repository import fetch_user_claims, get_device_auth, get_device_session_fields, get_user_role_ids, identify_device_session, identify_user, link_user_device, revoke_device_and_tokens, revoke_device_nget_id, revoke_device_ref_tokens, rotate_refresh_token_value, save_refresh_token, update_device_session_last_activity, user_id_by_email
from backend.auth.utils import create_access_token, hash_password, hash_token, make_session_token_plain
from backend.schema.full_schema import Users,Role, UserRole,Credential,CredentialType, DeviceSession,DeviceAuthToken
from sqlalchemy.exc import IntegrityError
from backend.config.settings import config_settings

async def link_user_role(session,user_id):
    # ensure user role exists (idempotent)
    q = select(Role).where(Role.name == config_settings.DEFAULT_ROLE)
    role = (await session.execute(q)).scalar_one_or_none()
    if not role:
        role = Role(name=config_settings.DEFAULT_ROLE)
        session.add(role)
        await session.flush()

    ur = UserRole(user_id=user_id, role_id=role.id)
    session.add(ur)

#* promote roles via a separate endpoint 


async def create_user(session,payload):

    user_id = await user_id_by_email(session,payload["email"])
    if user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User with email already exists")

    # create user + credential + default role (atomic)
    try:
        # create user row
        user = Users(email=payload["email"], name=payload.get("name"))
        session.add(user)
        await session.flush()  # get user.id

        user_id=user.id

        pwd_hash = hash_password(payload["password"])
        # create password credential
        cred = Credential(user_id=user_id, type=CredentialType.PASSWORD, provider=config_settings.SELF_PROVIDER, password_hash=pwd_hash)
        session.add(cred)
        
        # link user role
        await link_user_role(session,user_id)

        #* default email_verified = False in Users model (for email verifications)
        
        await session.commit()
        await session.refresh(user)
        return user.id
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=400, detail="User with that email already exists")


async def save_device_state(session,request,user_id):

    # gather device metadata
    ua = request.headers.get("user-agent", "")[:512]
    ip = None
    if request.client:
        ip = request.client.host

    device_name = (ua.split(")")[0] if ua else "unknown")
    device_type = "browser"

    # create device session row + session token (opaque) and store hashed form
     

    session_token_plain = make_session_token_plain()
    print("plain session",session_token_plain)
    session_token_hash = hash_token(session_token_plain)
    
   
    ds = DeviceSession(
        session_token_hash=session_token_hash,
        user_id=user_id,
        device_name=device_name,
        device_type=device_type,
        user_agent_snippet=ua[:512],
        ip_first_seen=ip,
        last_seen_ip=ip,
        last_activity_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        session_expires_at=datetime.now(timezone.utc) + timedelta(days=int(config_settings.DEVICE_SESSION_EXPIRE_DAYS))
    )
    session.add(ds)
    await session.flush()  # get ds.id

    print("ds_id",ds.id)

    return ds.id,ds.public_id,session_token_plain
        

async def issue_auth_tokens(session,payload,device_session):
    user=await identify_user(session,payload.email,payload.password)
    user_id=user.id
    print(user.public_id)
    
    ds=await identify_device_session(session,device_session)
    print("ds",ds)

    if ds["revoked_at"] is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail="device session is already revoked")

    session_id = ds["id"]

    if not ds["user_id"]:
        await link_user_device(session, session_id, user_id)
        print("linked user to device session")
        
        # await merge_guest_cart_into_user(session, user_id, session_id)

    refresh_token=await save_refresh_token(session,session_id,user_id,revoked_by="new_login")
    await session.commit()

    # Cache: set device:{device_public_id} in Redis (cache-aside). (ADD LATER)
    # await redis.set(f"device:{device_public_id}", {...}, ex=SLIDING_WINDOW_seconds)

    # create access token with public_id
    user_roles=await get_user_role_ids(session,user_id)
    access_token = create_access_token(user_id=user.public_id,user_roles=user_roles,role_version=user.role_version)
     
    return access_token,refresh_token


async def validate_refresh_and_fetch_user(session,plain_token):

    hashed_token=hash_token(plain_token)
    now=datetime.now(timezone.utc)

    # Single-query join: fetch token + user + role rows in one go
    stmt = (
        select(
            Users.public_id.label("public_id"),
            Users.role_version,
            UserRole.role_id.label("role_id")
        )
        .select_from(DeviceAuthToken)
        .join(Users, Users.id == DeviceAuthToken.user_id)
        .join(UserRole, UserRole.user_id == Users.id)
        .where(
            DeviceAuthToken.token_hash == hashed_token,
            DeviceAuthToken.revoked_at.is_(None),
            DeviceAuthToken.expires_at > now)
        )
    
    res=await session.execute(stmt)
    print("res",res)
    rows=res.all()
    print("rows",rows)

    if not rows:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail="Invalid or expired refresh token")
    
    first=rows[0]
    role_ids=[r[2] for r in rows]
    
    return {
        "user_public_id": first.public_id,
        "role_version":first.role_version,
        "role_ids": role_ids
    }

async def validate_refresh_and_update_refresh(session,plain_token,user_id):
    hashed_token=hash_token(plain_token)
    now=datetime.now(timezone.utc)

    device_auth = await get_device_auth(session, hashed_token,user_id)

    if not device_auth:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token or doesn't belong to user")

    if device_auth.expires_at <= now + timedelta(minutes=1):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Refresh token expired")
    
    ds_id = device_auth.device_session_id

    
    ds_row = await get_device_session_fields(session, user_id,ds_id=ds_id)
    if not ds_row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Device session unauthorized or invalid")
    
    if ds_row["revoked_at"] is not None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Device session revoked")
    if ds_row["session_expires_at"] and now >= ds_row["session_expires_at"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session absolute expiry reached")
    
    locked_device_auth = await get_device_auth(session, hashed_token,user_id,take_lock=True)

    # benign_revoked = False
    if locked_device_auth.revoked_at is not None:
        # If revoked_by indicates rotation we consider it benign concurrency (i.e., another concurrent
        # request rotated it). May use 'rotated'/'rotation' or other sentinel values.
        # Another check: if revoked_by == 'user' (explicit logout) treat as non-benign.
        if locked_device_auth.revoked_by in (None, "rotation", "rotated", "rotated_by_device"):
            # assume rotation-style revocation; allow to continue but mark
            benign_revoked = True
        else:
            # revoked by admin/system or marked as 'reuse_detected' => handle as misuse
            # Revoke entire device session and all its tokens (for security) and return 403
            await revoke_device_and_tokens(session, ds_id, revoked_by="reuse_detetction")
            # optionally alert / record security event here
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="Refresh token reuse detected; session revoked")

    if now + timedelta(seconds=40)>= locked_device_auth.expires_at:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")
    
    # rotate: revoke current token and create a new one
    # await rotate_refresh_token_value(session,locked_device_auth,now)  # not required as we already revoke all existing tokens in save refresh_token

    refresh_plain=await save_refresh_token(session,ds_row["id"],user_id,revoked_by="rotation")

    await update_device_session_last_activity(session, ds_row["id"], now)
    
    await session.commit()

    # Post-commit: invalidate device cache (hook for your Redis)
    # await redis.delete(f"device:{ds.public_id}")   # add when you wire redis

    # fetch user to get public_id, role_version if needed (can cache user metadata to avoid DB hit)
    user_claims=await fetch_user_claims(session,user_id)

    return user_claims,refresh_plain
     
    


async def provide_access_token(claims_dict):
    
    access_token = create_access_token(user_id=claims_dict["user_public_id"], 
                                       user_roles=claims_dict["role_ids"],role_version=claims_dict["role_version"])
    return access_token
    

async def get_or_create_device_session(session,request,device_session_plain,user_id):
    if device_session_plain:
        session_id=await identify_device_session(session,device_session_plain)

    # create device session 
    if not device_session_plain :
        session_id=await save_device_state(session,request,user_id)

    return session_id


async def logout_device_session(session,device_public_id):
    now = datetime.now(timezone.utc)

    ds_id = revoke_device_nget_id(session, device_public_id)

    # revoke tokens atomically
    await revoke_device_ref_tokens(session,ds_id)

    await session.commit()

    # invalidate caches (add when integrating Redis)
    # await redis.delete(f"device:{device_public_id}")
    # optionally clear refresh cookie: Set-Cookie header from the client or server response




        
    




