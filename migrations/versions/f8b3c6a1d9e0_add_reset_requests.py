"""add reset_requests (找回密码工单：向管理员申请重置)

Revision ID: f8b3c6a1d9e0
Revises: e7a1c9d2f4b6
建表幂等（已存在则跳过），便于线上平滑升级。
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "f8b3c6a1d9e0"
down_revision = "e7a1c9d2f4b6"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    if "reset_requests" in insp.get_table_names():
        return
    op.create_table(
        "reset_requests",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("username", sa.String(40), nullable=False),
        sa.Column("contact", sa.String(80), nullable=True),
        sa.Column("note", sa.String(300), nullable=True),
        sa.Column("status", sa.String(16), nullable=True),
        sa.Column("created_at", sa.Float, nullable=True),
        sa.Column("handled_at", sa.Float, nullable=True),
    )
    op.create_index("ix_reset_requests_user_id", "reset_requests", ["user_id"])
    op.create_index("ix_reset_requests_username", "reset_requests", ["username"])
    op.create_index("ix_reset_requests_status", "reset_requests", ["status"])
    op.create_index("ix_reset_requests_created_at", "reset_requests", ["created_at"])


def downgrade():
    pass
