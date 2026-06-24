# -*- coding: utf-8 -*-
"""找回密码工单：用户「向管理员申请重置」+ 管理员后台处理。

走「申请—人工核实—管理员重置」这条零外部依赖的路（不接邮件/短信）：
  1) 用户在登录页提交用户名 + 联系方式 + 说明，落一条 pending 工单；
  2) 管理员在后台看到待办，核实身份后直接为其设新密码（写新哈希）；
  3) 工单置 done。全程不出现明文回显，密码仍是单向哈希。
"""
import time

from sqlalchemy import func, select

from core.auth import MAX_PASSWORD_LEN, hash_password
from core.db import session_scope
from core.models import ResetRequest, User

MAX_PENDING_PER_USER = 3   # 同一用户名最多 3 条未处理工单，防刷
CONTACT_MAX = 80
NOTE_MAX = 300


def create_request(username, contact="", note=""):
    """用户提交找回密码申请。返回 (ok, message)。

    为不泄露「用户名是否存在」，无论账号在不在都回同样的成功提示；但仅在
    账号真实存在时才落工单（避免给不存在的用户名刷垃圾工单）。
    """
    username = (username or "").strip()[:40]
    contact = (contact or "").strip()[:CONTACT_MAX]
    note = (note or "").strip()[:NOTE_MAX]
    ok_msg = "申请已提交。管理员核实身份后会为你重置密码，请留意你填写的联系方式。"
    if not username:
        return False, "请填写用户名"
    with session_scope() as s:
        u = s.scalar(select(User).where(User.username == username))
        if not u:
            return True, ok_msg   # 不暴露用户是否存在
        pending = s.scalar(select(func.count()).select_from(ResetRequest).where(
            ResetRequest.username == username, ResetRequest.status == "pending")) or 0
        if pending >= MAX_PENDING_PER_USER:
            return False, "你已有待处理的找回申请，请耐心等待管理员处理。"
        s.add(ResetRequest(user_id=u.id, username=username, contact=contact or None,
                           note=note or None, status="pending", created_at=time.time()))
    return True, ok_msg


# ---------------- 管理员侧 ----------------
def pending_count():
    with session_scope() as s:
        return s.scalar(select(func.count()).select_from(ResetRequest)
                        .where(ResetRequest.status == "pending")) or 0


def list_requests(status="pending", limit=100):
    limit = min(300, max(1, int(limit or 100)))
    with session_scope() as s:
        q = select(ResetRequest)
        if status and status != "all":
            q = q.where(ResetRequest.status == status)
        rows = list(s.scalars(q.order_by(ResetRequest.created_at.desc()).limit(limit)))
        return [{
            "id": r.id, "user_id": r.user_id, "username": r.username,
            "contact": r.contact or "", "note": r.note or "",
            "status": r.status, "created_at": r.created_at, "handled_at": r.handled_at,
        } for r in rows]


def resolve_request(req_id, new_password):
    """管理员核实后为该工单对应账号设新密码，并把工单置为 done。"""
    if not new_password or len(new_password) < 8:
        return "新密码至少 8 位"
    if len(new_password) > MAX_PASSWORD_LEN:
        return "新密码过长（上限 %d 位）" % MAX_PASSWORD_LEN
    pw_hash, salt = hash_password(new_password)
    with session_scope() as s:
        r = s.get(ResetRequest, req_id)
        if not r:
            return "工单不存在"
        if r.status != "pending":
            return "该工单已处理"
        u = s.scalar(select(User).where(User.username == r.username))
        if not u:
            r.status = "dismissed"
            r.handled_at = time.time()
            return "对应账号已不存在，工单已关闭"
        u.pw_hash, u.salt = pw_hash, salt
        r.status = "done"
        r.handled_at = time.time()
        r.user_id = u.id
    return None


def dismiss_request(req_id):
    with session_scope() as s:
        r = s.get(ResetRequest, req_id)
        if not r:
            return "工单不存在"
        r.status = "dismissed"
        r.handled_at = time.time()
    return None
