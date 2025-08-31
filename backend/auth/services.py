from sqlalchemy import select
from fastapi import HTTPException,status
from backend.auth.repository import user_by_email
from backend.auth.utils import hash_password, verify_password
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


async def get_user_token(payload_dict,session):
    user_id=await user_by_email(payload_dict['email'], session)

    if not user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User doesn't exist")
    
    stmt= select(Credential.password_hash).where(Credential.user_id == user_id, Credential.type == CredentialType.PASSWORD)
    pwd_hash = (await session.exec(stmt)).first()
    if not pwd_hash:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not verify_password(payload_dict["password"], pwd_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    
    #* create device session

    #* create tokens 

