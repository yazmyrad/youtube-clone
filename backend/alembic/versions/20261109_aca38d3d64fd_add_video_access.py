"""add video access

Revision ID: aca38d3d64fd
Revises: 59f1d8884528
Create Date: 2026-11-09 02:29:26.128092
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'aca38d3d64fd'
down_revision: str | None = '59f1d8884528'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('video_access',
    sa.Column('video_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_video_access_user_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['video_id'], ['videos.id'], name=op.f('fk_video_access_video_id_videos'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('video_id', 'user_id', name=op.f('pk_video_access'))
    )
    op.create_index(op.f('ix_video_access_user_id'), 'video_access', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_video_access_user_id'), table_name='video_access')
    op.drop_table('video_access')
