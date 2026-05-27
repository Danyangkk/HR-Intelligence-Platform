"""005 agent feedback and badcase fields

Revision ID: 005
Revises: 004
Create Date: 2026-05-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agent_run", sa.Column("user_feedback", sa.String(length=8), nullable=True))
    op.add_column(
        "agent_run",
        sa.Column("auto_badcase", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("agent_run", sa.Column("badcase_reason", sa.String(length=64), nullable=True))
    op.add_column(
        "agent_run",
        sa.Column("review_status", sa.String(length=16), nullable=False, server_default="pending"),
    )
    op.create_index("ix_agent_run_auto_badcase", "agent_run", ["auto_badcase"])
    op.create_index("ix_agent_run_review_status", "agent_run", ["review_status"])

    op.create_table(
        "agent_feedback",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rating", sa.String(length=8), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent_run.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_feedback_run_id", "agent_feedback", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_feedback_run_id", table_name="agent_feedback")
    op.drop_table("agent_feedback")
    op.drop_index("ix_agent_run_review_status", table_name="agent_run")
    op.drop_index("ix_agent_run_auto_badcase", table_name="agent_run")
    op.drop_column("agent_run", "review_status")
    op.drop_column("agent_run", "badcase_reason")
    op.drop_column("agent_run", "auto_badcase")
    op.drop_column("agent_run", "user_feedback")
