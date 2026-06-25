# -*- coding: utf-8 -*-
"""代码可信度验证：静态检查（编译/语法）+ 沙箱实跑（真值/样例比对）。

用途：防止"模型输出的错误代码被当成正确答案直接给用户"。任何一段代码
（尤其 AI 给出的修订代码）都先过这道关，回传一个明确的可信标识：

  verified  已验证通过  —— 编译通过 + 用真实测试数据/题面样例实跑且全对（可信度最高）
  ran       运行通过    —— 编译通过 + 能正常跑，但无真值可比对（仅证明不崩，未证明正确）
  failed    验证未通过  —— 编译通过但样例/真值跑出不一致，附最小反例
  error     无法运行    —— 编译/语法错误，根本跑不起来

刻意复用既有沙箱与双轨判题（judge），不另起炉灶。
"""
from config import settings
from core import judge, sandbox
from core.rag import get_bank
from core.sandbox import _normalize

# 真值验证最多跑多少组用例（够证明可信即可，免费机算力有限）
_MAX_TRUTH_CASES = 10

_LABEL = {
    "verified": "已验证通过",
    "ran": "运行通过（未充分验证）",
    "failed": "验证未通过",
    "error": "无法运行",
}


def _result(level, trust, checks, counterexample=None):
    return {
        "verified": level == "verified",
        "level": level,
        "label": _LABEL[level],
        "trust": trust,
        "checks": checks,
        "counterexample": counterexample,
    }


def _sample_of(problem_id):
    """题库题的题面样例（无官方测试数据时退而用它做真值）。"""
    if not problem_id:
        return None
    p = get_bank().get(problem_id)
    if not p:
        return None
    inp = p.get("sample_input")
    out = p.get("sample_output")
    if inp is None or out is None:
        return None
    return {"input": inp, "expected": out}


def verify_code(code, language="python", problem_id=None):
    """对一段代码做静态检查 + 沙箱实跑，返回可信度标识。"""
    if not (code or "").strip():
        return _result("error", 0, [{"name": "静态检查", "ok": False, "detail": "代码为空"}])

    # ---- 1) 静态检查：能否通过编译/语法 ----
    # Python 是解释型，sandbox.prepare 不做语法检查（错误在运行期才暴露），
    # 这里显式编译一次，把语法错误归为"无法运行"，与 C++ 的编译失败一视同仁。
    if language == "python":
        try:
            compile(code, "main.py", "exec")
        except SyntaxError as e:
            return _result("error", 0,
                           [{"name": "静态检查（语法）", "ok": False,
                             "detail": "语法错误: %s (第 %s 行)" % (e.msg, e.lineno)}])
    prog = sandbox.prepare(code, language)
    if not prog.ok():
        detail = ((prog.error or {}).get("stderr") or "编译/语法错误").strip()[:500]
        return _result("error", 0,
                       [{"name": "静态检查（编译/语法）", "ok": False, "detail": detail}])
    static_check = {"name": "静态检查（编译/语法）", "ok": True, "detail": "通过，无语法/编译错误"}

    try:
        # ---- 2) 真值验证：优先官方测试数据，其次题面样例 ----
        tests = judge.load_real_tests(problem_id)
        if tests:
            sub = tests[:_MAX_TRUTH_CASES]
            res = judge.judge_by_truth(code, sub, language=language)
            passed, total = res.get("passed", 0), res.get("total", 0)
            if res.get("verdict") == sandbox.AC and passed == total and total > 0:
                checks = [static_check,
                          {"name": "真值实跑（官方测试数据）", "ok": True,
                           "detail": "通过全部 %d 组官方用例" % total}]
                return _result("verified", 96, checks)
            checks = [static_check,
                      {"name": "真值实跑（官方测试数据）", "ok": False,
                       "detail": "%d/%d 组通过，裁决 %s" % (passed, total, res.get("verdict"))}]
            return _result("failed", 18, checks, res.get("counterexample"))

        sample = _sample_of(problem_id)
        if sample:
            run = prog.run(sample["input"], settings.SANDBOX_TIMEOUT)
            if run.get("status") != "OK":
                checks = [static_check,
                          {"name": "样例实跑", "ok": False,
                           "detail": "运行异常：%s" % (run.get("stderr") or run.get("status"))[:300]}]
                return _result("failed", 12, checks)
            got = _normalize(run.get("stdout", ""))
            exp = _normalize(sample["expected"])
            if got == exp:
                checks = [static_check,
                          {"name": "样例实跑（题面样例）", "ok": True, "detail": "样例输出一致"}]
                return _result("verified", 80, checks)
            checks = [static_check,
                      {"name": "样例实跑（题面样例）", "ok": False, "detail": "样例输出不一致"}]
            return _result("failed", 20, checks,
                           {"input": sample["input"], "expected": sample["expected"],
                            "actual": run.get("stdout", "")})

        # ---- 3) 无真值可比：只能证明"跑得起来不崩"，不能证明正确 ----
        # 喂空输入试跑。多数竞赛代码会读 stdin，空输入下的 EOFError / 等待超时
        # 都只是"缺数据"而非真崩溃，不应据此判错；只有真正的运行期异常才算崩。
        run = prog.run("", settings.SANDBOX_TIMEOUT)
        st = run.get("status", "")
        stderr = run.get("stderr", "") or ""
        needs_input = st == "TLE" or "EOF" in stderr or "EOFError" in stderr
        crashed = st not in ("OK", "TLE") and not needs_input
        if crashed:
            checks = [static_check,
                      {"name": "沙箱试运行", "ok": False,
                       "detail": "运行即抛异常：%s" % stderr[:300]}]
            return _result("failed", 15, checks)
        checks = [static_check,
                  {"name": "沙箱试运行", "ok": True,
                   "detail": "可正常启动运行；无样例数据，未做输出正确性验证"}]
        return _result("ran", 50, checks)
    finally:
        prog.close()
