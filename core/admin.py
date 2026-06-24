# -*- coding: utf-8 -*-
"""管理员后台：鉴权 + 全站运营数据 + 用户增删改查。

设计要点
--------
- 单管理员账号，缺省 manager / 123456，可用环境变量 ADMIN_USER / ADMIN_PASS 覆盖
  （生产部署应在平台 Secret 里改掉，避免弱口令裸奔）。口令用常数时间比较防计时旁路。
- 管理态用独立的 HMAC 签名 token（与普通用户登录态分离，互不影响），带签发时间，
  超过有效期自动失效。
- 密码安全红线：用户口令是 pbkdf2-HMAC-SHA256 加盐**单向**哈希，**无法**还原明文。
  后台只展示「算法 + 迭代次数 + 哈希/盐前缀」以自证加盐存储，并提供「管理员重置密码」
  作为接管账号的正当手段——这是专业系统的正确做法，而非把明文存出来。
"""
import hashlib
import hmac
import os
import platform
import time
from collections import defaultdict, deque
from datetime import datetime

from sqlalchemy import delete, func, select, update

from config import settings
from core.auth import (MAX_PASSWORD_LEN, _NAME_RE, create_user as _auth_create_user,
                       hash_password)
from core.db import engine, session_scope
from core.models import (AuditLog, Post, PostLike, Reply, StudyLog, Submission,
                         User, UserProblem)

# 进程启动时刻：用于「在线时长」。模块导入即记录。
START_TS = time.time()

ADMIN_USER = os.getenv("ADMIN_USER", "manager")
ADMIN_PASS = os.getenv("ADMIN_PASS", "123456")
# 是否仍在用仓库里写死的默认弱口令（公开仓库可见）：启动时据此醒目告警，提醒改 env。
USING_DEFAULT_CREDS = (ADMIN_USER == "manager" and ADMIN_PASS == "123456")

_SECRET = settings.SECRET_KEY.encode()
_TOKEN_TTL = 12 * 3600          # 管理态有效期（秒）

# 登录爆破防护：按 IP 记失败时间戳，窗口内失败达上限即临时锁定（独立于全站限流，
# 更严格，专挡管理口令穷举）。内存态、单实例即够。
_ADMIN_MAX_FAILS = 6
_ADMIN_FAIL_WINDOW = 600        # 统计窗口（秒）
_ADMIN_LOCK_SECONDS = 600       # 触发上限后的锁定时长（秒）
_fails = defaultdict(deque)


# ---------------- 鉴权 ----------------
def verify(username, password):
    """常数时间比对管理员账号口令。"""
    u_ok = hmac.compare_digest((username or "").encode(), ADMIN_USER.encode())
    p_ok = hmac.compare_digest((password or "").encode(), ADMIN_PASS.encode())
    return u_ok and p_ok


def _prune(ip, now):
    q = _fails[ip]
    while q and now - q[0] > _ADMIN_FAIL_WINDOW:
        q.popleft()
    return q


def login_locked(ip):
    """该 IP 是否因连续失败被临时锁定。"""
    now = time.time()
    q = _prune(ip, now)
    if len(q) >= _ADMIN_MAX_FAILS:
        # 最近一次失败起算锁定时长；超过则解锁
        return (now - q[-1]) < _ADMIN_LOCK_SECONDS
    return False


def note_login_fail(ip):
    _fails[ip].append(time.time())


def clear_login_fails(ip):
    _fails.pop(ip, None)


def make_token():
    issued = str(int(time.time()))
    msg = "admin:" + issued
    sig = hmac.new(_SECRET, msg.encode(), hashlib.sha256).hexdigest()
    return "%s.%s" % (msg, sig)


def check_token(token):
    """校验管理态 token：签名正确且未过期。"""
    if not token or token.count(".") != 1:
        return False
    msg, sig = token.rsplit(".", 1)
    good = hmac.new(_SECRET, msg.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, good):
        return False
    try:
        issued = int(msg.split(":", 1)[1])
    except (ValueError, IndexError):
        return False
    return (time.time() - issued) <= _TOKEN_TTL


# ---------------- 工具 ----------------
def _pw_descriptor(pw_hash, salt):
    """把存储的哈希解析成「可展示但不可逆」的描述，自证加盐哈希、绝不泄明文。"""
    h = pw_hash or ""
    if h.startswith("pbkdf2_sha256$"):
        try:
            _, iters, hexh = h.split("$", 2)
        except ValueError:
            iters, hexh = "?", ""
        algo, iters_n = "pbkdf2-sha256", iters
    else:
        algo, iters_n, hexh = "pbkdf2-sha256(legacy)", "100000", h
    return {
        "algo": algo,
        "iters": iters_n,
        "hash_preview": (hexh or "")[:16],
        "salt_preview": (salt or "")[:8],
        "reversible": False,
    }


