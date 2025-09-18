
from sqlalchemy import select, text

async def add_product():
    pass


async def add_product_categories(session,product_id, cat_ids):
    # Bulk insert product_category_link (single statement)
    if cat_ids:
        # Build parameterized VALUES list
        # e.g. VALUES (:p0_prod, :p0_cat), (:p1_prod, :p1_cat), ...
        values_parts = []
        params = {}
        for i, cid in enumerate(cat_ids):
            values_parts.append(f"(:p{i}_prod_id, :p{i}_cat_id)")
            params[f"p{i}_prod_id"] = product_id
            params[f"p{i}_cat_id"] = cid

        values_sql = ", ".join(values_parts)
        insert_sql = f"""
            INSERT INTO product_category_link (product_id, prod_category_id)
            VALUES {values_sql}
            ON CONFLICT (product_id, prod_category_id) DO NOTHING
        """
        await session.execute(text(insert_sql), params)