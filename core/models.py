# -*- coding: utf-8 -*-
"""SQLAlchemy 2.0 ORM 模型。

时间字段沿用 time.time() 浮点时间戳，避免改动既有聚合逻辑。
user_id 对游客为 NULL（共用游客桶），登录用户外键关联 users.id。
"""
import time

from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint
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
    code: Mapped[str | None] = mapped_column(Text, nullable=True)   # 提交时的源代码


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


class Post(Base):
    """社群帖子。username 冗余存一份便于展示（本应用无改名功能，安全）。"""
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True)
    username: Mapped[str] = mapped_column(String(40))
    tag: Mapped[str] = mapped_column(String(20), index=True)   # 求助/题解/讨论/反馈
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    reply_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[float] = mapped_column(Float, default=time.time, index=True)


class Reply(Base):
    __tablename__ = "post_replies"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True)
    username: Mapped[str] = mapped_column(String(40))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[float] = mapped_column(Float, default=time.time, index=True)


class PostLike(Base):
    """点赞去重：同一用户对同一帖只能点一次。"""
    __tablename__ = "post_likes"
    __table_args__ = (UniqueConstraint("post_id", "user_id", name="uq_post_user_like"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
