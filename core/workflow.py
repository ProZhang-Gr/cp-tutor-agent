# -*- coding: utf-8 -*-
"""LangGraph 工作流编排。

定义两条状态机工作流，体现"多步骤辅导流程"：

  分析流  retrieve → analyze → plan
      检索相似题 → 题目分析 → 策略规划

  评测流  review → [条件分支] → gen_tests → run_tests → summarize
      代码审查 →（语法过不了则直接收尾）→ 生成用例 → 沙箱判题 → 汇总

用 graph.stream(stream_mode="updates") 逐节点产出中间结果，
驱动前端"智能体协作流程"的实时可视化。
"""
from typing import Any, Dict, List, TypedDict

from langgraph.graph import END, START, StateGraph

from core import agents, sandbox
from core.rag import get_bank


# ===================== 分析流 =====================
class AnalysisState(TypedDict):
    problem: str
    deep: bool
    similar: List[Dict[str, Any]]
    analysis: Dict[str, Any]
    strategies: Dict[str, Any]


def _node_retrieve(state):
    return {"similar": get_bank().search(state["problem"], k=3)}


def _node_analyze(state):
    return {"analysis": agents.analyze(state["problem"], deep=state.get("deep", False))}


def _node_plan(state):
    return {"strategies": agents.plan(state["problem"], state["analysis"])}


def _route_after_analyze(state):
    # 不是有效算法题就别再做策略规划，直接收尾
    return "plan" if state.get("analysis", {}).get("is_problem", True) else END


def _build_analysis_graph():
    g = StateGraph(AnalysisState)
    g.add_node("retrieve", _node_retrieve)
    g.add_node("analyze", _node_analyze)
    g.add_node("plan", _node_plan)
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "analyze")
    g.add_conditional_edges("analyze", _route_after_analyze, {"plan": "plan", END: END})
    g.add_edge("plan", END)
    return g.compile()


# ===================== 评测流 =====================
class EvalState(TypedDict):
    problem: str
    code: str
    language: str
    problem_title: str
    problem_type: str
    difficulty: str
    review: Dict[str, Any]
    test_cases: List[Dict[str, Any]]
    judge: Dict[str, Any]
    summary: Dict[str, Any]


def _node_review(state):
    return {"review": agents.review(state["problem"], state["code"],
                                    state.get("language", "python"))}


def _node_gen_tests(state):
    return {"test_cases": agents.gen_tests(state["problem"])}


def _node_run_tests(state):
    cases = state.get("test_cases", [])
    if not cases:
        return {"judge": {"results": [], "passed": 0, "total": 0,
                          "all_passed": False, "verdict": "无用例"}}
    return {"judge": sandbox.judge(state["code"], cases)}


def _node_summarize(state):
    review = state.get("review", {})
    judge = state.get("judge", {"passed": 0, "total": 0, "all_passed": False})
    score = review.get("score", 0)
    total, passed = judge.get("total", 0), judge.get("passed", 0)

    if not review.get("syntax_ok", True):
        verdict, kind = "代码存在语法错误", "CE"
    elif total and passed == total:
        verdict, kind = "全部测试用例通过", "AC"
    elif total and passed > 0:
        verdict, kind = "部分用例通过，仍需修正", "WA"
    elif total:
        verdict, kind = "未通过测试", judge.get("verdict", "WA")
    else:
        verdict, kind = "已完成静态审查", "AC" if score >= 60 else "WA"

    # 综合分：静态审查分 60% + 测试通过率 40%
    test_ratio = (passed / total) if total else (score / 100.0)
    final = round(score * 0.6 + test_ratio * 100 * 0.4)

    return {"summary": {
        "verdict": verdict,
        "error_kind": kind,
        "final_score": final,
        "passed": passed,
        "total": total,
        "next_step": review.get("next_step", ""),
    }}


def _route_after_review(state):
    # 语法都通不过，没必要再跑测试，直接收尾
    if not state.get("review", {}).get("syntax_ok", True):
        return "summarize"
    return "gen_tests"


def _build_eval_graph():
    g = StateGraph(EvalState)
    g.add_node("review", _node_review)
    g.add_node("gen_tests", _node_gen_tests)
    g.add_node("run_tests", _node_run_tests)
    g.add_node("summarize", _node_summarize)
    g.add_edge(START, "review")
    g.add_conditional_edges("review", _route_after_review,
                            {"gen_tests": "gen_tests", "summarize": "summarize"})
    g.add_edge("gen_tests", "run_tests")
    g.add_edge("run_tests", "summarize")
    g.add_edge("summarize", END)
    return g.compile()


# 编译为单例
ANALYSIS_GRAPH = _build_analysis_graph()
EVAL_GRAPH = _build_eval_graph()


def run_analysis_stream(problem, deep=False):
    """逐节点产出 (node_name, delta)。"""
    for update in ANALYSIS_GRAPH.stream({"problem": problem, "deep": deep},
                                        stream_mode="updates"):
        for node, delta in update.items():
            yield node, delta


def run_eval_stream(problem, code, language="python", **meta):
    state = {"problem": problem, "code": code, "language": language}
    state.update(meta)
    for update in EVAL_GRAPH.stream(state, stream_mode="updates"):
        for node, delta in update.items():
            yield node, delta
