"""006 permission refactor — roles, payroll_access, audit, tickets

Revision ID: 006
Revises: 005
Create Date: 2026-05-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("employee_id", sa.String(length=32), nullable=True))
    op.add_column(
        "users",
        sa.Column("payroll_access", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "users",
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("users", sa.Column("created_by", sa.String(length=64), nullable=True))
    op.create_index("ix_users_employee_id", "users", ["employee_id"], unique=True)

    op.create_table(
        "payroll_grant_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("target_username", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("granted_by", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payroll_grant_log_target", "payroll_grant_log", ["target_username"])

    op.create_table(
        "payroll_access_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("actor", sa.String(length=64), nullable=False),
        sa.Column("target_ref", sa.String(length=128), nullable=False),
        sa.Column("entry", sa.String(length=64), nullable=False),
        sa.Column("fields", sa.String(length=256), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payroll_access_log_actor", "payroll_access_log", ["actor"])

    op.create_table(
        "improvement_ticket",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("change_target", sa.Text(), nullable=True),
        sa.Column("test_requirement", sa.Text(), nullable=True),
        sa.Column("evidence_run_ids", sa.Text(), nullable=True),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column("gate_result", sa.Text(), nullable=True),
        sa.Column("assignee", sa.String(length=64), nullable=False, server_default="tech_super_admin"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_improvement_ticket_status", "improvement_ticket", ["status"])


def downgrade() -> None:
    op.drop_index("ix_improvement_ticket_status", table_name="improvement_ticket")
    op.drop_table("improvement_ticket")
    op.drop_index("ix_payroll_access_log_actor", table_name="payroll_access_log")
    op.drop_table("payroll_access_log")
    op.drop_index("ix_payroll_grant_log_target", table_name="payroll_grant_log")
    op.drop_table("payroll_grant_log")
    op.drop_index("ix_users_employee_id", table_name="users")
    op.drop_column("users", "created_by")
    op.drop_column("users", "must_change_password")
    op.drop_column("users", "payroll_access")
    op.drop_column("users", "employee_id")
