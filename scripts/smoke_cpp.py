# -*- coding: utf-8 -*-
"""冒烟：C++ 编译运行 / 编译错误 / Program 编译一次多次跑 / Python 回归。
运行：D:/Anaconda3/python.exe scripts/smoke_cpp.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import sandbox

CPP_OK = r'''
#include <bits/stdc++.h>
using namespace std;
int main(){
    int n; long long t;
    if(!(cin>>n>>t)) return 0;
    vector<long long> a(n);
    for(auto&x:a) cin>>x;
    for(int i=0;i<n;i++) for(int j=i+1;j<n;j++)
        if(a[i]+a[j]==t){ cout<<i<<" "<<j<<"\n"; return 0; }
    cout<<-1<<"\n";
    return 0;
}
'''

CPP_CE = "int main(){ this is not c++ ; }"
CPP_TLE = "#include <bits/stdc++.h>\nint main(){ while(1){} }"
PY_OK = "import sys\nd=sys.stdin.read().split()\nprint(int(d[0])+int(d[1]))\n"


def ok(c, m):
    print(("  OK  " if c else "  XX  ") + m)
    assert c, "FAILED: " + m


print("== C++ 编译运行 ==")
r = sandbox.run_code(CPP_OK, "cpp", "4 9\n2 7 11 15\n")
ok(r["status"] == "OK", "状态 OK，实得 %s" % r["status"])
ok(r["stdout"].split() == ["0", "1"], "输出 0 1，实得 %r" % r["stdout"])

print("== C++ 编译错误 -> CE ==")
r = sandbox.run_code(CPP_CE, "cpp", "")
ok(r["status"] == "CE", "状态 CE，实得 %s" % r["status"])
ok("main.cpp" in (r["stderr"] or "") or r["stderr"], "CE 带编译报错")

print("== C++ 死循环 -> TLE ==")
t0 = time.time()
r = sandbox.run_code(CPP_TLE, "cpp", "", timeout=2)
ok(r["status"] == "TLE", "状态 TLE，实得 %s" % r["status"])
ok(time.time() - t0 < 6, "TLE 及时返回（<6s）")

print("== Program：编译一次，多次运行 ==")
prog = sandbox.prepare(CPP_OK, "cpp")
ok(prog.ok(), "编译成功")
r1 = prog.run("4 9\n2 7 11 15\n"); r2 = prog.run("3 5\n1 2 4\n")
ok(r1["stdout"].split() == ["0", "1"], "复用#1 正确")
ok(r2["stdout"].split() == ["0", "2"], "复用#2 正确（a0=1+a2=4=5→0 2）实得 %r" % r2["stdout"])
prog.close()

print("== judge_by_truth（C++）==")
from core import judge
tests = [{"input": "4 9\n2 7 11 15\n", "expected": "0 1\n", "kind": "样例"},
         {"input": "3 5\n1 2 4\n", "expected": "0 2\n", "kind": "隐藏"}]
jr = judge.judge_by_truth(CPP_OK, tests, language="cpp")
ok(jr["verdict"] == "AC" and jr["passed"] == 2, "两组全过 AC，实得 %s %s/%s" % (jr["verdict"], jr["passed"], jr["total"]))

print("== Python 回归 ==")
r = sandbox.run_code(PY_OK, "python", "2 3\n")
ok(r["status"] == "OK" and r["stdout"].strip() == "5", "Python 仍正常，实得 %r" % r["stdout"])

print("\n全部通过 ✅")
