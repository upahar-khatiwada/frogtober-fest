"""Compliance: structured evidence + action on compliance_items; compliance_overrides table.

compliance_items gains `source` (rule | model, CHECK frozen here), `evidence_chunk_ids` /
`evidence_document_ids` (INTEGER[]), `evidence_ref`, `evidence_quote`, `action_needed` and
`requirement_index`. `compliance_overrides` records who accepted which hard failures, when and why
(the only way a blocked tender reaches Proposal).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('compliance_items', sa.Column('source', sa.Text(), server_default='rule', nullable=False))
    op.add_column('compliance_items', sa.Column('evidence_chunk_ids', postgresql.ARRAY(sa.Integer()), server_default='{}', nullable=False))
    op.add_column('compliance_items', sa.Column('evidence_document_ids', postgresql.ARRAY(sa.Integer()), server_default='{}', nullable=False))
    op.add_column('compliance_items', sa.Column('evidence_ref', sa.Text(), nullable=True))
    op.add_column('compliance_items', sa.Column('evidence_quote', sa.Text(), nullable=True))
    op.add_column('compliance_items', sa.Column('action_needed', sa.Text(), nullable=True))
    op.add_column('compliance_items', sa.Column('requirement_index', sa.Integer(), nullable=True))
    op.create_check_constraint('ck_compliance_items_source', 'compliance_items', "source IN ('rule', 'model')")
    op.create_table('compliance_overrides',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tender_id', sa.Integer(), nullable=False),
    sa.Column('overridden_by', sa.Text(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('hard_failures', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['tender_id'], ['tenders.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_compliance_overrides_tender_id'), 'compliance_overrides', ['tender_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_compliance_overrides_tender_id'), table_name='compliance_overrides')
    op.drop_table('compliance_overrides')
    op.drop_constraint('ck_compliance_items_source', 'compliance_items', type_='check')
    for column in ('requirement_index', 'action_needed', 'evidence_quote', 'evidence_ref', 'evidence_document_ids',
                   'evidence_chunk_ids', 'source'):
        op.drop_column('compliance_items', column)
