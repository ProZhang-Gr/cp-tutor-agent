# -*- coding: utf-8 -*-
"""Alembic 环境：复用 core.db 的引擎与 core.models 的元数据。

引擎本身已根据 DATABASE_URL 选择 SQLite / PostgreSQL，
因此迁移在本地与生产都指向正确的库。
"""
import os
import sys
from logging.config import fileConfig

from alembic import context

# 让 env.py 能 import 到项目内的 core.*
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db import engine          # noqa: E402
from core.models import Base        # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=str(engine.url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
