"""improvement_ticket: content → content_biz + draft_changes

Revision ID: 011_ticket_content_biz_draft
Revises: 010_eval_harness
Create Date: 2026-05-29
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "improvement_ticket",
        sa.Column("draft_changes", JSONB, nullable=True),
    )
    op.alter_column("improvement_ticket", "content", new_column_name="content_biz")


def downgrade() -> None:
    op.alter_column("improvement_ticket", "content_biz", new_column_name="content")
    op.drop_column("improvement_ticket", "draft_changes")
