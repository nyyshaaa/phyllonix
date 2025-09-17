"""seed product categories

Revision ID: 25d460f457df
Revises: 4d23f512513a
Create Date: 2025-09-17 15:05:03.519554

"""
from datetime import datetime,timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

now_ts = datetime.now(timezone.utc)

# revision identifiers, used by Alembic.
revision: str = '25d460f457df'
down_revision: Union[str, Sequence[str], None] = '4d23f512513a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "productcategory"

# Categories to seed (name, slug, description)
CATEGORIES = [
    ("snacks", "Natural ,Healthy ,Nutritious Snacks"),
    ("ladoos", "Energy booster , fully healthy , strength building nutritious laddos"),
    ("choco","chocolate wonderland"),
    ("arts", "Handmade arts & crafts"),
    ("gadgets","Cool gadgets & accessories"),
    ("tshirts","Summer orange vibe tshirts"),
    ("stunt-artist-dresses", "Cosplay stunt artist dresses / performance outfits"),
    ("other", "Other items"),
]


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()

    values_sql = ", ".join("(:name_{i}, :desc_{i},:created_{i}, :updated_{i})".format(i=i) for i in range(len(CATEGORIES)))
    params = {}
    for i, (name, desc) in enumerate(CATEGORIES):
        params[f"name_{i}"] = name
        params[f"desc_{i}"] = desc
        params[f"created_{i}"] = now_ts
        params[f"updated_{i}"] = now_ts

    # Insert: name, description. ON CONFLICT DO NOTHING for idempotency.
    insert_sql = f"""
        INSERT INTO {TABLE} (name, description,created_at, updated_at)
        VALUES {values_sql}
        ON CONFLICT (name) DO NOTHING
    """
    conn.execute(sa.text(insert_sql), params)


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    names = [c[0] for c in CATEGORIES]
    # Delete seeded categories by name (safe)
    conn.execute(sa.text(f"DELETE FROM {TABLE} WHERE name = ANY(:names)"), {"names": names})
