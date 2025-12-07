"""add unique constraint on product.name npt reflecting in deployed schema

Revision ID: 6f4bd48e4aeb
Revises: cba69ff98159
Create Date: 2025-12-07 18:34:54.707481

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6f4bd48e4aeb'
down_revision: Union[str, Sequence[str], None] = 'cba69ff98159'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade():
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'product_name_key'
                AND conrelid = 'product'::regclass
            ) THEN
                ALTER TABLE product
                ADD CONSTRAINT product_name_key UNIQUE (name);
            END IF;
        END;
        $$;
        """
    )

def downgrade():
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'product_name_key'
                AND conrelid = 'product'::regclass
            ) THEN
                ALTER TABLE product
                DROP CONSTRAINT product_name_key;
            END IF;
        END;
        $$;
        """
    )