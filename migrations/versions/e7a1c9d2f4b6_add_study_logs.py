"""add study_logs (学习行为埋点：聚合时长与计数，非键鼠记录)

Revision ID: e7a1c9d2f4b6
Revises: d5f2a1b8c3e4
建表幂等（已存在则跳过），便于线上平滑升级。
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "e7a1c9d2f4b6"
down_revision = "d5f2a1b8c3e4"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    if "study_logs" in insp.get_table_names():
        return
    op.create_table(
        "study_logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("ts", sa.Float, nullable=True),
        sa.Column("problem_id", sa.String(40), nullable=True),
        sa.Column("active_seconds", sa.Integer, nullable=True),
        sa.Column("keystrokes", sa.Integer, nullable=True),
        sa.Column("runs", sa.Integer, nullable=True),
        sa.Column("submits", sa.Integer, nullable=True),
    )
    op.create_index("ix_study_logs_user_id", "study_logs", ["user_id"])
    op.create_index("ix_study_logs_ts", "study_logs", ["ts"])


def downgrade():
    pass
