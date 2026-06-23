# -*- coding: utf-8 -*-
"""双轨判题引擎。

判题不再依赖"让 LLM 想象期望输出"，而是建立真正的真值来源：

  轨道一 · 真值判定（truth）：题目带官方测试数据（data/tests/<id>.json）时，
      直接拿真实数据逐组比对，确定性最硬，等同 OJ。

  轨道二 · 对拍（stress / 差分测试）：题目没有数据（用户自己粘的题）时，
      让 LLM 产出「朴素暴力解 + 随机数据生成器」，先用题面样例校验暴力解可信度，
      再用大量小规模随机数据让「用户解」和「暴力解」对拍，第一处不一致即为最小反例。
      这正是竞赛选手手动"对拍"的自动化版本。

两条轨道都返回统一结构，并在 WA 时给出一个具体反例（input / expected / actual），
供 Agentic 调试回路进一步定位。
"""
import os

from config import settings
from core import agents, sandbox
from core.sandbox import AC, CE, RE, TLE, WA, _normalize, run_python


def _trunc(s, n=1200):
    s = s or ""
    return s if len(s) <= n else s[:n] + "\n…（已截断）"


def load_real_tests(problem_id):
    """读取题目的官方真实测试数据；没有则返回 None。

    problem_id 来自客户端，直接拼路径会有目录穿越风险（如 ../../xxx），
    故解析后强制校验最终路径仍落在 TESTS_DIR 内，越界一律拒绝。
    """
    if not problem_id:
        return None
    tests_dir = os.path.abspath(settings.TESTS_DIR)
    path = os.path.abspath(os.path.join(tests_dir, str(problem_id) + ".json"))
    if os.path.commonpath([tests_dir, path]) != tests_dir:
        return None   # 目录穿越尝试，拒绝
    if not os.path.exists(path):
        return None
    try:
        import json
        with open(path, "r", encoding="utf-8") as f:
            cases = json.load(f)
        return cases or None
    except Exception:
        return None


# ===================== 轨道一：真值判定 =====================
def judge_by_truth(code, tests, timeout=None):
    """对真实测试数据逐组判题，遇首个不通过即停（贴近 OJ）。"""
    timeout = timeout or settings.SANDBOX_TIMEOUT
    total = len(tests)
    passed = 0
    detail = []
    counterexample = None
    verdict = AC

    for i, tc in enumerate(tests):
        inp = tc.get("input", "") or ""
        expected = tc.get("expected", "") or ""
        run = run_python(code, inp, timeout)
        st = run["status"]

        if st == CE:
            return {
                "mode": "truth", "verdict": CE, "passed": 0, "total": total,
                "results": [{"index": 0, "kind": tc.get("kind", ""), "status": CE,
                             "input": "", "expected": "", "actual": run["stderr"]}],
                "counterexample": None,
            }
        if st in (TLE, RE):
            verdict = st
            counterexample = {"input": _trunc(inp), "expected": _trunc(expected),
                              "actual": _trunc(run["stderr"] or "(无输出)"), "reason": st}
            detail.append({"index": i, "kind": tc.get("kind", ""), "status": st,
                           "input": _trunc(inp, 400), "expected": _trunc(expected, 400),
                           "actual": _trunc(run["stderr"], 400)})
            break
        if _normalize(run["stdout"]) == _normalize(expected):
            passed += 1
            detail.append({"index": i, "kind": tc.get("kind", ""), "status": AC,
                           "input": _trunc(inp, 400), "expected": _trunc(expected, 400),
                           "actual": _trunc(run["stdout"], 400)})
        else:
            verdict = WA
            counterexample = {"input": _trunc(inp), "expected": _trunc(expected),
                              "actual": _trunc(run["stdout"]), "reason": WA}
            detail.append({"index": i, "kind": tc.get("kind", ""), "status": WA,
                           "input": _trunc(inp, 400), "expected": _trunc(expected, 400),
                           "actual": _trunc(run["stdout"], 400)})
            break

    if counterexample is None:
        verdict = AC
    return {
        "mode": "truth", "verdict": verdict, "passed": passed, "total": total,
        "results": detail, "counterexample": counterexample,
    }


# ===================== 轨道二：对拍（差分测试） =====================
def _run_ok(code, stdin, timeout):
    r = run_python(code, stdin, timeout)
    return r["status"] == "OK", r


