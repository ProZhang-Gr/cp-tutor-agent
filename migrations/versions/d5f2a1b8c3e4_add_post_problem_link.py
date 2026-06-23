"""add problem_id/problem_title to posts (题解关联题目)

Revision ID: d5f2a1b8c3e4
Revises: c4e1f0a92b37
给社群帖子加可选的关联题目字段；加列幂等（已存在则跳过），便于线上平滑升级。
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "d5f2a1b8c3e4"
down_revision = "c4e1f0a92b37"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    if "posts" not in insp.get_table_names():
        return
    cols = [c["name"] for c in insp.get_columns("posts")]
    if "problem_id" not in cols:
        op.add_column("posts", sa.Column("problem_id", sa.String(40), nullable=True))
        op.create_index("ix_posts_problem_id", "posts", ["problem_id"])
    if "problem_title" not in cols:
        op.add_column("posts", sa.Column("problem_title", sa.String(200), nullable=True))


def downgrade():
    pass
