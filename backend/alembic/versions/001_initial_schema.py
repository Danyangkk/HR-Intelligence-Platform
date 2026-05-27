"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-05-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "category",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.String(length=32), nullable=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=True),
        sa.Column("sort", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["category.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "template",
        sa.Column("l3_id", sa.String(length=32), nullable=False),
        sa.Column("columns", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("filters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("unique_key", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["l3_id"], ["category.id"]),
        sa.PrimaryKeyConstraint("l3_id"),
    )

    op.create_table(
        "data_record",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("l3_id", sa.String(length=32), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("uk_hash", sa.String(length=128), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["l3_id"], ["category.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("l3_id", "uk_hash", name="uq_data_record_l3_uk"),
    )
    op.create_index("ix_data_record_l3_id", "data_record", ["l3_id"])

    op.create_table(
        "document",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("l3_id", sa.String(length=32), nullable=False),
        sa.Column("file_name", sa.String(length=512), nullable=False),
        sa.Column("file_key", sa.String(length=512), nullable=True),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("doc_kind", sa.String(length=16), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=True),
        sa.Column("index_status", sa.String(length=16), nullable=False),
        sa.Column("uploader", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["l3_id"], ["category.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_l3_id", "document", ["l3_id"])

    op.create_table(
        "doc_chunk",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("title_path", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["document.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "feishu_sync",
        sa.Column("l3_id", sa.String(length=32), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column("next_sync_at", sa.DateTime(), nullable=True),
        sa.Column("cursor", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_msg", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["l3_id"], ["category.id"]),
        sa.PrimaryKeyConstraint("l3_id"),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("actor", sa.String(length=64), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("l3_id", sa.String(length=32), nullable=True),
        sa.Column("target_id", sa.String(length=64), nullable=True),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=256), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )


def downgrade() -> None:
    op.drop_table("users")
    op.drop_table("audit_log")
    op.drop_table("feishu_sync")
    op.drop_table("doc_chunk")
    op.drop_index("ix_document_l3_id", table_name="document")
    op.drop_table("document")
    op.drop_index("ix_data_record_l3_id", table_name="data_record")
    op.drop_table("data_record")
    op.drop_table("template")
    op.drop_table("category")
