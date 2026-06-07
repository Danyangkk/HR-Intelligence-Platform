"""016 Clear pre-filled new_case_ids — restore manual eval case registration

Revision ID: 016
Revises: 015
"""
from typing import Sequence, Union

from alembic import op

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Open tickets should not carry pre-registered case ids; tech admin registers manually.
    op.execute(
        """
        UPDATE improvement_ticket
        SET new_case_ids = NULL
        WHERE status IN ('pending', 'in_progress', 'gate_running', 'gate_failed')
          AND new_case_ids IS NOT NULL
        """
    )


def downgrade() -> None:
    pass
