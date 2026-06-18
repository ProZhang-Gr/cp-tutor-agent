# -*- coding: utf-8 -*-
"""数据库引擎与会话（SQLAlchemy 2.0）。

默认本地 SQLite；设了 DATABASE_URL 则用 PostgreSQL（带连接池）。
Render / Neon 常给 `postgres://`，这里规范化为 SQLAlchemy 所需的驱动 URL。
"""
import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from core.models import Base


def _normalize(url):
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


def _make_engine():
    url = settings.DATABASE_URL
    if url:
        return create_engine(_normalize(url), pool_pre_ping=True,
                             pool_size=5, max_overflow=10, future=True)
    os.makedirs(settings.DATA_DIR, exist_ok=True)
    return create_engine("sqlite:///" + settings.DB_PATH,
                         connect_args={"check_same_thread": False}, future=True)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


@contextmanager
def session_scope():
    """事务性会话：正常提交、异常回滚、最终关闭。"""
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def create_all():
    """按 ORM 模型建表（幂等）。生产以 Alembic 迁移为准，此为兜底。"""
    Base.metadata.create_all(engine)
