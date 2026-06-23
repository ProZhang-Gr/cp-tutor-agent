# -*- coding: utf-8 -*-
"""认证：密码加盐哈希（pbkdf2，标准库）+ HMAC 签名的无状态登录 token。"""
import hashlib
import hmac
import os
import re
import time

from sqlalchemy import select

from config import settings
from core.db import session_scope
from core.models import User

_SECRET = settings.SECRET_KEY.encode()


# ---------------- 密码 ----------------
# 现行 pbkdf2 迭代次数（OWASP 量级）。哈希自描述存迭代次数，旧账号按各自存储的
# 次数校验、登录成功后平滑升级，调参不会把老用户锁在门外。
_PBKDF2_ITERS = 260_000
_LEGACY_ITERS = 100_000   # 历史账号（纯 hex、无前缀）隐含的迭代次数
MAX_PASSWORD_LEN = 128    # 防超长口令把 pbkdf2 拖成 CPU DoS


def _pbkdf2(password, salt_bytes, iters):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, iters).hex()


def hash_password(password, salt=None, iters=_PBKDF2_ITERS):
    if salt is None:
        salt = os.urandom(16).hex()
    h = _pbkdf2(password, bytes.fromhex(salt), iters)
    # 自描述格式：pbkdf2_sha256$<迭代次数>$<hex哈希>
    return "pbkdf2_sha256$%d$%s" % (iters, h), salt


def _verify_password(password, salt, stored):
    """校验密码，兼容旧格式（纯 hex，隐含 100000 次）与新自描述格式。"""
    if not stored:
        return False
    if stored.startswith("pbkdf2_sha256$"):
        try:
            _, iters_s, hexh = stored.split("$", 2)
            iters = int(iters_s)
        except ValueError:
            return False
        calc = _pbkdf2(password, bytes.fromhex(salt), iters)
        return hmac.compare_digest(calc, hexh)
    # 旧格式：纯 hex
    calc = _pbkdf2(password, bytes.fromhex(salt), _LEGACY_ITERS)
    return hmac.compare_digest(calc, stored)


def _needs_upgrade(stored):
    """旧格式或迭代次数低于现行值 → 登录成功后顺手升级到更强的哈希。"""
    if not stored or not stored.startswith("pbkdf2_sha256$"):
        return True
    try:
        return int(stored.split("$", 2)[1]) < _PBKDF2_ITERS
    except (ValueError, IndexError):
        return True


# ---------------- 登录 token（签名 Cookie）----------------
def make_token(user_id):
    msg = str(user_id)
    sig = hmac.new(_SECRET, msg.encode(), hashlib.sha256).hexdigest()
    return "%s.%s" % (msg, sig)


def parse_token(token):
    if not token or "." not in token:
        return None
    msg, sig = token.rsplit(".", 1)
    good = hmac.new(_SECRET, msg.encode(), hashlib.sha256).hexdigest()
    if hmac.compare_digest(sig, good):
        try:
            return int(msg)
        except ValueError:
            return None
    return None


# ---------------- 用户 ----------------
_NAME_RE = re.compile(r"^[A-Za-z0-9_一-龥]{2,20}$")


def validate_credentials(username, password):
    if not username or not _NAME_RE.match(username):
        return "用户名需 2-20 位，限字母/数字/下划线/中文"
    if not password or len(password) < 8:
        return "密码至少 8 位"
    if len(password) > MAX_PASSWORD_LEN:
        return "密码过长（上限 %d 位）" % MAX_PASSWORD_LEN
    return None


def get_user_by_name(username):
    with session_scope() as s:
        u = s.scalar(select(User).where(User.username == username))
        if not u:
            return None
        return {"id": u.id, "username": u.username, "pw_hash": u.pw_hash, "salt": u.salt}


def get_user_by_id(uid):
    with session_scope() as s:
        u = s.get(User, uid)
        if not u:
            return None
        return {"id": u.id, "username": u.username, "created_at": u.created_at}


def create_user(username, password):
    if get_user_by_name(username):
        return None, "用户名已存在"
    pw_hash, salt = hash_password(password)
    with session_scope() as s:
        u = User(username=username, pw_hash=pw_hash, salt=salt, created_at=time.time())
        s.add(u)
        s.flush()
        return {"id": u.id, "username": u.username}, None


def _upgrade_hash(uid, password):
    """登录成功后把旧/弱哈希升级为现行强度（best-effort，失败不影响登录）。"""
    try:
        new_hash, new_salt = hash_password(password)
        with session_scope() as s:
            u = s.get(User, uid)
            if u:
                u.pw_hash, u.salt = new_hash, new_salt
    except Exception:
        pass


def authenticate(username, password):
    # 超长口令直接拒绝，避免 pbkdf2 被超长输入拖成 CPU 消耗
    if password is None or len(password) > MAX_PASSWORD_LEN:
        return None
    user = get_user_by_name(username)
    if not user:
        # 用户不存在也跑一次等强度哈希，抹平"用户是否存在"的响应时间差（防用户名枚举）
        _pbkdf2(password or "", b"\x00" * 16, _PBKDF2_ITERS)
        return None
    if not _verify_password(password, user["salt"], user["pw_hash"]):
        return None
    if _needs_upgrade(user["pw_hash"]):
        _upgrade_hash(user["id"], password)
    return {"id": user["id"], "username": user["username"]}
