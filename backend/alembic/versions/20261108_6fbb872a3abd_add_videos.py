"""add videos

Revision ID: 6fbb872a3abd
Revises: 149df2cd4cb3
Create Date: 2026-11-08 03:18:56.744173
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '6fbb872a3abd'
down_revision: str | None = '149df2cd4cb3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Trigram index for title search. Superuser-free: pg_trgm is a trusted extension.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table('videos',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('owner_id', sa.Uuid(), nullable=False),
    sa.Column('title', sa.String(length=100), nullable=False),
    sa.Column('description', sa.String(length=5000), server_default='', nullable=False),
    sa.Column('visibility', sa.Enum('public', 'unlisted', 'private', name='video_visibility'), server_default='private', nullable=False),
    sa.Column('status', sa.Enum('uploading', 'processing', 'ready', 'failed', name='video_status'), server_default='uploading', nullable=False),
    sa.Column('failure_reason', sa.Text(), nullable=True),
    sa.Column('raw_key', sa.Text(), nullable=True),
    sa.Column('hls_prefix', sa.Text(), nullable=True),
    sa.Column('thumbnail_key', sa.Text(), nullable=True),
    sa.Column('duration_seconds', sa.Integer(), nullable=True),
    sa.Column('source_size_bytes', sa.BigInteger(), nullable=True),
    sa.Column('views_count', sa.BigInteger(), server_default='0', nullable=False),
    sa.Column('likes_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('dislikes_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('comments_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('hidden_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("btrim(title) <> ''", name=op.f('ck_videos_title_not_blank')),
    sa.CheckConstraint("status <> 'ready' OR (hls_prefix IS NOT NULL AND thumbnail_key IS NOT NULL AND duration_seconds IS NOT NULL AND published_at IS NOT NULL)", name=op.f('ck_videos_ready_has_media')),
    sa.CheckConstraint('comments_count >= 0', name=op.f('ck_videos_comments_count_non_negative')),
    sa.CheckConstraint('dislikes_count >= 0', name=op.f('ck_videos_dislikes_count_non_negative')),
    sa.CheckConstraint('duration_seconds > 0', name=op.f('ck_videos_duration_positive')),
    sa.CheckConstraint('likes_count >= 0', name=op.f('ck_videos_likes_count_non_negative')),
    sa.CheckConstraint('source_size_bytes >= 0', name=op.f('ck_videos_source_size_non_negative')),
    sa.CheckConstraint('views_count >= 0', name=op.f('ck_videos_views_count_non_negative')),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_videos_owner_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_videos'))
    )
    op.create_index('ix_videos_channel', 'videos', ['owner_id', sa.literal_column('published_at DESC'), sa.literal_column('id DESC')], unique=False, postgresql_where=sa.text("status = 'ready' AND deleted_at IS NULL"))
    op.create_index('ix_videos_deleted', 'videos', ['deleted_at'], unique=False, postgresql_where=sa.text('deleted_at IS NOT NULL'))
    op.create_index('ix_videos_feed', 'videos', [sa.literal_column('published_at DESC'), sa.literal_column('id DESC')], unique=False, postgresql_where=sa.text("visibility = 'public' AND status = 'ready' AND hidden_at IS NULL AND deleted_at IS NULL"))
    op.create_index('ix_videos_owner_created', 'videos', ['owner_id', sa.literal_column('created_at DESC')], unique=False, postgresql_where=sa.text('deleted_at IS NULL'))
    op.create_index('ix_videos_title_trgm', 'videos', ['title'], unique=False, postgresql_using='gin', postgresql_ops={'title': 'gin_trgm_ops'}, postgresql_where=sa.text("visibility = 'public' AND status = 'ready' AND hidden_at IS NULL AND deleted_at IS NULL"))
    op.create_index('ix_videos_uploading_created', 'videos', ['created_at'], unique=False, postgresql_where=sa.text("status = 'uploading'"))


def downgrade() -> None:
    op.drop_index('ix_videos_uploading_created', table_name='videos', postgresql_where=sa.text("status = 'uploading'"))
    op.drop_index('ix_videos_title_trgm', table_name='videos', postgresql_using='gin', postgresql_ops={'title': 'gin_trgm_ops'}, postgresql_where=sa.text("visibility = 'public' AND status = 'ready' AND hidden_at IS NULL AND deleted_at IS NULL"))
    op.drop_index('ix_videos_owner_created', table_name='videos', postgresql_where=sa.text('deleted_at IS NULL'))
    op.drop_index('ix_videos_feed', table_name='videos', postgresql_where=sa.text("visibility = 'public' AND status = 'ready' AND hidden_at IS NULL AND deleted_at IS NULL"))
    op.drop_index('ix_videos_deleted', table_name='videos', postgresql_where=sa.text('deleted_at IS NOT NULL'))
    op.drop_index('ix_videos_channel', table_name='videos', postgresql_where=sa.text("status = 'ready' AND deleted_at IS NULL"))
    op.drop_table('videos')
    sa.Enum(name='video_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='video_visibility').drop(op.get_bind(), checkfirst=True)
    # The extension stays: later migrations and other databases may depend on it.
