"""010 Eval Harness 表（eval_run + eval_case_result）

Revision ID: 010
Revises: 009
Create Date: 2026-05-28

评测打分体系（④Eval ≠ ③Test）：
- eval_run: 一次跑批的总览（版本/时间/三层指标聚合）
- eval_case_result: 每条 case 的三层打分明细（layer1/layer2/layer3）

设计原则：layer 字段允许多次记录（同一 case 跑了 layer1+2+3 就有 3 行），
方便后续按 layer 单独看通过率/分项均分，也方便部分 case 只跑 layer1。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "eval_run",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),  # 系统版本标签（如 git rev）
        sa.Column("trigger", sa.String(length=32), nullable=False, server_default="manual"),  # manual|scheduled|regression
        sa.Column("triggered_by", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="running"),  # running|done|failed
        sa.Column("started_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("total_cases", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("layer1_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("layer1_pass", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("layer2_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("layer2_pass", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("layer3_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("layer3_scored", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("layer3_avg", sa.Float(), nullable=True),
        sa.Column("layer3_correctness_avg", sa.Float(), nullable=True),
        sa.Column("layer3_completeness_avg", sa.Float(), nullable=True),
        sa.Column("layer3_citation_avg", sa.Float(), nullable=True),
        sa.Column("layer3_compliance_avg", sa.Float(), nullable=True),
        sa.Column("total_score", sa.Float(), nullable=True),  # 综合分（layer3_avg）
        sa.Column("intent_breakdown", postgresql.JSONB(astext_type=sa.Text()), nullable=True),  # 按意图分项均分
        sa.Column("weakness_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),  # 弱项清单
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_eval_run_started", "eval_run", ["started_at"])

    op.create_table(
        "eval_case_result",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column("layer", sa.SmallInteger(), nullable=False),  # 1|2|3
        sa.Column("passed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("score", sa.Float(), nullable=True),  # layer3 综合分；layer1/2 不设
        sa.Column("score_detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),  # rubric 详细
        sa.Column("expected", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("actual", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("judge_reasoning", sa.Text(), nullable=True),
        sa.Column("violations", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),  # 单条评测异常（layer3 LLM-as-judge 容错）
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["run_id"], ["eval_run.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_eval_case_result_run", "eval_case_result", ["run_id"])
    op.create_index("ix_eval_case_result_case", "eval_case_result", ["case_id"])


def downgrade() -> None:
    op.drop_index("ix_eval_case_result_case", table_name="eval_case_result")
    op.drop_index("ix_eval_case_result_run", table_name="eval_case_result")
    op.drop_table("eval_case_result")
    op.drop_index("ix_eval_run_started", table_name="eval_run")
    op.drop_table("eval_run")
