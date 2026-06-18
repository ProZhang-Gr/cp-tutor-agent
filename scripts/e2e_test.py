# -*- coding: utf-8 -*-
"""端到端冒烟测试：真值判题 → 反例 → 调试 agent。"""
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8011"


def sse_post(path, payload):
    req = urllib.request.Request(BASE + path,
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    events = []
    with urllib.request.urlopen(req, timeout=180) as r:
        for raw in r:
            line = raw.decode("utf-8").strip()
            if line.startswith("data:"):
                events.append(json.loads(line[5:].strip()))
    return events


def wait_ready():
    for _ in range(40):
        try:
            urllib.request.urlopen(BASE + "/api/problems", timeout=3).read()
            return True
        except Exception:
            time.sleep(0.5)
    return False


def main():
    if not wait_ready():
        print("server not ready"); sys.exit(1)

    probs = json.loads(urllib.request.urlopen(BASE + "/api/problems", timeout=10).read())
    cc = [p for p in probs if str(p["id"]).startswith("CC")]
    print("[problems] total=%d  CC=%d" % (len(probs), len(cc)))

    # 用 CC0001 的描述 + 一个错误解（漏了 n//11 上限）触发真值 WA
    p = next(x for x in probs if x["id"] == "CC0001")
    wrong = "n=int(input())\ns=input().strip()\nprint(s.count('8'))\n"
    evs = sse_post("/api/evaluate", {
        "problem": p["description"], "code": wrong, "language": "python",
        "problem_id": "CC0001", "problem_title": p["title"],
        "problem_type": p["type"], "difficulty": p["difficulty"]})
    judge = summary = None
    for e in evs:
        if e.get("event") == "node" and e.get("node") == "judge":
            judge = e["data"]["judge"]
        if e.get("event") == "node" and e.get("node") == "summarize":
            summary = e["data"]["summary"]
    print("[evaluate] mode=%s verdict=%s passed=%s/%s" % (
        judge["mode"], judge["verdict"], judge["passed"], judge["total"]))
    ce = judge.get("counterexample")
    print("[evaluate] summary=%s score=%s" % (summary["verdict"], summary["final_score"]))
    print("[evaluate] counterexample input=%r expected=%r got=%r" % (
        ce["input"][:30], ce["expected"][:10], ce["actual"][:10]))

    # 把反例喂给调试 agent
    devs = sse_post("/api/debug", {
        "problem": p["description"], "code": wrong, "counterexample": ce})
    kinds = [e.get("event") for e in devs]
    runs = sum(1 for k in kinds if k == "action")
    concl = next((e["data"] for e in devs if e.get("event") == "conclusion"), None)
    print("[debug] events=%s  sandbox_runs=%d" % (kinds, runs))
    if concl:
        print("[debug] root_cause=%s" % concl["root_cause"][:120])
    print("\nALL OK" if judge["verdict"] == "WA" and concl else "\nCHECK FAILED")


if __name__ == "__main__":
    main()
