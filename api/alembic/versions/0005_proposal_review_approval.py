"""Review and the human gate: proposals.reviewed_at, opened_at, approved_by, approval_note.

The ReviewReport stays in `review_json` (verdict pass / needs_work / fail, computed by agents/review.py). Approval
(POST /proposals/{id}/approve) needs a review, a verdict other than fail, and an open (POST /proposals/{id}/open)
after the review; it stores who approved and why.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('proposals', sa.Column('approved_by', sa.Text(), nullable=True))
    op.add_column('proposals', sa.Column('approval_note', sa.Text(), nullable=True))
    op.add_column('proposals', sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('proposals', sa.Column('opened_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('proposals', 'opened_at')
    op.drop_column('proposals', 'reviewed_at')
    op.drop_column('proposals', 'approval_note')
    op.drop_column('proposals', 'approved_by')
