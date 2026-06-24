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


class StudyLog(Base):
    """学习行为埋点（聚合，非键鼠记录）。

    刻意只存「时长 + 计数」这类聚合学习行为，不存任何按键内容/鼠标轨迹，
    既能刻画学习投入（专注时长、活跃度、人均每题用时），又不触碰隐私红线。
    游客 user_id 为 NULL，登录用户按 uid 归属。
    """
    __tablename__ = "study_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True)
    ts: Mapped[float] = mapped_column(Float, default=time.time, index=True)
    problem_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    active_seconds: Mapped[int] = mapped_column(Integer, default=0)  # 专注（页面可见且有操作）时长
    keystrokes: Mapped[int] = mapped_column(Integer, default=0)      # 编辑器击键次数（仅计数）
    runs: Mapped[int] = mapped_column(Integer, default=0)            # 本段内点「运行」次数
    submits: Mapped[int] = mapped_column(Integer, default=0)         # 本段内点「提交评测」次数


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
    # 可选关联题目：把帖子（尤其题解）挂到某道题上，便于在题目剖析处聚合
    problem_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    problem_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
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


class ResetRequest(Base):
    """找回密码工单：用户在登录页提交「向管理员申请重置」，管理员后台处理。

    刻意不走邮件（免费实例不接 SMTP，改动太大）：用户留一个联系方式 + 说明，
    管理员核实身份后在后台直接为其设新密码（写新哈希），再线下把新密码告知本人。
    密码仍是单向哈希，全程不出现明文回显。
    """
    __tablename__ = "reset_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True)   # 提交时若用户名命中则关联
    username: Mapped[str] = mapped_column(String(40), index=True)
    contact: Mapped[str | None] = mapped_column(String(80), nullable=True)   # QQ/手机后四位等便于核实
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)  # pending/done/dismissed
    created_at: Mapped[float] = mapped_column(Float, default=time.time, index=True)
    handled_at: Mapped[float | None] = mapped_column(Float, nullable=True)
