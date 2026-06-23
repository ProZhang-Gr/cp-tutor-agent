# -*- coding: utf-8 -*-
"""防滥用守门：IP 限流（内存滑动窗口）+ 每日配额（DB 审计计数）+ 审计日志。

每个 LLM 端点调用前 check_and_log()：
  1. 按 IP 限流（防突发刷接口）
  2. 按用户/游客的 24h 配额（防长期白嫖、给花费封顶）
  3. 通过则写一条审计记录（同时供每日报告使用）
返回 (ok, message)。
"""
import time
from collections import defaultdict, deque

from sqlalchemy import func, select

from config import settings
from core.db import session_scope
from core.models import AuditLog

# IP -> 最近请求时间戳队列（内存滑动窗口，单进程足够）
_hits = defaultdict(deque)


def _rate_ok(ip):
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= settings.RATE_PER_MIN:
        return False
    q.append(now)
    return True


def _quota_used(user_id, ip):
    """过去 24h 该用户(或游客IP)的 LLM 调用次数。"""
    since = time.time() - 86400
    with session_scope() as s:
        cond = AuditLog.user_id == user_id if user_id is not None \
            else (AuditLog.user_id.is_(None)) & (AuditLog.ip == ip)
        return s.scalar(select(func.count()).select_from(AuditLog)
                        .where(AuditLog.ts >= since, cond)) or 0


def _global_used():
    """过去 24h 全站 LLM 调用总次数（给花费兜底）。"""
    since = time.time() - 86400
    with session_scope() as s:
        return s.scalar(select(func.count()).select_from(AuditLog)
                        .where(AuditLog.ts >= since)) or 0


def rate_limit_only(ip):
    """仅做 IP 限流（不计 LLM 配额、不写审计）。用于代码运行、登录等非 LLM 端点。"""
    if not _rate_ok(ip):
        return False, "请求过于频繁，请稍后再试（每分钟上限 %d 次）" % settings.RATE_PER_MIN
    return True, ""


def check_and_log(ip, user_id, endpoint, is_pro=False, meta=None):
    """返回 (ok, message)。ok=True 时已写入审计（含 IP / UA 等监控信息）。"""
    if not _rate_ok(ip):
        return False, "请求过于频繁，请稍后再试（每分钟上限 %d 次）" % settings.RATE_PER_MIN
    # 全站每日总量兜底（含 Pro）：达到上限所有人当日降级，保护 LLM 花费
    if settings.GLOBAL_DAILY_LLM_CAP and _global_used() >= settings.GLOBAL_DAILY_LLM_CAP:
        return False, "今日平台 AI 调用量已达上限，为保障服务稳定请明天再试。"
    if not is_pro:
        limit = settings.QUOTA_USER if user_id is not None else settings.QUOTA_GUEST
        if _quota_used(user_id, ip) >= limit:
            return False, "今日额度已用完（%d 次/天）。登录或升级 Pro 可提升额度。" % limit
    with session_scope() as s:
        s.add(AuditLog(ts=time.time(), user_id=user_id, ip=ip, endpoint=endpoint,
                       meta=(meta or "")[:300] or None))
    return True, ""


def count_endpoint_today(user_id, endpoint):
    """过去 24h 该用户在某端点的调用次数（用于看广告等按日限次）。"""
    since = time.time() - 86400
    with session_scope() as s:
        return s.scalar(select(func.count()).select_from(AuditLog)
                        .where(AuditLog.ts >= since, AuditLog.user_id == user_id,
                               AuditLog.endpoint == endpoint)) or 0


def log_event(user_id, ip, endpoint):
    """写一条审计记录（不做限流/配额判断）。"""
    with session_scope() as s:
        s.add(AuditLog(ts=time.time(), user_id=user_id, ip=ip, endpoint=endpoint))
