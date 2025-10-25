

# insert_products_testdata.py
import asyncio
import random
from datetime import datetime, timedelta
from typing import List

from sqlmodel.ext.asyncio.session import AsyncSession
from backend.common.utils import now
from backend.db.connection import async_session
from backend.schema.full_schema import Product
from backend.config.admin_config import admin_config


TEST_ADMIN_ID = admin_config.TEST_ADMIN_ID

NAMES = [
   "Girl Racing Through Clouds","Cotton Tee - Fly High in Blue","Firefly lights","Wolves and girls painting","Mystical Forest Hoodie",
   "Chocolate Drizzle Coconut Bites","Pistachio,Peanuts & Rose Energy Ladoo","Matcha Almond Protein Ladoo","Dancing Petals Painting"

]


CATEGORIES = ["snack", "arts", "clothing", "gadget"]

def gen_name(i: int) -> str:
    adj = random.choice(NAMES)
    return f"Test Product {i} - {adj}"


async def create_products_batch(session: AsyncSession, products: List[Product]):
    session.add_all(products)
    await session.commit()
    # optional: expire objects to free memory
    for p in products:
        await session.refresh(p)

async def main(total: int = 500, batch_size: int = 100):
    """
    Inserts `total` products in batches of `batch_size`.
    Default: 500 products, batch size 100.
    """
    print(f"Starting insertion of {total} products (batch_size={batch_size})")

    created = 0
    batch = []

    async with async_session() as session:
        for i in range(1, total + 1):

            # ensure unique name - include i
            name = gen_name(i)

            p = Product(
                stock_qty=random.randint(0, 500),
                name=name,
                base_price=random.randint(199, 4999) * 100, 
                owner_id=int(admin_config.TEST_ADMIN_ID),
            )

            batch.append(p)
            created += 1

            if len(batch) >= batch_size:
                await create_products_batch(session, batch)
                print(f"Inserted {created}/{total}")
                batch = []

        # last partial batch
        if batch:
            await create_products_batch(session, batch)
            print(f"Inserted {created}/{total}")

    print("Done.")

if __name__ == "__main__":
    asyncio.run(main(total=500, batch_size=100))
