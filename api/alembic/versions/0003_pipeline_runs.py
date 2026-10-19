"""Pipeline runs: pipeline_runs table; agent_runs.pipeline_run_id + cached.

`pipeline_runs` is one orchestrated pass over one tender (pipeline/orchestrator.py), polled by
GET /runs/{id}. A partial unique index allows at most one queued/running run per tender. agent_runs
rows written during a run link to it (`pipeline_run_id`), and `cached` marks rows replayed from the
LLM replay cache (the pre-cached demo) rather than a live model call.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TENDER_STATUSES = "'new', 'extracted', 'matched', 'checked', 'drafted', 'reviewed', 'approved', 'skipped', 'blocked', 'failed'"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('pipeline_runs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tender_id', sa.Integer(), nullable=False),
    sa.Column('target', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), server_default='queued', nullable=False),
    sa.Column('start_status', sa.Text(), nullable=False),
    sa.Column('resumed_from', sa.Text(), nullable=True),
    sa.Column('end_status', sa.Text(), nullable=True),
    sa.Column('stages', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('heartbeat_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('queued', 'running', 'succeeded', 'stopped', 'failed')", name='ck_pipeline_runs_status'),
    sa.CheckConstraint(f"target IN ({_TENDER_STATUSES})", name='ck_pipeline_runs_target'),
    sa.ForeignKeyConstraint(['tender_id'], ['tenders.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_pipeline_runs_tender_id'), 'pipeline_runs', ['tender_id'], unique=False)
    op.create_index('uq_pipeline_runs_active_tender', 'pipeline_runs', ['tender_id'], unique=True,
                    postgresql_where=sa.text("status IN ('queued', 'running')"))
    op.add_column('agent_runs', sa.Column('pipeline_run_id', sa.Integer(), nullable=True))
    op.add_column('agent_runs', sa.Column('cached', sa.Boolean(), server_default='false', nullable=False))
    op.create_index(op.f('ix_agent_runs_pipeline_run_id'), 'agent_runs', ['pipeline_run_id'], unique=False)
    op.create_foreign_key('agent_runs_pipeline_run_id_fkey', 'agent_runs', 'pipeline_runs', ['pipeline_run_id'], ['id'],
                          ondelete='SET NULL')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('agent_runs_pipeline_run_id_fkey', 'agent_runs', type_='foreignkey')
    op.drop_index(op.f('ix_agent_runs_pipeline_run_id'), table_name='agent_runs')
    op.drop_column('agent_runs', 'cached')
    op.drop_column('agent_runs', 'pipeline_run_id')
    op.drop_index('uq_pipeline_runs_active_tender', table_name='pipeline_runs', postgresql_where=sa.text("status IN ('queued', 'running')"))
    op.drop_index(op.f('ix_pipeline_runs_tender_id'), table_name='pipeline_runs')
    op.drop_table('pipeline_runs')
