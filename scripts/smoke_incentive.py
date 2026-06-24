# -*- coding: utf-8 -*-
"""冒烟：每日签到 / 学习行为埋点 / 社群答疑奖励 端到端验证（TestClient）。

按记忆告诫：新端点务必跑 TestClient 验真，别只信 py_compile。
运行：D:/Anaconda3/python.exe scripts/smoke_incentive.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from app import app
from config import settings

c = TestClient(app)
U = "smoke_%d" % (int(time.time()) % 100000)
PW = "test12345"


def ok(cond, msg):
    print(("  ✅ " if cond else "  ❌ ") + msg)
    assert cond, "FAILED: " + msg


print("== 注册 ==")
r = c.post("/api/register", json={"username": U, "password": PW})
ok(r.status_code == 200, "注册 200")

print("== 签到 ==")
r = c.get("/api/me").json()
ok(r.get("checkin", {}).get("today") is False, "初始未签到")
r = c.post("/api/checkin")
ok(r.status_code == 200, "首次签到 200")
ok(r.json().get("gained") == settings.CHECKIN_POINTS, "发放 %d 点" % settings.CHECKIN_POINTS)
r2 = c.post("/api/checkin")
ok(r2.status_code == 409, "当日重复签到 409")
ok(c.get("/api/me").json()["checkin"]["today"] is True, "签到后 me.checkin.today=True")

print("== 学习行为埋点 ==")
r = c.post("/api/telemetry", json={"problem_id": "P1", "active_seconds": 120,
                                   "keystrokes": 50, "runs": 2, "submits": 1})
ok(r.status_code == 200 and r.json()["saved"] is True, "埋点写入 saved=True")
r = c.post("/api/telemetry", json={"active_seconds": 0, "keystrokes": 0, "runs": 0, "submits": 0})
ok(r.json()["saved"] is False, "全 0 段静默忽略 saved=False")
r = c.post("/api/telemetry", json={"active_seconds": 999999, "keystrokes": 9}).json()
ok(True, "超大时长上报不报错（服务端截断）")
s = c.get("/api/telemetry/summary").json()
ok(s["total_keystrokes"] == 59, "击键累计 59（50+9）实得 %s" % s["total_keystrokes"])
ok(s["total_minutes"] >= 2.0, "累计专注时长 ≥2 分钟，实得 %s" % s["total_minutes"])
ok(s["total_minutes"] <= 2 + settings.TELEMETRY_MAX_SECONDS / 60 + 0.1, "超大时长被截断")

print("== 社群答疑奖励 ==")
r = c.post("/api/community/posts", json={"tag": "题解", "title": "冒烟题解贴",
                                         "body": "这是一条用于冒烟测试的题解正文，足够长。"})
ok(r.status_code == 200, "发帖 200")
ok(r.json().get("reward") == settings.POST_REWARD_POINTS, "发帖奖励 %d 点，实得 %s"
   % (settings.POST_REWARD_POINTS, r.json().get("reward")))
pid = r.json()["post"]["id"]
r = c.post("/api/community/posts/%d/reply" % pid, json={"body": "这是一条冒烟测试回帖，帮你答疑。"})
ok(r.status_code == 200, "回帖 200")
ok(r.json().get("reward") == settings.REPLY_REWARD_POINTS, "回帖奖励 %d 点，实得 %s"
   % (settings.REPLY_REWARD_POINTS, r.json().get("reward")))

print("== 游客边界 ==")
g = TestClient(app)
ok(g.post("/api/checkin").status_code == 401, "游客签到 401")
ok(g.post("/api/telemetry", json={"active_seconds": 30}).status_code == 200, "游客埋点 200（计入游客桶）")

print("\n全部通过 ✅")
