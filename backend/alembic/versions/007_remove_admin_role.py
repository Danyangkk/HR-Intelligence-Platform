"""007 remove admin role — migrate to staff

Revision ID: 007
Revises: 006
Create Date: 2026-05-27

"""
from typing import Sequence, Union

from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE users SET role = 'staff' WHERE role = 'admin'")


def downgrade() -> None:
    pass
