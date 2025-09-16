
import asyncio
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from sqlmodel import select
from sqlalchemy.ext.asyncio.session import AsyncSession

from backend.auth.utils import verify_password

try:
    from backend.db.connection import async_session
    from backend.schema.full_schema import Users, Credential, CredentialType, Role, UserRole
    from backend.auth.services import hash_password  
except Exception as e:
    raise RuntimeError("Update import paths in seed_scripts/seed_admin.py to match your project") from e
# -------------------------------------------------------------------

load_dotenv()


async def create_admin():
    admin_email = os.environ.get("ADMIN_EMAIL")
    admin_password = os.environ.get("ADMIN_PASSWORD")
    admin_name = os.environ.get("ADMIN_NAME", "Admin")

    if not admin_email or not admin_password:
        raise SystemExit("Set ADMIN_EMAIL and ADMIN_PASSWORD environment variables before running")

    async with async_session() as session:
        # 1) find or create user
        q = await session.execute(select(Users).where(Users.email == admin_email))
        user = q.scalar_one_or_none()

        if not user:
            user = Users(email=admin_email, name=admin_name)
            session.add(user)
            await session.commit()
            await session.refresh(user)
            print(f"Created user id={user.id} public_id={getattr(user,'public_id',None)}")
        else:
            print(f"Found existing user id={user.id} public_id={getattr(user,'public_id',None)}")

        q = await session.execute(select(Credential).where(Credential.user_id == user.id, Credential.type == CredentialType.PASSWORD))
        cred = q.scalar_one_or_none()
        pwd_hash = hash_password(admin_password)

        if not cred:
            cred = Credential(user_id=user.id, type=CredentialType.PASSWORD, password_hash=pwd_hash)
            session.add(cred)
            await session.commit()
            print("Created password credential for admin user")
        else:
            if not verify_password(admin_password, cred.password_hash):
                raise RuntimeError("Invalid credentials")
            # update password hash (optional; useful for initial bootstrap)

        q = await session.execute(select(Role).where(Role.name == "admin"))
        admin_role = q.scalar_one_or_none()
        if not admin_role:
            raise SystemExit("Admin role missing. Run role/permission migrations first.")

        q = await session.execute(select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == admin_role.id))
        ur = q.scalar_one_or_none()
        if not ur:
            new_link = UserRole(user_id=user.id, role_id=admin_role.id)
            session.add(new_link)
            await session.commit()
            print("Assigned admin role to user")
        else:
            print("User already has admin role")

    print("Done.")

if __name__ == "__main__":
    asyncio.run(create_admin())
