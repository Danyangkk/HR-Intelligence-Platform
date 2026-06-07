"""014 Gate eval integration (run types + ticket linkage)

Revision ID: 014
Revises: 013
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "eval_run",
        sa.Column("run_type", sa.String(length=16), nullable=False, server_default="full"),
    )
    op.add_column("eval_run", sa.Column("source_ticket_id", sa.BigInteger(), nullable=True))
    op.add_column("eval_run", sa.Column("baseline_run_id", sa.BigInteger(), nullable=True))
    op.add_column("eval_run", sa.Column("eval_set_version", sa.String(length=64), nullable=True))
    op.add_column("eval_run", sa.Column("gate_verdict", sa.String(length=8), nullable=True))
    op.create_foreign_key(
        "fk_eval_run_source_ticket",
        "eval_run",
        "improvement_ticket",
        ["source_ticket_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_eval_run_baseline",
        "eval_run",
        "eval_run",
        ["baseline_run_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column("eval_case_result", sa.Column("diff_category", sa.String(length=16), nullable=True))
    op.add_column(
        "eval_case_result",
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "eval_case_result",
        sa.Column("pass_count", sa.Integer(), nullable=False, server_default="1"),
    )

    op.add_column("improvement_ticket", sa.Column("linked_run_id", sa.BigInteger(), nullable=True))
    op.add_column(
        "improvement_ticket", sa.Column("gate_eval_set_version", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "improvement_ticket", sa.Column("gate_pipeline_version", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "improvement_ticket",
        sa.Column("new_case_ids", postgresql.ARRAY(sa.String(length=64)), nullable=True),
    )
    op.create_foreign_key(
        "fk_ticket_linked_run",
        "improvement_ticket",
        "eval_run",
        ["linked_run_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "eval_baseline",
        sa.Column("id", sa.SmallInteger(), primary_key=True, server_default="1"),
        sa.Column("released_baseline_run_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(
            ["released_baseline_run_id"], ["eval_run.id"], ondelete="SET NULL"
        ),
    )
    op.execute("INSERT INTO eval_baseline (id, released_baseline_run_id) VALUES (1, NULL)")


def downgrade() -> None:
    op.drop_table("eval_baseline")
    op.drop_constraint("fk_ticket_linked_run", "improvement_ticket", type_="foreignkey")
    op.drop_column("improvement_ticket", "new_case_ids")
    op.drop_column("improvement_ticket", "gate_pipeline_version")
    op.drop_column("improvement_ticket", "gate_eval_set_version")
    op.drop_column("improvement_ticket", "linked_run_id")
    op.drop_column("eval_case_result", "pass_count")
    op.drop_column("eval_case_result", "attempts")
    op.drop_column("eval_case_result", "diff_category")
    op.drop_constraint("fk_eval_run_baseline", "eval_run", type_="foreignkey")
    op.drop_constraint("fk_eval_run_source_ticket", "eval_run", type_="foreignkey")
    op.drop_column("eval_run", "gate_verdict")
    op.drop_column("eval_run", "eval_set_version")
    op.drop_column("eval_run", "baseline_run_id")
    op.drop_column("eval_run", "source_ticket_id")
    op.drop_column("eval_run", "run_type")