def judge_by_stress(problem, code, trials=None, timeout=None):
    """用 LLM 暴力解当真值对拍用户解，抓最小反例。"""
    trials = trials or settings.STRESS_TRIALS
    timeout = timeout or settings.STRESS_TIMEOUT

    kit = agents.gen_stress_kit(problem)
    brute, gen, samples = kit["brute_code"], kit["gen_code"], kit["samples"]

    if not brute or not gen:
        return {"mode": "stress", "verdict": "NO_KIT", "passed": 0, "total": 0,
                "results": [], "counterexample": None,
                "stress": {"brute_ok": False, "trials": 0,
                           "note": "无法自动生成对拍工具，已退回静态审查评分。"}}

    # 1) 校验暴力解：它得先通过题面样例，否则真值不可信
    brute_ok = True
    for s in samples:
        ok, r = _run_ok(brute, s.get("input", ""), timeout)
        if not ok or _normalize(r["stdout"]) != _normalize(s.get("output", "")):
            brute_ok = False
            break

    detail = []

    # 2) 先用题面样例直接判用户解（最高可信度的反例来源）
    for i, s in enumerate(samples):
        inp, exp = s.get("input", ""), s.get("output", "")
        run = run_python(code, inp, timeout)
        st = run["status"]
        if st == CE:
            return {"mode": "stress", "verdict": CE, "passed": 0, "total": len(samples),
                    "results": [{"index": 0, "kind": "样例", "status": CE,
                                 "input": "", "expected": "", "actual": run["stderr"]}],
                    "counterexample": None,
                    "stress": {"brute_ok": brute_ok, "trials": 0, "note": "样例阶段语法错误"}}
        passed_case = st == "OK" and _normalize(run["stdout"]) == _normalize(exp)
        detail.append({"index": i, "kind": "样例", "status": AC if passed_case else (st if st != "OK" else WA),
                       "input": _trunc(inp, 400), "expected": _trunc(exp, 400),
                       "actual": _trunc(run["stdout"] if st == "OK" else run["stderr"], 400)})
        if not passed_case:
            ce = {"input": _trunc(inp), "expected": _trunc(exp),
                  "actual": _trunc(run["stdout"] if st == "OK" else run["stderr"]),
                  "reason": st if st != "OK" else WA}
            return {"mode": "stress", "verdict": st if st in (TLE, RE) else WA,
                    "passed": i, "total": len(samples), "results": detail,
                    "counterexample": ce,
                    "stress": {"brute_ok": brute_ok, "trials": 0,
                               "note": "题面样例即不通过"}}

    # 3) 随机对拍：用暴力解当真值，逐组找第一处分歧
    done = 0
    for seed in range(trials):
        ok_g, rg = _run_ok(gen, str(seed), timeout)
        if not ok_g or not rg["stdout"].strip():
            continue
        inp = rg["stdout"]
        ok_b, rb = _run_ok(brute, inp, timeout)
        if not ok_b:        # 暴力解自己崩了/超时，这组数据跳过
            continue
        expected = rb["stdout"]
        run = run_python(code, inp, timeout)
        st = run["status"]
        done += 1
        if st in (CE, TLE, RE):
            ce = {"input": _trunc(inp), "expected": _trunc(expected),
                  "actual": _trunc(run["stderr"] or "(无输出)"), "reason": st}
            return {"mode": "stress", "verdict": st, "passed": len(samples) + done - 1,
                    "total": len(samples) + done, "results": detail, "counterexample": ce,
                    "stress": {"brute_ok": brute_ok, "trials": done,
                               "note": "随机对拍第 %d 组触发 %s" % (done, st)}}
        if _normalize(run["stdout"]) != _normalize(expected):
            ce = {"input": _trunc(inp), "expected": _trunc(expected),
                  "actual": _trunc(run["stdout"]), "reason": WA}
            return {"mode": "stress", "verdict": WA, "passed": len(samples) + done - 1,
                    "total": len(samples) + done, "results": detail, "counterexample": ce,
                    "stress": {"brute_ok": brute_ok, "trials": done,
                               "note": "随机对拍第 %d 组发现反例" % done}}

    # 全部通过：注意这是经验性结论，不是数学证明
    note = "对拍 %d 组随机数据 + %d 个样例均未发现反例" % (done, len(samples))
    if not brute_ok:
        note += "（注：暴力解未通过样例校验，真值可信度有限）"
    return {"mode": "stress", "verdict": AC, "passed": len(samples) + done,
            "total": len(samples) + done, "results": detail, "counterexample": None,
            "stress": {"brute_ok": brute_ok, "trials": done, "note": note}}


# ===================== 统一入口 =====================
def judge_solution(problem, code, problem_id=None):
    """优先用官方真实数据判（真值），没有则自动对拍。"""
    tests = load_real_tests(problem_id)
    if tests:
        return judge_by_truth(code, tests)
    return judge_by_stress(problem, code)
