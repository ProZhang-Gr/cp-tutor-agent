# -*- coding: utf-8 -*-
"""SQLAlchemy 2.0 ORM 模型。

时间字段沿用 time.time() 浮点时间戳，避免改动既有聚合逻辑。
user_id 对游客为 NULL（共用游客桶），登录用户外键关联 users.id。
"""
import time

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    pw_hash: Mapped[str] = mapped_column(String(128))
    salt: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    credits: Mapped[int] = mapped_column(Integer, default=0)   # 算力点，>0 即 Pro


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True)
    ts: Mapped[float] = mapped_column(Float, default=time.time, index=True)
    problem_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    problem_title: Mapped[str | None] = mapped_column(String(200))
    problem_type: Mapped[str | None] = mapped_column(String(60))
    difficulty: Mapped[str | None] = mapped_column(String(30))
    passed: Mapped[int] = mapped_column(Integer, default=0)
    tests_passed: Mapped[int] = mapped_column(Integer, default=0)
    tests_total: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[int] = mapped_column(Integer, default=0)
    error_kind: Mapped[str | None] = mapped_column(String(20))


class AuditLog(Base):
    """每次 LLM 调用的审计记录：用于监察、限流配额统计与每日报告。"""
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[float] = mapped_column(Float, default=time.time, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    ip: Mapped[str | None] = mapped_column(String(64), index=True)
    endpoint: Mapped[str | None] = mapped_column(String(40))
    tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meta: Mapped[str | None] = mapped_column(String(300), nullable=True)


class UserProblem(Base):
    __tablename__ = "user_problems"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    type: Mapped[str | None] = mapped_column(String(60))
    difficulty: Mapped[str | None] = mapped_column(String(30))
    description: Mapped[str] = mapped_column(Text)
    created_at: Mapped[float] = mapped_column(Float, default=time.time, index=True)