def _day_key(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def _daily_series(timestamps, days=14):
    """把一串时间戳按本地日期聚合成最近 days 天的 [{date, count}]（补零）。"""
    cnt = {}
    for ts in timestamps:
        cnt[_day_key(ts)] = cnt.get(_day_key(ts), 0) + 1
    today = datetime.now().date()
    out = []
    for i in range(days - 1, -1, -1):
        d = today.fromordinal(today.toordinal() - i)
        k = d.strftime("%Y-%m-%d")
        out.append({"date": k[5:], "count": cnt.get(k, 0)})   # 只留 MM-DD 省地方
    return out


# ---------------- 概览（仪表盘核心数据）----------------
def overview():
    now = time.time()
    day_ago = now - 86400
    today_start = datetime.now().replace(hour=0, minute=0, second=0,
                                         microsecond=0).timestamp()
    with session_scope() as s:
        total_users = s.scalar(select(func.count()).select_from(User)) or 0
        pro_users = s.scalar(select(func.count()).select_from(User)
                             .where(User.credits > 0)) or 0
        total_credits = s.scalar(select(func.coalesce(func.sum(User.credits), 0))) or 0
        today_signups = s.scalar(select(func.count()).select_from(User)
                                 .where(User.created_at >= today_start)) or 0

        total_sub = s.scalar(select(func.count()).select_from(Submission)) or 0
        ac_sub = s.scalar(select(func.count()).select_from(Submission)
                          .where(Submission.passed == 1)) or 0

        total_posts = s.scalar(select(func.count()).select_from(Post)) or 0
        total_replies = s.scalar(select(func.count()).select_from(Reply)) or 0

        llm_today = s.scalar(select(func.count()).select_from(AuditLog)
                             .where(AuditLog.ts >= day_ago)) or 0

        # 今日活跃用户：近 24h 在审计或学习埋点里出现过的登录用户（去重）
        a_uids = set(s.scalars(select(AuditLog.user_id.distinct())
                     .where(AuditLog.ts >= day_ago, AuditLog.user_id.isnot(None))))
        s_uids = set(s.scalars(select(StudyLog.user_id.distinct())
                     .where(StudyLog.ts >= day_ago, StudyLog.user_id.isnot(None))))
        dau = len(a_uids | s_uids)

        # 学习投入汇总
        active_seconds = s.scalar(
            select(func.coalesce(func.sum(StudyLog.active_seconds), 0))) or 0
        total_runs = s.scalar(select(func.coalesce(func.sum(StudyLog.runs), 0))) or 0
        total_submits = s.scalar(
            select(func.coalesce(func.sum(StudyLog.submits), 0))) or 0

        # 近 14 天趋势：提交量 + AI 调用量（拉时间戳到 Python 分桶，规避方言差异）
        sub_ts = list(s.scalars(select(Submission.ts)
                      .where(Submission.ts >= now - 14 * 86400)))
        llm_ts = list(s.scalars(select(AuditLog.ts)
                      .where(AuditLog.ts >= now - 14 * 86400)))

    cap = settings.GLOBAL_DAILY_LLM_CAP or 0
    try:
        from core.rag import get_bank
        bank_count = len(get_bank().list_all())
    except Exception:
        bank_count = 0

    db_url = settings.DATABASE_URL
    if db_url:
        try:
            from urllib.parse import urlparse
            host = urlparse(db_url.replace("postgres://", "postgresql://")).hostname or "?"
        except Exception:
            host = "?"
        db_desc = "PostgreSQL · " + host
    else:
        db_desc = "SQLite · " + os.path.basename(settings.DB_PATH)

    return {
        "kpi": {
            "total_users": total_users,
            "dau": dau,
            "today_signups": today_signups,
            "pro_users": pro_users,
            "total_credits": int(total_credits),
            "total_submissions": total_sub,
            "ac_submissions": ac_sub,
            "ac_rate": round(100 * ac_sub / total_sub) if total_sub else 0,
            "total_posts": total_posts,
            "total_replies": total_replies,
            "active_hours": round(active_seconds / 3600, 1),
            "total_runs": int(total_runs),
            "total_submits": int(total_submits),
        },
        "system": {
            "db": db_desc,
            "uptime_seconds": int(now - START_TS),
            "python": platform.python_version(),
            "platform": platform.system() + " " + platform.release(),
            "engine": engine.dialect.name,
            "bank_count": bank_count,
            "llm_key": bool(settings.DEEPSEEK_API_KEY),
            "llm_today": llm_today,
            "llm_cap": cap,
            "llm_cap_pct": round(100 * llm_today / cap) if cap else 0,
            "rate_per_min": settings.RATE_PER_MIN,
            "now": now,
        },
        "trend_submissions": _daily_series(sub_ts),
        "trend_llm": _daily_series(llm_ts),
    }


# ---------------- 用户列表（含每用户聚合，避免 N+1）----------------
def list_users(q="", page=1, size=20):
    q = (q or "").strip()
    page = max(1, int(page or 1))
    size = min(100, max(1, int(size or 20)))
    with session_scope() as s:
        base = select(User)
        if q:
            base = base.where(User.username.ilike("%" + q + "%"))
        total = s.scalar(select(func.count()).select_from(base.subquery())) or 0
        users = list(s.scalars(base.order_by(User.id.desc())
                     .offset((page - 1) * size).limit(size)))
        uids = [u.id for u in users]

        sub_cnt, ac_cnt, last_sub = {}, {}, {}
        study_sec, last_study = {}, {}
        last_audit = {}
        if uids:
            for uid, c, ac, mx in s.execute(
                select(Submission.user_id, func.count(), func.sum(Submission.passed),
                       func.max(Submission.ts))
                .where(Submission.user_id.in_(uids))
                .group_by(Submission.user_id)):
                sub_cnt[uid] = c or 0
                ac_cnt[uid] = int(ac or 0)
                last_sub[uid] = mx or 0
            for uid, sec, mx in s.execute(
                select(StudyLog.user_id, func.sum(StudyLog.active_seconds),
                       func.max(StudyLog.ts))
                .where(StudyLog.user_id.in_(uids))
                .group_by(StudyLog.user_id)):
                study_sec[uid] = int(sec or 0)
                last_study[uid] = mx or 0
            for uid, mx in s.execute(
                select(AuditLog.user_id, func.max(AuditLog.ts))
                .where(AuditLog.user_id.in_(uids))
                .group_by(AuditLog.user_id)):
                last_audit[uid] = mx or 0

        rows = []
        for u in users:
            last_active = max(last_sub.get(u.id, 0), last_study.get(u.id, 0),
                              last_audit.get(u.id, 0), u.created_at or 0)
            rows.append({
                "id": u.id,
                "username": u.username,
                "created_at": u.created_at,
                "credits": u.credits or 0,
                "is_pro": (u.credits or 0) > 0,
                "submissions": sub_cnt.get(u.id, 0),
                "ac": ac_cnt.get(u.id, 0),
                "active_minutes": round(study_sec.get(u.id, 0) / 60),
                "last_active": last_active,
                "password": _pw_descriptor(u.pw_hash, u.salt),
            })
    return {"users": rows, "total": total, "page": page, "size": size}


def user_detail(uid):
    with session_scope() as s:
        u = s.get(User, uid)
        if not u:
            return None
        subs = list(s.scalars(select(Submission)
                    .where(Submission.user_id == uid)
                    .order_by(Submission.ts.desc()).limit(20)))
        posts = list(s.scalars(select(Post)
                     .where(Post.user_id == uid)
                     .order_by(Post.created_at.desc()).limit(20)))
        study = s.execute(select(func.coalesce(func.sum(StudyLog.active_seconds), 0),
                                 func.coalesce(func.sum(StudyLog.runs), 0),
                                 func.coalesce(func.sum(StudyLog.submits), 0),
                                 func.coalesce(func.sum(StudyLog.keystrokes), 0))
                          ).one()
        return {
            "id": u.id, "username": u.username, "created_at": u.created_at,
            "credits": u.credits or 0, "is_pro": (u.credits or 0) > 0,
            "password": _pw_descriptor(u.pw_hash, u.salt),
            "study": {"active_minutes": round((study[0] or 0) / 60),
                      "runs": int(study[1] or 0), "submits": int(study[2] or 0),
                      "keystrokes": int(study[3] or 0)},
            "submissions": [{
                "id": r.id, "ts": r.ts, "problem_title": r.problem_title,
                "problem_type": r.problem_type, "passed": bool(r.passed),
                "score": r.score, "error_kind": r.error_kind or "AC",
            } for r in subs],
            "posts": [{"id": p.id, "tag": p.tag, "title": p.title,
                       "likes": p.likes, "reply_count": p.reply_count,
                       "created_at": p.created_at} for p in posts],
        }


# ---------------- 用户增删改 ----------------
def create_user(username, password, credits=0):
    err = _validate(username, password)
    if err:
        return None, err
    user, e = _auth_create_user(username, password)
    if e:
        return None, e
    credits = max(0, int(credits or 0))
    if credits:
        with session_scope() as s:
            u = s.get(User, user["id"])
            if u:
                u.credits = credits
    return {"id": user["id"], "username": user["username"], "credits": credits}, None


def update_user(uid, username=None, credits=None):
    with session_scope() as s:
        u = s.get(User, uid)
        if not u:
            return None, "用户不存在"
        if username is not None:
            username = username.strip()
            if not _NAME_RE.match(username):
                return None, "用户名需 2-20 位，限字母/数字/下划线/中文"
            dup = s.scalar(select(User).where(User.username == username, User.id != uid))
            if dup:
                return None, "用户名已存在"
            u.username = username
        if credits is not None:
            try:
                u.credits = max(0, int(credits))
            except (TypeError, ValueError):
                return None, "算力点需为非负整数"
        return {"id": u.id, "username": u.username, "credits": u.credits,
                "is_pro": u.credits > 0}, None


def reset_password(uid, new_password):
    if not new_password or len(new_password) < 8:
        return "新密码至少 8 位"
    if len(new_password) > MAX_PASSWORD_LEN:
        return "新密码过长（上限 %d 位）" % MAX_PASSWORD_LEN
    pw_hash, salt = hash_password(new_password)
    with session_scope() as s:
        u = s.get(User, uid)
        if not u:
            return "用户不存在"
        u.pw_hash, u.salt = pw_hash, salt
    return None


def delete_user(uid):
    """删除用户。其私有数据（提交/埋点/题单/点赞）一并清除；社群帖子/回帖
    改为匿名（user_id 置空、保留冗余 username），以免破坏他人讨论的引用完整性。"""
    with session_scope() as s:
        u = s.get(User, uid)
        if not u:
            return "用户不存在"
        s.execute(delete(PostLike).where(PostLike.user_id == uid))
        s.execute(delete(UserProblem).where(UserProblem.user_id == uid))
        s.execute(delete(Submission).where(Submission.user_id == uid))
        s.execute(delete(StudyLog).where(StudyLog.user_id == uid))
        s.execute(update(Post).where(Post.user_id == uid).values(user_id=None))
        s.execute(update(Reply).where(Reply.user_id == uid).values(user_id=None))
        s.delete(u)
    return None


def _validate(username, password):
    if not username or not _NAME_RE.match(username.strip()):
        return "用户名需 2-20 位，限字母/数字/下划线/中文"
    if not password or len(password) < 8:
        return "密码至少 8 位"
    if len(password) > MAX_PASSWORD_LEN:
        return "密码过长（上限 %d 位）" % MAX_PASSWORD_LEN
    return None


# ---------------- 活动审计流 ----------------
def recent_audit(limit=80):
    limit = min(300, max(1, int(limit or 80)))
    with session_scope() as s:
        rows = list(s.scalars(select(AuditLog).order_by(AuditLog.ts.desc()).limit(limit)))
        uids = [r.user_id for r in rows if r.user_id is not None]
        names = {}
        if uids:
            for uid, nm in s.execute(select(User.id, User.username)
                                     .where(User.id.in_(set(uids)))):
                names[uid] = nm
        return [{
            "ts": r.ts, "user_id": r.user_id,
            "username": names.get(r.user_id) if r.user_id is not None else "游客",
            "ip": r.ip or "?", "endpoint": r.endpoint or "?",
            "meta": (r.meta or "")[:160],
        } for r in rows]


# ---------------- 内容管理 ----------------
def list_posts_admin(limit=100):
    limit = min(300, max(1, int(limit or 100)))
    with session_scope() as s:
        rows = list(s.scalars(select(Post).order_by(Post.created_at.desc()).limit(limit)))
        return [{
            "id": p.id, "username": p.username, "tag": p.tag, "title": p.title,
            "likes": p.likes, "reply_count": p.reply_count, "created_at": p.created_at,
            "anonymous": p.user_id is None,
        } for p in rows]


def delete_post(pid):
    with session_scope() as s:
        p = s.get(Post, pid)
        if not p:
            return "帖子不存在"
        s.execute(delete(PostLike).where(PostLike.post_id == pid))
        s.execute(delete(Reply).where(Reply.post_id == pid))
        s.delete(p)
    return None
