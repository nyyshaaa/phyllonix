from sqlalchemy import select
from sqlalchemy.ext.asyncio import  AsyncSession

from backend.api.default_roles import DEFAULT_ROLES
from backend.schema.full_schema import Role


async def seed_roles(session: AsyncSession):
    for r in DEFAULT_ROLES:
        q = await session.execute(select(Role).where(Role.name == r["name"]))
        role = q.scalar_one_or_none()
        if not role:
            role = Role(name=r["name"], description=r["description"])
            session.add(role)
    await session.commit()