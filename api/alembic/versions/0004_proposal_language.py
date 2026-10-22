"""Proposal versions: proposals.language.

A proposal is written in the notice's language (en/ne; `mixed` -> ne) unless English is forced
(agents/proposal.py). Sections (with their cited chunk ids and flags) stay in the `sections` JSONB.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('proposals', sa.Column('language', sa.Text(), nullable=True))
    op.create_check_constraint('ck_proposals_language', 'proposals', "language IN ('en', 'ne')")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_proposals_language', 'proposals', type_='check')
    op.drop_column('proposals', 'language')
