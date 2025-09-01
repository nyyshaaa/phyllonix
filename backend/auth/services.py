from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from fastapi import HTTPException,status
from backend.auth.repository import user_by_email
from backend.auth.utils import REFRESH_TOKEN_EXPIRE_DAYS, create_access_token, hash_password, hash_token, make_refresh_plain, make_session_token_plain, verify_password
from backend.schema.device_session import DeviceAuthToken, DeviceSession
from backend.schema.roles import Role, UserRole
from backend.schema.user import Users
from backend.schema.user_creds import Credential,CredentialType
from sqlalchemy.ext.asyncio import IntegrityError


#** create partial index on email 
async def create_user(session,payload_dict):

    user = await user_by_email(payload_dict['email'], session)
    if user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User with email already exists")

    # create user + credential + default role (atomic)
    try:
        # create user row
        user = Users(email=payload_dict['email'], name=payload_dict['name'])
        session.add(user)
        await session.flush()  # get user.id

        user_id=user.id

        pwd_hash = hash_password(payload_dict['password'])
        # create password credential
        cred = Credential(user_id, type=CredentialType.PASSWORD, provider="phyllonix", password_hash=pwd_hash)
        session.add(cred)

        # ensure user role exists (idempotent)
        #* avoid this check and add roles at app startup
        q = select(Role).where(Role.name == "buyer")
        role = (await session.exec(q)).first()
        if not role:
            role = Role(name="buyer", description="Default user role as buyer")
            session.add(role)
            await session.flush()

        ur = UserRole(user_id, role_id=role.id)
        session.add(ur)

        # default email_verified = False in Users model (ensure the model has that column)
        
        await session.commit()
        await session.refresh(user)
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=400, detail="User with that email already exists")


async def save_device_and_token_state(session,request,user_id,payload):
    # gather device metadata
    ua = request.headers.get("user-agent", "")[:512]
    ip = None
    if request.client:
        ip = request.client.host

    device_name = payload.device_name or (ua.split(")")[0] if ua else "unknown")
    device_type = payload.device_type or "browser"
    device_id = payload.device_id  

    # create device session row + session token (opaque) and store hashed form
    async with session.begin():
        session_token_plain = make_session_token_plain()
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
            session_expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        )
        session.add(ds)
        await session.flush()  # get ds.id

        await save_refresh_token(ds.id)
    
    return ds.id
        
async def save_refresh_token(session,ds_id,user_id):
    # create hashed refresh token (rotation pattern)
    refresh_plain = make_refresh_plain()
    refresh_hash = hash_token(refresh_plain)
    now = datetime.now(timezone.utc)
    refresh_row = DeviceAuthToken(
        device_session_id=ds_id,
        user_id=user_id,
        token_hash=refresh_hash,
        issued_at=now,
        expires_at=now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        revoked_at=None
    )
    session.add(refresh_row)

async def get_user_token(session,request,payload):
    email = payload.email.strip().lower()
    user=await user_by_email(email, session)
    user_id=user.public_id

    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email provided is not valid")
    
    stmt= select(Credential.password_hash).where(Credential.user_id == user_id, Credential.type == CredentialType.PASSWORD)
    pwd_hash = (await session.exec(stmt)).first()
    
    if not pwd_hash or not verify_password(payload.password, pwd_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    
    #* create device session
    ds_id=await save_device_and_token_state(session,request,user_id,payload)

    #* create access token
    # create access token JWT with sid=ds.id (use your existing function)
    access = create_access_token(user_id=user_id, session_id=ds_id)

