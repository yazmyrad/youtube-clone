"""add processing jobs

Revision ID: 59f1d8884528
Revises: 6fbb872a3abd
Create Date: 2026-11-08 20:06:58.306179
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '59f1d8884528'
down_revision: str | None = '6fbb872a3abd'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('processing_jobs',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('video_id', sa.Uuid(), nullable=False),
    sa.Column('status', sa.Enum('queued', 'running', 'done', 'failed', name='job_status'), server_default='queued', nullable=False),
    sa.Column('attempts', sa.SmallInteger(), server_default='0', nullable=False),
    sa.Column('max_attempts', sa.SmallInteger(), server_default='3', nullable=False),
    sa.Column('run_after', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('locked_by', sa.Text(), nullable=True),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['video_id'], ['videos.id'], name=op.f('fk_processing_jobs_video_id_videos'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_processing_jobs'))
    )
    op.create_index('ix_processing_jobs_due', 'processing_jobs', ['run_after'], unique=False, postgresql_where=sa.text("status = 'queued'"))
    op.create_index('ix_processing_jobs_lease', 'processing_jobs', ['locked_until'], unique=False, postgresql_where=sa.text("status = 'running'"))
    op.create_index('uq_processing_jobs_active_video', 'processing_jobs', ['video_id'], unique=True, postgresql_where=sa.text("status IN ('queued', 'running')"))


def downgrade() -> None:
    op.drop_index('uq_processing_jobs_active_video', table_name='processing_jobs', postgresql_where=sa.text("status IN ('queued', 'running')"))
    op.drop_index('ix_processing_jobs_lease', table_name='processing_jobs', postgresql_where=sa.text("status = 'running'"))
    op.drop_index('ix_processing_jobs_due', table_name='processing_jobs', postgresql_where=sa.text("status = 'queued'"))
    op.drop_table('processing_jobs')
    sa.Enum(name='job_status').drop(op.get_bind(), checkfirst=True)
