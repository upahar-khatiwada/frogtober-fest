"""Initial schema: spec section 11 + Nepal extensions.

Additive over spec section 11: Nepal columns on tenders/company/documents,
ingestion bookkeeping on documents, kb_chunks.chunk_index/token_count,
agent_runs.attempts/error/raw_output, compliance_items.rule_id/explanation,
created_at/updated_at, and CHECK constraints mirroring schemas/enums.py
(values frozen here as of this revision). `tenders.budget` is named
`estimated_cost_npr`. Embedding dimension is fixed at 1024 (bge-m3).

Revision ID: 0001
Revises:
Create Date: 2026-10-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table('agent_runs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tender_id', sa.Integer(), nullable=True),
    sa.Column('stage', sa.Text(), nullable=False),
    sa.Column('model', sa.Text(), nullable=False),
    sa.Column('input_hash', sa.Text(), nullable=False),
    sa.Column('output_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('latency_ms', sa.Integer(), nullable=False),
    sa.Column('ok', sa.Boolean(), nullable=False),
    sa.Column('attempts', sa.Integer(), server_default='1', nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('raw_output', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("stage IN ('scout', 'matching', 'compliance', 'proposal', 'review')", name='ck_agent_runs_stage'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_agent_runs_tender_id'), 'agent_runs', ['tender_id'], unique=False)
    op.create_table('company',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('sectors', postgresql.ARRAY(sa.Text()), server_default='{}', nullable=False),
    sa.Column('services', sa.Text(), server_default='', nullable=False),
    sa.Column('location', sa.Text(), nullable=True),
    sa.Column('turnover_npr', sa.BigInteger(), nullable=True),
    sa.Column('certifications', postgresql.ARRAY(sa.Text()), server_default='{}', nullable=False),
    sa.Column('profile_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('province', sa.Text(), nullable=True),
    sa.Column('pan_number', sa.Text(), nullable=True),
    sa.Column('vat_number', sa.Text(), nullable=True),
    sa.Column('licence_classes', postgresql.ARRAY(sa.Text()), server_default='{}', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("province IN ('koshi', 'madhesh', 'bagmati', 'gandaki', 'lumbini', 'karnali', 'sudurpashchim')", name='ck_company_province'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('tenders',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source_url', sa.Text(), nullable=True),
    sa.Column('raw_text', sa.Text(), nullable=True),
    sa.Column('title', sa.Text(), nullable=True),
    sa.Column('buyer', sa.Text(), nullable=True),
    sa.Column('deadline', sa.DateTime(timezone=True), nullable=True),
    sa.Column('location', sa.Text(), nullable=True),
    sa.Column('record_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('status', sa.Text(), server_default='new', nullable=False),
    sa.Column('procurement_type', sa.Text(), nullable=True),
    sa.Column('method', sa.Text(), nullable=True),
    sa.Column('province', sa.Text(), nullable=True),
    sa.Column('district', sa.Text(), nullable=True),
    sa.Column('deadline_bs', sa.Text(), nullable=True),
    sa.Column('estimated_cost_npr', sa.BigInteger(), nullable=True),
    sa.Column('language', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("language IN ('en', 'ne', 'mixed')", name='ck_tenders_language'),
    sa.CheckConstraint("method IN ('ncb', 'icb', 'eoi', 'rfp', 'quotation', 'other')", name='ck_tenders_method'),
    sa.CheckConstraint("procurement_type IN ('goods', 'works', 'consulting', 'non_consulting', 'unknown')", name='ck_tenders_procurement_type'),
    sa.CheckConstraint("province IN ('koshi', 'madhesh', 'bagmati', 'gandaki', 'lumbini', 'karnali', 'sudurpashchim')", name='ck_tenders_province'),
    sa.CheckConstraint("status IN ('new', 'extracted', 'matched', 'checked', 'drafted', 'reviewed', 'approved', 'skipped', 'blocked', 'failed')", name='ck_tenders_status'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source_url')
    )
    op.create_index(op.f('ix_tenders_deadline'), 'tenders', ['deadline'], unique=False)
    op.create_index(op.f('ix_tenders_status'), 'tenders', ['status'], unique=False)
    op.create_table('compliance_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tender_id', sa.Integer(), nullable=False),
    sa.Column('requirement', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('severity', sa.Text(), nullable=False),
    sa.Column('evidence', sa.Text(), nullable=True),
    sa.Column('rule_id', sa.Text(), nullable=True),
    sa.Column('explanation', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("severity IN ('hard', 'soft')", name='ck_compliance_items_severity'),
    sa.CheckConstraint("status IN ('pass', 'fail', 'unclear')", name='ck_compliance_items_status'),
    sa.ForeignKeyConstraint(['tender_id'], ['tenders.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_compliance_items_tender_id'), 'compliance_items', ['tender_id'], unique=False)
    op.create_table('documents',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('company_id', sa.Integer(), nullable=False),
    sa.Column('filename', sa.Text(), nullable=False),
    sa.Column('doc_type', sa.Text(), nullable=False),
    sa.Column('expires_on', sa.Date(), nullable=True),
    sa.Column('raw_text', sa.Text(), nullable=True),
    sa.Column('content_type', sa.Text(), nullable=True),
    sa.Column('content', sa.LargeBinary(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('fiscal_year_bs', sa.Text(), nullable=True),
    sa.Column('value_npr', sa.BigInteger(), nullable=True),
    sa.Column('ingest_status', sa.Text(), server_default='pending', nullable=False),
    sa.Column('ingest_error', sa.Text(), nullable=True),
    sa.Column('warnings', postgresql.ARRAY(sa.Text()), server_default='{}', nullable=False),
    sa.Column('page_count', sa.Integer(), nullable=True),
    sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("doc_type IN ('company_registration', 'business_licence', 'licence_renewal', 'pan_vat', 'tax_clearance', 'tax_return', 'self_declaration', 'power_of_attorney', 'bid_security', 'audit_report', 'experience_certificate', 'jv_agreement', 'company_profile', 'other')", name='ck_documents_doc_type'),
    sa.CheckConstraint("ingest_status IN ('pending', 'processing', 'ready', 'needs_ocr', 'failed')", name='ck_documents_ingest_status'),
    sa.ForeignKeyConstraint(['company_id'], ['company.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_documents_company_id'), 'documents', ['company_id'], unique=False)
    op.create_table('matches',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tender_id', sa.Integer(), nullable=False),
    sa.Column('score', sa.Integer(), nullable=False),
    sa.Column('reasons', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('decision', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("decision IN ('pursue', 'skip')", name='ck_matches_decision'),
    sa.ForeignKeyConstraint(['tender_id'], ['tenders.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_matches_tender_id'), 'matches', ['tender_id'], unique=False)
    op.create_table('proposals',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tender_id', sa.Integer(), nullable=False),
    sa.Column('version', sa.Integer(), server_default='1', nullable=False),
    sa.Column('sections', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('review_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('status', sa.Text(), server_default='draft', nullable=False),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("status IN ('draft', 'reviewed', 'approved')", name='ck_proposals_status'),
    sa.ForeignKeyConstraint(['tender_id'], ['tenders.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_proposals_tender_id'), 'proposals', ['tender_id'], unique=False)
    op.create_table('kb_chunks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('chunk_index', sa.Integer(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('token_count', sa.Integer(), nullable=False),
    sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=1024), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_kb_chunks_document_id'), 'kb_chunks', ['document_id'], unique=False)
    op.create_index('ix_kb_chunks_embedding_hnsw', 'kb_chunks', ['embedding'], unique=False, postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_kb_chunks_embedding_hnsw', table_name='kb_chunks', postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.drop_index(op.f('ix_kb_chunks_document_id'), table_name='kb_chunks')
    op.drop_table('kb_chunks')
    op.drop_index(op.f('ix_proposals_tender_id'), table_name='proposals')
    op.drop_table('proposals')
    op.drop_index(op.f('ix_matches_tender_id'), table_name='matches')
    op.drop_table('matches')
    op.drop_index(op.f('ix_documents_company_id'), table_name='documents')
    op.drop_table('documents')
    op.drop_index(op.f('ix_compliance_items_tender_id'), table_name='compliance_items')
    op.drop_table('compliance_items')
    op.drop_index(op.f('ix_tenders_status'), table_name='tenders')
    op.drop_index(op.f('ix_tenders_deadline'), table_name='tenders')
    op.drop_table('tenders')
    op.drop_table('company')
    op.drop_index(op.f('ix_agent_runs_tender_id'), table_name='agent_runs')
    op.drop_table('agent_runs')
