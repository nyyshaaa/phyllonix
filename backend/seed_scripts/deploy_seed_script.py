
import asyncio
from datetime import datetime, timedelta, timezone
import os
import random
from uuid6 import uuid7
import string
from typing import List
from backend.auth.utils import hash_password, hash_token, make_session_token_plain
from backend.common.utils import now
from sqlmodel import SQLModel, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker,AsyncSession
from backend.schema.full_schema import ( 
    Users,
    UserRole,
    Role,
    Permission,
    RolePermission,
    Credential,
    CredentialType,
    Product,
    ProductCategory,
    ProductCategoryLink,
    DeviceSession,
)
from backend.config.settings import config_settings
from backend.db.utils import _normalize_db_url

DATABASE_URL=_normalize_db_url(config_settings.DATABASE_URL)

# ------------------ DB setup ------------------


if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL env var not set")

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
async_session_maker = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async_engine=create_async_engine(DATABASE_URL)

async_session_maker=async_sessionmaker(bind=async_engine,class_=AsyncSession,expire_on_commit=False)

# ------------------ Config ------------------

NUM_USERS = 1000
NUM_PRODUCTS = 500
BATCH_SIZE = 200
PRODUCT_BATCH_COMMIT = 200 

SEED_PASSWORD_TEMPLATE = config_settings.SEED_PASSWORD_TEMPLATE
ADMIN_PASSWORD = config_settings.ADMIN_DEPLOY_TEST_PASSWORD
ADMIN_EMAIL = config_settings.ADMIN_DEPLOY_TEST_EMAIL

PRODUCT_NAMES = [
    "Girl Racing Through Clouds",
    "Cotton Tee - Fly High in Blue",
    "Firefly lights",
    "Wolves and girls painting",
    "Mystical Forest Hoodie",
    "Coconut Orange Chocolate",
    "Pistachio,Peanuts & Rose Energy Ladoo",
    "Matcha Almond Protein Ladoo",
    "Dancing Petals Painting",
]

def gen_product_name(i: int) -> str:
    base = random.choice(PRODUCT_NAMES)
    return f"Product {i} - {base}"

# ------------------ Helpers ------------------

def random_email(i: int) -> str:
    return f"chloroouser{i}@gmail.com"

def random_name(i: int) -> str:
    return f"chloro user {i}"

async def get_role_map(session: AsyncSession):
    roles = (await session.execute(select(Role))).scalars().all()
    return {r.name: r for r in roles}

async def get_permission_map(session: AsyncSession):
    perms = (await session.execute(select(Permission))).scalars().all()
    return {p.name: p for p in perms}

async def get_category_map(session: AsyncSession):
    cats = (await session.execute(select(ProductCategory))).scalars().all()
    return {c.name: c for c in cats}


# ------------------ Seed Users + UserRoles + Credentials ------------------

async def seed_users_and_credentials(session: AsyncSession):
    role_map = await get_role_map(session)

    buyer_role = role_map.get("buyer")
    admin_role = role_map.get("admin")
    if not buyer_role:
        raise RuntimeError("Role 'buyer' not found")
    if not admin_role:
        print("[WARN] Role 'admin' not found, admin user will be buyer only")

    print(f"Seeding up to {NUM_USERS} users with ON CONFLICT DO NOTHING...")

    created_count = 0

    for i in range(1, NUM_USERS + 1):
        email = ADMIN_EMAIL if i == 1 else random_email(i)
        name = "Chloro admin user" if i == 1 else random_name(i)

        # 1) Insert user with ON CONFLICT DO NOTHING, returning id if actually inserted
        user_insert = (
            insert(Users.__table__)
            .values(
                public_id=uuid7(),
                email=email,
                name=name,
                role_version=0,
                created_at=now(),
                updated_at=now(),
            )
            .on_conflict_do_nothing(
                index_elements=["email"]   # uses UNIQUE(email)
            )
            .returning(Users.id)
        )

        result = await session.execute(user_insert)
        user_id = result.scalar_one_or_none()

        if user_id is None:
            # conflict -> user already existed; skip
            continue

        # 2) Decide the role for this user
        if i == 1 and admin_role:
            role_id = admin_role.id
        else:
            role_id = buyer_role.id

        # 3) Insert UserRole with ON CONFLICT DO NOTHING 
        user_role_insert = (
            insert(UserRole.__table__)
            .values(user_id=user_id, role_id=role_id)
            .on_conflict_do_nothing(
                constraint="uq_user_role_user_id_role_id"
            )
        )
        await session.execute(user_role_insert)

        # 4) Insert Credential
        plain_pw = SEED_PASSWORD_TEMPLATE.format(index=i)
        if i == 1 and ADMIN_PASSWORD:
            plain_pw = ADMIN_PASSWORD
        else:
            plain_pw = SEED_PASSWORD_TEMPLATE.format(index=i)
        hashed = hash_password(plain_pw)

        cred_insert = (
            insert(Credential.__table__)
            .values(
                user_id=user_id,
                type=CredentialType.PASSWORD,
                password_hash=hashed,
            )
            # optional if you added UNIQUE(user_id, type):
            .on_conflict_do_nothing(
                constraint="uq_credential_user_type_provider"
            )
        )
        await session.execute(cred_insert)

        created_count += 1
        if created_count % 100 == 0:
            print(f"Inserted {created_count} new users so far...")

    # 5) Single commit at the end
    await session.commit()
    print(f"Done. Created {created_count} new users (conflicts were skipped).")


