"""013 Eval judge feedback（PR6 人工校准）

Revision ID: 013
Revises: 012
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "eval_judge_feedback",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("case_result_id", sa.BigInteger(), nullable=False),
        sa.Column("verdict", sa.String(length=16), nullable=False),
        sa.Column("human_overall", sa.SmallInteger(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["case_result_id"], ["eval_case_result.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_eval_judge_feedback_case_result",
        "eval_judge_feedback",
        ["case_result_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_eval_judge_feedback_case_result", table_name="eval_judge_feedback")
    op.drop_table("eval_judge_feedback")
