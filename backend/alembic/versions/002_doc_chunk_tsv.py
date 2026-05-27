"""Add tsvector column for BM25-style full text search on doc chunks."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TSVECTOR

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("doc_chunk", sa.Column("tsv", TSVECTOR(), nullable=True))
    op.execute("CREATE INDEX ix_doc_chunk_tsv ON doc_chunk USING gin(tsv)")


def downgrade() -> None:
    op.drop_index("ix_doc_chunk_tsv", table_name="doc_chunk")
    op.drop_column("doc_chunk", "tsv")
