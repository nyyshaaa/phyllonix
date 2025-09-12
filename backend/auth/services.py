from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from fastapi import HTTPException,status
from backend.auth.repository import get_user_role_names, identify_device_session, identify_user, save_refresh_token,  user_id_by_email
from backend.auth.utils import REFRESH_TOKEN_EXPIRE_DAYS, create_access_token, hash_password, hash_token, make_refresh_plain, make_session_token_plain, verify_password
from backend.schema.full_schema import Users,Role, UserRole,Credential,CredentialType, DeviceSession
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


#** create partial index on email 
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


async def save_device_state(session,request,user_id,payload):

    # gather device metadata
    ua = request.headers.get("user-agent", "")[:512]
    ip = None
    if request.client:
        ip = request.client.host

    device_name = payload.device_name or (ua.split(")")[0] if ua else "unknown")
    device_type = payload.device_type or "browser"
    device_id = payload.device_id  

    # create device session row + session token (opaque) and store hashed form
     
    #** check if to mix device fingerprint in creating device session 
    session_token_plain = make_session_token_plain()
    print("plain session",session_token_plain)
    session_token_hash = hash_token(session_token_plain)

    ds = DeviceSession(
        session_token_hash=session_token_hash,
        device_name=device_name,
        device_type=device_type,
        user_agent_snippet=ua[:512],
        device_fingerprint_hash=None if not device_id else hash_token(f"{device_id}|{ua[:200]}"),
        ip_first_seen=ip,
        last_seen_ip=ip,
        last_activity_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        session_expires_at=datetime.now(timezone.utc) + timedelta(days=int(config_settings.DEVICE_SESSION_EXPIRE_DAYS))
    )
    session.add(ds)
    await session.flush()  # get ds.id

    print("ds_id",ds.id)

    return ds.id
        

async def issue_auth_tokens(session,request,payload,device_session):
    user=await identify_user(session,payload.email,payload.password)
    user_id=user.id
    print("user_id",user_id)
    
    session_id=None
    if device_session:
        session_id=await identify_device_session(session,device_session)
    
    # create device session , refresh token and save
    if not session_id:
        session_id=await save_device_state(session,request,user_id,payload)

    refresh_token=await save_refresh_token(session,session_id,user_id)
    
    
    await session.commit()
    # create access token with public_id
    user_roles=await get_user_role_names(session,user_id)
    access_token = create_access_token(user_id=user.public_id, ds_id=session_id,user_roles=user_roles)

    return access_token,refresh_token




