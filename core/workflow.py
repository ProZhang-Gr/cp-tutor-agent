# -*- coding: utf-8 -*-
"""LangGraph 工作流编排。

定义两条状态机工作流，体现"多步骤辅导流程"：

  分析流  retrieve → analyze → plan
      检索相似题 → 题目分析 → 策略规划

  评测流  review → [条件分支] → judge → summarize
      代码审查 →（语法过不了则直接收尾）→ 双轨判题（真值/对拍）→ 汇总

用 graph.stream(stream_mode="updates") 逐节点产出中间结果，
驱动前端"智能体协作流程"的实时可视化。
"""
from typing import Any, Dict, List, TypedDict

from langgraph.graph import END, START, StateGraph

from core import agents, judge
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
    problem_id: str
    problem_title: str
    problem_type: str
    difficulty: str
    review: Dict[str, Any]
    judge: Dict[str, Any]
    summary: Dict[str, Any]


def _node_review(state):
    return {"review": agents.review(state["problem"], state["code"],
                                    state.get("language", "python"))}


def _node_judge(state):
    """双轨判题：有官方数据走真值，否则自动对拍。"""
    return {"judge": judge.judge_solution(
        state["problem"], state["code"], state.get("problem_id"))}


# 判题裁决 → 中文结论
_VERDICT_TXT = {
    "AC": "通过", "WA": "答案错误", "TLE": "超时",
    "RE": "运行错误", "CE": "语法/编译错误",
}


def _node_summarize(state):
    review = state.get("review", {})
    jd = state.get("judge", {}) or {}
    score = review.get("score", 0)
    mode = jd.get("mode")
    jv = jd.get("verdict")
    total, passed = jd.get("total", 0), jd.get("passed", 0)
    mode_txt = "真值判定" if mode == "truth" else ("对拍" if mode == "stress" else "")

    if not review.get("syntax_ok", True) or jv == "CE":
        verdict, kind = "代码存在语法错误", "CE"
    elif jv == "AC" and total > 0:
        verdict = ("全部真实测试通过" if mode == "truth"
                   else "对拍未发现反例（经验性通过）")
        kind = "AC"
    elif jv in ("WA", "TLE", "RE"):
        verdict = "%s · %s" % (_VERDICT_TXT.get(jv, jv), mode_txt)
        kind = jv
    elif jv == "NO_KIT":
        verdict, kind = "无官方数据且无法自动对拍，已按静态审查评分", ("AC" if score >= 60 else "WA")
    else:
        verdict, kind = "已完成静态审查", "AC" if score >= 60 else "WA"

    # 综合分：判题裁决是铁证，主导评分；审查分仅作小幅风格加成。
    review_bonus = min(max(score, 0), 100) * 0.05  # 0~5 分风格加成
    if kind == "CE":
        final = min(score, 20)
    elif jv == "AC" and total > 0:
        base = 95 if mode == "truth" else 85   # 对拍是经验性结论，略保守
        final = round(min(100, base + review_bonus))
    elif jv in ("WA", "TLE", "RE") and total > 0:
        # 过了多少给多少（最高 55），再加风格分
        final = round(min(60, (passed / total) * 55 + review_bonus))
    else:
        final = score  # 仅静态审查

    return {"summary": {
        "verdict": verdict,
        "error_kind": kind,
        "final_score": final,
        "passed": passed,
        "total": total,
        "judge_mode": mode,
        "counterexample": jd.get("counterexample"),
        "next_step": review.get("next_step", ""),
    }}


def _route_after_review(state):
    # 语法都通不过，没必要再判题，直接收尾
    if not state.get("review", {}).get("syntax_ok", True):
        return "summarize"
    return "judge"


def _build_eval_graph():
    g = StateGraph(EvalState)
    g.add_node("review", _node_review)
    g.add_node("judge", _node_judge)
    g.add_node("summarize", _node_summarize)
    g.add_edge(START, "review")
    g.add_conditional_edges("review", _route_after_review,
                            {"judge": "judge", "summarize": "summarize"})
    g.add_edge("judge", "summarize")
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
