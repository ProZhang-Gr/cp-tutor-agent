"""add community posts/replies/likes

Revision ID: c4e1f0a92b37
Revises: 7f2a9c1b4d8e
Create Date: 2026-06-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4e1f0a92b37'
down_revision: Union[str, Sequence[str], None] = '7f2a9c1b4d8e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'posts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('username', sa.String(length=40), nullable=False),
        sa.Column('tag', sa.String(length=20), nullable=False),
        sa.Column('title', sa.String(length=120), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('likes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('reply_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.Float(), nullable=False, server_default='0'),
    )
    op.create_index('ix_posts_user_id', 'posts', ['user_id'])
    op.create_index('ix_posts_tag', 'posts', ['tag'])
    op.create_index('ix_posts_created_at', 'posts', ['created_at'])

    op.create_table(
        'post_replies',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('post_id', sa.Integer(), sa.ForeignKey('posts.id'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('username', sa.String(length=40), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.Float(), nullable=False, server_default='0'),
    )
    op.create_index('ix_post_replies_post_id', 'post_replies', ['post_id'])
    op.create_index('ix_post_replies_user_id', 'post_replies', ['user_id'])
    op.create_index('ix_post_replies_created_at', 'post_replies', ['created_at'])

    op.create_table(
        'post_likes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('post_id', sa.Integer(), sa.ForeignKey('posts.id'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.Float(), nullable=False, server_default='0'),
        sa.UniqueConstraint('post_id', 'user_id', name='uq_post_user_like'),
    )
    op.create_index('ix_post_likes_post_id', 'post_likes', ['post_id'])
    op.create_index('ix_post_likes_user_id', 'post_likes', ['user_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('post_likes')
    op.drop_table('post_replies')
    op.drop_table('posts')
