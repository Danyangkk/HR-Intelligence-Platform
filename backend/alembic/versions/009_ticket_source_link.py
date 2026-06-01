"""009 improvement_ticket 加来源关联字段（复盘报告 → finding → suggestion → ticket）

Revision ID: 009
Revises: 008
Create Date: 2026-05-28

补全改进闭环 SOP 状态机：
- source_type：'review_report' | 'manual'
- source_report_id：来源复盘报告 id（如 'r-2026-w22'）
- source_finding_id：对应 finding 的 id
- source_suggestion_id：对应 suggestion 的 id

下次工单"已上线"时，可根据这三个 id 把 mock report 里对应 finding/suggestion
状态置为 fixed，关联的 agent_run.review_status 也一并 fixed。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "improvement_ticket",
        sa.Column("source_type", sa.String(length=32), nullable=False, server_default="manual"),
    )
    op.add_column(
        "improvement_ticket",
        sa.Column("source_report_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "improvement_ticket",
        sa.Column("source_finding_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "improvement_ticket",
        sa.Column("source_suggestion_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_improvement_ticket_source_suggestion",
        "improvement_ticket",
        ["source_suggestion_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_improvement_ticket_source_suggestion", table_name="improvement_ticket")
    op.drop_column("improvement_ticket", "source_suggestion_id")
    op.drop_column("improvement_ticket", "source_finding_id")
    op.drop_column("improvement_ticket", "source_report_id")
    op.drop_column("improvement_ticket", "source_type")
