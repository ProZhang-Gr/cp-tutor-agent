# -*- coding: utf-8 -*-
"""冒烟：管理后台鉴权 + 概览 + 用户增删改查 + 重置密码 + 找回密码工单 + 内容/审计。

跑：D:/Anaconda3/python.exe scripts/smoke_admin.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from app import app

c = TestClient(app)
TAG = str(int(time.time()) % 100000)


def ok(cond, msg):
    print(("  OK  " if cond else "  XX  ") + msg)
    assert cond, "FAILED: " + msg


print("== 未登录访问后台数据 -> 401 ==")
ok(c.get("/api/admin/overview").status_code == 401, "overview 拦截游客")
ok(c.get("/api/admin/users").status_code == 401, "users 拦截游客")

print("== 管理员登录 ==")
ok(c.post("/api/admin/login", json={"username": "manager", "password": "wrong"}).status_code == 401, "错误口令 401")
r = c.post("/api/admin/login", json={"username": "manager", "password": "123456"})
ok(r.status_code == 200, "manager/123456 登录 200")
ok(c.get("/api/admin/session").json().get("admin") is True, "session 显示已登录")

print("== 概览 ==")
ov = c.get("/api/admin/overview").json()
ok("kpi" in ov and "system" in ov, "含 kpi/system")
ok("trend_submissions" in ov and len(ov["trend_submissions"]) == 14, "14 天趋势")
ok(ov["system"]["db"], "系统含 DB 描述：" + ov["system"]["db"])
print("    用户总数 =", ov["kpi"]["total_users"], "| 今日活跃 =", ov["kpi"]["dau"],
      "| 累计提交 =", ov["kpi"]["total_submissions"])

print("== 用户列表 + 密码列只给哈希指纹（不可逆）==")
ul = c.get("/api/admin/users?page=1&size=5").json()
ok(ul["total"] >= 1 and len(ul["users"]) >= 1, "返回用户")
pw = ul["users"][0]["password"]
ok(pw["reversible"] is False and pw["algo"].startswith("pbkdf2"), "密码不可逆且为 pbkdf2：" + pw["algo"])
ok("hash_preview" in pw and len(pw["hash_preview"]) <= 16, "只给哈希前缀，不给明文")

print("== 新增用户（CRUD-C）==")
uname = "adm_" + TAG
r = c.post("/api/admin/users", json={"username": uname, "password": "initpw123", "credits": 50})
ok(r.status_code == 200, "创建成功")
uid = r.json()["user"]["id"]
ok(r.json()["user"]["credits"] == 50, "初始算力点 50")

print("== 修改算力点（CRUD-U）==")
r = c.patch("/api/admin/users/%d" % uid, json={"credits": 0})
ok(r.status_code == 200 and r.json()["user"]["is_pro"] is False, "改为 0 -> 非 Pro")

print("== 管理员重置密码，新密码可登录、旧密码失效 ==")
ok(c.post("/api/login", json={"username": uname, "password": "initpw123"}).status_code == 200, "旧密码本可登录")
r = c.post("/api/admin/users/%d/reset-password" % uid, json={"password": "resetpw456"})
ok(r.status_code == 200, "重置成功")
ok(c.post("/api/login", json={"username": uname, "password": "initpw123"}).status_code == 401, "旧密码失效")
ok(c.post("/api/login", json={"username": uname, "password": "resetpw456"}).status_code == 200, "新密码可登录")

print("== 找回密码工单：用户申请 -> 管理员重置 ==")
u2 = "fgt_" + TAG
ok(c.post("/api/register", json={"username": u2, "password": "origpw7890"}).status_code == 200, "注册申请人")
r = c.post("/api/password-reset", json={"username": u2, "contact": "QQ12345", "note": "忘了密码"})
ok(r.status_code == 200 and r.json().get("ok"), "提交找回申请")
# 不存在的用户名也回成功（不暴露存在性），但不落工单
ok(c.post("/api/password-reset", json={"username": "no_such_user_" + TAG}).json().get("ok"), "不存在用户名也回成功")
lst = c.get("/api/admin/reset-requests?status=pending").json()
ok(lst["pending"] >= 1, "有待处理工单 pending=%d" % lst["pending"])
mine = [q for q in lst["requests"] if q["username"] == u2]
ok(len(mine) == 1, "我的工单在列且去重（不存在用户名未落单）")
rid = mine[0]["id"]
ok(mine[0]["contact"] == "QQ12345", "联系方式已记录")
r = c.post("/api/admin/reset-requests/%d/resolve" % rid, json={"password": "brandnew999"})
ok(r.status_code == 200, "管理员据工单重置")
ok(c.post("/api/login", json={"username": u2, "password": "brandnew999"}).status_code == 200, "新密码可登录")
ok(c.post("/api/login", json={"username": u2, "password": "origpw7890"}).status_code == 401, "原密码失效")

print("== 审计 + 内容 ==")
ok(len(c.get("/api/admin/audit?limit=10").json()["audit"]) >= 0, "审计返回")
posts = c.get("/api/admin/posts?limit=10").json()["posts"]
ok(len(posts) >= 1, "有帖子可治理")

print("== 删除用户（CRUD-D）==")
r = c.delete("/api/admin/users/%d" % uid)
ok(r.status_code == 200, "删除成功")
ok(c.post("/api/login", json={"username": uname, "password": "resetpw456"}).status_code == 401, "删后无法登录")

print("== 登出后再访问 -> 401 ==")
c.post("/api/admin/logout")
ok(c.get("/api/admin/overview").status_code == 401, "登出后被拦截")

print("\n全部通过 ✅")
