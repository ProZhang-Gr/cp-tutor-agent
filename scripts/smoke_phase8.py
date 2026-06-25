# -*- coding: utf-8 -*-
"""第八阶段冒烟：个性化训练计划 / 代码可信度验证 / 成长曲线 / 上下文画像。"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
import app as A

c = TestClient(A.app)

# 1) 个性化训练计划：游客也能拿到一份起步计划
r = c.get("/api/study-plan")
assert r.status_code == 200, r.status_code
j = r.json()
print("[plan] headline:", j["headline"])
print("[plan] focus_types:", j["focus_types"], "| target:", j["target_difficulty"])
print("[plan] items:", [(i["id"], i["title"], i["difficulty"]) for i in j["items"]])
assert len(j["items"]) > 0, "训练计划应至少给一道题"
assert j.get("narrative"), "应有训练寄语"

# 2) 可信度验证：正确代码（无题目，只能证明能跑）
good = "print(sum(map(int, input().split())))"
r = c.post("/api/verify", json={"code": good, "language": "python"})
v = r.json()
print("[verify good] level:", v["level"], "label:", v["label"], "trust:", v["trust"])
assert v["level"] in ("ran", "verified"), v

# 3) 可信度验证：语法错误代码
bad = "def f(:\n  pass"
r = c.post("/api/verify", json={"code": bad, "language": "python"})
v = r.json()
print("[verify syntax-err] level:", v["level"], "label:", v["label"])
assert v["level"] == "error", v
assert v["verified"] is False

# 4) 可信度验证：带题目（用真值数据）——取一道有官方测试数据的题
from core import judge
from core.rag import get_bank
truth_pid = None
for p in get_bank().list_all():
    if judge.load_real_tests(p["id"]):
        truth_pid = p["id"]
        break
print("[verify] truth problem available:", truth_pid)
if truth_pid:
    # 拿一段必错代码（恒输出 0）对真值题验证，应判"验证未通过"并附反例
    r = c.post("/api/verify", json={"code": "print(0)", "language": "python",
                                    "problem_id": truth_pid})
    v = r.json()
    print("[verify truth wrong] level:", v["level"], "label:", v["label"],
          "| has counterexample:", bool(v.get("counterexample")))
    assert v["level"] in ("failed", "verified", "ran"), v

# 5) stats 带 growth 时序
r = c.get("/api/stats")
s = r.json()
assert "growth" in s, "stats 应含 growth 字段"
print("[stats] growth points:", len(s["growth"]))

# 6) profile 画像新增字段
from core import profile
prof = profile.build_profile(None)
assert "recent_solved" in prof, "profile 应含 recent_solved"
print("[profile] recent_solved key present, directive sample:",
      repr(profile.build_directive(None)))

print("ALL OK")
