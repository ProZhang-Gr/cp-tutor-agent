# -*- coding: utf-8 -*-
"""冒烟：/api/run 端点的 C++ 编译运行 + Python 回归 + 语言兜底。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from app import app

c = TestClient(app)


def ok(cond, msg):
    print(("  OK  " if cond else "  XX  ") + msg)
    assert cond, "FAILED: " + msg


CPP = ("#include <iostream>\nusing namespace std;\n"
       "int main(){int a,b;cin>>a>>b;cout<<a+b<<endl;return 0;}\n")
PY = "a,b=map(int,input().split());print(a+b)\n"

print("== /api/run C++ ==")
r = c.post("/api/run", json={"code": CPP, "stdin": "2 3\n", "language": "cpp"}).json()
ok(r["status"] == "OK", "状态 OK，实得 %s / %s" % (r["status"], (r.get("stderr") or "")[:120]))
ok(r["stdout"].strip() == "5", "输出 5，实得 %r" % r["stdout"])

print("== /api/run C++ 编译错误 -> CE ==")
r = c.post("/api/run", json={"code": "int main(){ oops }", "stdin": "", "language": "cpp"}).json()
ok(r["status"] == "CE", "状态 CE，实得 %s" % r["status"])

print("== /api/run Python 回归 ==")
r = c.post("/api/run", json={"code": PY, "stdin": "10 20\n", "language": "python"}).json()
ok(r["status"] == "OK" and r["stdout"].strip() == "30", "Python OK 输出 30，实得 %r" % r["stdout"])

print("== /api/run 未知语言兜底为 Python ==")
r = c.post("/api/run", json={"code": PY, "stdin": "1 1\n", "language": "rust"}).json()
ok(r["status"] == "OK" and r["stdout"].strip() == "2", "兜底跑 Python 输出 2，实得 %r" % r["stdout"])

print("\n全部通过 ✅")
