"""015 Restore pending accept flow — revert orphan in_progress rows

Revision ID: 015
Revises: 014
"""
from typing import Sequence, Union

from alembic import op

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 从未接单（updated_at 未变）且无门禁痕迹的 in_progress 回置为 pending
    op.execute(
        """
        UPDATE improvement_ticket t
        SET status = 'pending'
        WHERE t.status = 'in_progress'
          AND t.linked_run_id IS NULL
          AND (t.gate_result IS NULL OR trim(t.gate_result) = '')
          AND t.gate_eval_set_version IS NULL
          AND t.gate_pipeline_version IS NULL
          AND t.updated_at = t.created_at
          AND NOT EXISTS (
            SELECT 1 FROM eval_run r WHERE r.source_ticket_id = t.id
          )
        """
    )


def downgrade() -> None:
    pass
