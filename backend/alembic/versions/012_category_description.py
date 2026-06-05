"""Add description column to category table."""

revision = "012"
down_revision = "011"

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.add_column("category", sa.Column("description", sa.String(256), nullable=True))


def downgrade() -> None:
    op.drop_column("category", "description")
