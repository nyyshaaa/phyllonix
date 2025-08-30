"""rename table user to users

Revision ID: fbef4fd0439f
Revises: 9c56107ee0e2
Create Date: 2025-08-30 12:53:05.848908

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fbef4fd0439f'
down_revision: Union[str, Sequence[str], None] = '9c56107ee0e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.rename_table('user', 'users')
    pass


def downgrade() -> None:
    """Downgrade schema."""
    op.rename_table('users', 'user')
    pass
