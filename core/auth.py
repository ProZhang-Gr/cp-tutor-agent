# -*- coding: utf-8 -*-
"""认证：密码加盐哈希（pbkdf2，标准库）+ HMAC 签名的无状态登录 token。"""
import hashlib
import hmac
import os
import re
import time

from config import settings
from core import db

_SECRET = settings.SECRET_KEY.encode()


# ---------------- 密码 ----------------
def hash_password(password, salt=None):
    if salt is None:
        salt = os.urandom(16).hex()
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 100_000).hex()
    return h, salt


def _verify_password(password, salt, expected):
    h, _ = hash_password(password, salt)
    return hmac.compare_digest(h, expected)


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
    if not password or len(password) < 6:
        return "密码至少 6 位"
    return None


def get_user_by_name(username):
    return db.query_one("SELECT * FROM users WHERE username = ?", (username,))


def get_user_by_id(uid):
    return db.query_one("SELECT id, username, created_at FROM users WHERE id = ?", (uid,))


def create_user(username, password):
    if get_user_by_name(username):
        return None, "用户名已存在"
    pw_hash, salt = hash_password(password)
    db.execute(
        "INSERT INTO users (username, pw_hash, salt, created_at) VALUES (?,?,?,?)",
        (username, pw_hash, salt, time.time()),
    )
    user = get_user_by_name(username)
    return {"id": user["id"], "username": user["username"]}, None


def authenticate(username, password):
    user = get_user_by_name(username)
    if not user or not _verify_password(password, user["salt"], user["pw_hash"]):
        return None
    return {"id": user["id"], "username": user["username"]}
