# -*- coding: utf-8 -*-
"""会员计费（模拟）：算力点 credits。credits>0 即 Pro。

充值为模拟（不接真实支付）：¥X → +X*CREDITS_PER_YUAN 算力点。
Pro 不受每日配额限制，但每次 LLM 调用消耗 1 算力点。
"""
from core.db import session_scope
from core.models import User

CREDITS_PER_YUAN = 10


def get_status(uid):
    if uid is None:
        return {"credits": 0, "is_pro": False}
    with session_scope() as s:
        u = s.get(User, uid)
        c = u.credits if u else 0
        return {"credits": c, "is_pro": c > 0}


def recharge(uid, yuan):
    if uid is None:
        return None
    add = max(0, int(yuan)) * CREDITS_PER_YUAN
    with session_scope() as s:
        u = s.get(User, uid)
        if not u:
            return None
        u.credits += add
        return u.credits


def spend(uid, n=1):
    """消耗算力点；成功返回剩余，余额不足返回 None。"""
    if uid is None:
        return None
    with session_scope() as s:
        u = s.get(User, uid)
        if not u or u.credits < n:
            return None
        u.credits -= n
        return u.credits
