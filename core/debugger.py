# -*- coding: utf-8 -*-
"""Agentic 调试回路（ReAct）。

这不是"让模型看一眼代码说说哪里错"，而是一个会动手实验的 agent：
给定一个失败反例，它在「思考 → 调用沙箱跑探针 → 观察结果 → 修正假设」的循环里
真实地多轮调用工具，逐步把 bug 缩小到根因，最后给出定位与修复方向。

唯一工具：run(code, stdin) —— 在隔离子进程里运行一段 Python，返回 stdout/stderr/状态。
每一步以流式事件吐给前端，让人看见它确实在多轮调用工具。
"""
import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from config import settings
from core import sandbox
from core.llm import get_json_llm, parse_json


def _trunc(s, n=800):
    s = s or ""
    return s if len(s) <= n else s[:n] + "\n…（截断）"


def _fmt_thought(t):
    """把思考统一成带换行的 markdown，避免一大坨文字墙。

    - 数组：逐条转项目符号；
    - 单段长文兜底：按句末标点切成多行，至少保证有换行。
    """
    if isinstance(t, list):
        items = [str(x).strip() for x in t if str(x).strip()]
    else:
        s = str(t or "").strip()
        if not s:
            return ""
        parts = re.split(r"(?<=[。；！？!?;])\s*", s)
        items = [p.strip() for p in parts if p.strip()]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return "\n".join("- " + x for x in items)


DEBUG_SYS = """你是一个会动手做实验的调试 agent。你有且仅有一个工具：
  run(code, stdin) —— 在沙箱里运行一段完整的 __LANG__ 代码并喂入标准输入，返回它的 stdout / stderr / 运行状态。

目标：针对用户在某道算法题上失败的解法，通过【真实运行实验】把 bug 定位到根因，而不是空想。

每一步只输出一个 JSON（不要任何多余文字）：
{
  "thought": ["要点1", "要点2"],
  "action": "run" 或 "finish",
  "code": "当 action=run：要运行的完整 __LANG__ 代码（可给用户代码插桩打印、也可自己写最小复现/探针）",
  "stdin": "当 action=run：喂给程序的标准输入",
  "conclusion": {
     "root_cause": "当 action=finish：bug 根因，一句话点透",
     "evidence": "你由哪次实验观察到的证据支撑这个结论",
     "fix_hint": "修复方向（给思路与关键改动，可给片段，但不要直接甩出整题 AC 代码）"
  }
}

规则：
- thought 必须是【数组】，1~3 条极简要点，每条不超过 30 字，只说此刻怀疑什么、打算验证什么；可用 `代码`。
  严禁逐句复述题意/反例，严禁把推导过程写成长段落或一大坨。
- 先用给定反例确认问题，再围绕单个假设设计 run 实验逐步缩小范围。
- 每次 run 的代码要短小、聚焦一个假设；善用插桩打印中间变量。
- 至少做一次 run 实验再 finish。到达步数上限时必须 finish。"""


_LANG_NAME = {"python": "Python3", "cpp": "C++"}
_LANG_FENCE = {"python": "python", "cpp": "cpp"}


def _initial_human(problem, code, counterexample, language="python"):
    ce = counterexample or {}
    lang_name = _LANG_NAME.get(language, "Python3")
    fence = _LANG_FENCE.get(language, "python")
    return HumanMessage(content=(
        "题目：\n%s\n\n用户的解法（%s）：\n```%s\n%s\n```\n\n"
        "这是一个让它失败的反例：\n输入：\n%s\n期望输出：\n%s\n实际输出/报错：\n%s\n失败类型：%s\n\n"
        "请开始调试。先给出第一步 JSON。" % (
            _trunc(problem, 2000), lang_name, fence, _trunc(code, 4000),
            _trunc(ce.get("input", ""), 600), _trunc(ce.get("expected", ""), 600),
            _trunc(ce.get("actual", ""), 600), ce.get("reason", ""))))


def run_debug_stream(problem, code, counterexample, language="python"):
    """逐步产出调试过程事件：(kind, payload)。

    kind ∈ {thought, action, observation, conclusion, error}
    实验代码在用户提交的语言（python/cpp）里真实编译运行。
    """
    llm = get_json_llm(temperature=0.2, max_tokens=1500)
    sys_prompt = DEBUG_SYS.replace("__LANG__", _LANG_NAME.get(language, "Python3"))
    messages = [SystemMessage(content=sys_prompt),
                _initial_human(problem, code, counterexample, language)]
    max_steps = settings.DEBUG_MAX_STEPS

    for step in range(1, max_steps + 1):
        last = step == max_steps
        try:
            resp = llm.invoke(messages)
        except Exception as e:
            yield "error", {"message": str(e)}
            return
        data = parse_json(resp.content)
        thought = data.get("thought", "")
        action = data.get("action", "")
        yield "thought", {"step": step, "text": _fmt_thought(thought)}

        if action == "run" and not last:
            run_code = data.get("code", "") or ""
            stdin = data.get("stdin", "") or ""
            yield "action", {"step": step, "code": run_code, "stdin": stdin}
            r = sandbox.run_code(run_code, language, stdin, timeout=settings.STRESS_TIMEOUT)
            obs = {"step": step, "status": r["status"],
                   "stdout": _trunc(r["stdout"]), "stderr": _trunc(r["stderr"])}
            yield "observation", obs
            messages.append(AIMessage(content=resp.content))
            messages.append(HumanMessage(content=(
                "运行结果：状态=%s\nstdout:\n%s\nstderr:\n%s\n请继续下一步 JSON。" % (
                    obs["status"], obs["stdout"], obs["stderr"]))))
            continue

        # finish（或已到步数上限）
        conclusion = data.get("conclusion") or {}
        if not conclusion and last:
            # 到上限还没给结论：再逼一次最终结论
            messages.append(AIMessage(content=resp.content))
            messages.append(HumanMessage(content="已到步数上限，请直接输出 action=finish 的最终 conclusion JSON。"))
            try:
                resp = llm.invoke(messages)
                conclusion = parse_json(resp.content).get("conclusion") or {}
            except Exception:
                pass
        yield "conclusion", {
            "root_cause": conclusion.get("root_cause", "未能给出明确根因"),
            "evidence": conclusion.get("evidence", ""),
            "fix_hint": conclusion.get("fix_hint", ""),
        }
        return