# ------------------ Seed Products + ProductCategoryLink ------------------

async def seed_products_and_links(session: AsyncSession):
    cat_map = await get_category_map(session)
    if not cat_map:
        print("[WARN] No ProductCategory rows found, skipping products.")
        return

    cat_list = list(cat_map.values())
    print(f"Seeding up to {NUM_PRODUCTS} products with ON CONFLICT DO NOTHING...")

    admin_user = (
        await session.execute(select(Users).where(Users.email == ADMIN_EMAIL))
    ).first()
    owner_id = admin_user.id if admin_user else None

    created_products = 0
    ops_since_commit = 0

    for i in range(1, NUM_PRODUCTS + 1):
        name = gen_product_name(i)

        # 1) Insert product with ON CONFLICT DO NOTHING on unique(name)
        product_insert = (
            insert(Product.__table__)
            .values(
                public_id=uuid7(),
                name=name,
                stock_qty=random.randint(50, 500),
                base_price=random.randint(199, 4999) * 100,
                owner_id=owner_id,
                created_at=now(),
                updated_at=now(),
            )
            .on_conflict_do_nothing(
                index_elements=["name"]  
            )
            .returning(Product.id)
        )

        result = await session.execute(product_insert)
        product_id = result.scalar_one_or_none()

        if product_id is None:
            # product with this name already exists; skip creating links
            # (assuming links were created in earlier runs 
            continue

        created_products += 1

        num_cats = random.randint(1, min(2, len(cat_list)))
        chosen_cats = random.sample(cat_list, num_cats)

        for cat in chosen_cats:
            link_insert = (
                insert(ProductCategoryLink.__table__)
                .values(
                    product_id=product_id,
                    prod_category_id=cat.id,
                )
                .on_conflict_do_nothing(
                    constraint="uq_product_category"
                )
            )
            await session.execute(link_insert)
            since_commit += 1

        if created_products % 100 == 0:
            print(f"Inserted {created_products} new products so far...")

        if since_commit >= PRODUCT_BATCH_COMMIT:
            await session.commit()
            since_commit = 0

    await session.commit()
    print(f"Done. Created {created_products} new products (conflicts were skipped).")

# ------------------ Optional: Seed DeviceSessions ------------------

async def seed_device_sessions(session: AsyncSession):
    """
    Optional: create some fake device sessions for a subset of users.
    """
    users = (await session.execute(select(Users))).scalars.all()
    if not users:
        print("No users found, skipping DeviceSession seeding")
        return

    print("Seeding DeviceSession for ~20% of users...")

    sessions_batch: List[DeviceSession] = []

    for user in users:
        if random.random() > 0.2:
            continue

        session_token_plain = make_session_token_plain()
        session_token_hash = hash_token(session_token_plain)

        ds = DeviceSession(
            session_token_hash=session_token_hash,
            user_id=user.id,
            device_name="Seeded Chrome on Linux",
            device_type="browser",
            user_agent_snippet="seed-script/1.0",
            # created_at will be set by default_factory=now
            # public_id will be set by default_factory=uuid7
            last_activity_at=now(),
            session_expires_at=now() + timedelta(days=30),
        )

        sessions_batch.append(ds)

        if len(sessions_batch) >= BATCH_SIZE:
            session.add_all(sessions_batch)
            await session.commit()
            print(f"Committed {len(sessions_batch)} device sessions so far...")
            sessions_batch.clear()

    if sessions_batch:
        session.add_all(sessions_batch)
        await session.commit()
        print(f"Committed final {len(sessions_batch)} device sessions")

    print("DeviceSession seeding done.")

# ------------------ Main ------------------

async def main():
    async with async_session_maker() as session:
        # 0. Optional sanity: ensure tables exist
        # await engine.run_sync(SQLModel.metadata.create_all)  # usually only for local

       
        await seed_users_and_credentials(session)
        await seed_products_and_links(session)
        await seed_device_sessions(session)

    await engine.dispose()
    print("Seeding complete")

if __name__ == "__main__":
    asyncio.run(main())
