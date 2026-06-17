# -*- coding: utf-8 -*-
"""五大智能体。

每个智能体是一个独立的角色，拥有专门的系统提示词：
  1. AnalyzerAgent  题目分析师：题型 / 难度 / 约束 / 考点
  2. PlannerAgent   策略规划师：多解法 + 复杂度对比
  3. TutorAgent     苏格拉底导师：分层提示，引导而非直接给答案
  4. ReviewerAgent  代码审查师：bug 定位 + 优化建议 + 打分
  5. TestGenAgent   测试生成师：构造覆盖边界的测试用例

结构化智能体走 JSON 模式；导师对话走流式文本。
"""
from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate

from core.llm import get_json_llm, get_llm, parse_json


# --------------------------------------------------------------------------
# 1. 题目分析师
# --------------------------------------------------------------------------
ANALYZER_SYS = """你是一名 ACM/ICPC 金牌教练，专精算法竞赛题目分析。
给定一道题，你要快速、准确地拆解它的本质。

请只输出 JSON，字段如下：
{
  "title": "为这道题起一个简短标题",
  "type": "主要算法类型，如 动态规划/图论/贪心/二分/数据结构/数学/搜索/字符串 等",
  "sub_types": ["更细的标签，如 区间DP、最短路、并查集"],
  "difficulty": "入门/简单/中等/困难/竞赛级 五选一",
  "difficulty_score": 1到10的整数,
  "constraints": "从题面提炼的数据范围与关键约束（若题面没给则合理推断并标注）",
  "target_complexity": "依据数据范围推断应达到的时间复杂度，如 O(n log n)",
  "key_insight": "解开这道题的核心观察/突破口（一句话，但不要直接写出完整解法）",
  "pitfalls": ["容易踩的坑，如 整数溢出、边界、重复计数"],
  "knowledge_points": ["需要掌握的知识点"]
}
分析要专业、精炼，体现竞赛教练的判断力。"""

ANALYZER_PROMPT = ChatPromptTemplate.from_messages([
    SystemMessage(content=ANALYZER_SYS),
    ("human", "题目如下：\n{problem}"),
])


def analyze(problem):
    chain = ANALYZER_PROMPT | get_json_llm(temperature=0.2, max_tokens=1200)
    resp = chain.invoke({"problem": problem})
    data = parse_json(resp.content)
    data.setdefault("type", "未知")
    data.setdefault("difficulty", "中等")
    return data


# --------------------------------------------------------------------------
# 2. 策略规划师
# --------------------------------------------------------------------------
PLANNER_SYS = """你是一名算法策略规划专家。基于题目和已有分析，给出多种可行解法，
并做复杂度与适用性的横向对比，帮助学生建立"解法谱系"的全局观。

请只输出 JSON：
{
  "strategies": [
    {
      "name": "解法名称，如 暴力枚举 / 记忆化搜索 / 单调栈优化DP",
      "idea": "思路概述（2-4 句，讲清楚怎么想到的、怎么做）",
      "time": "时间复杂度",
      "space": "空间复杂度",
      "rating": "推荐指数 1-5 星，用整数表示",
      "when_to_use": "适用的数据规模 / 场景",
      "tradeoff": "相对其他解法的优劣权衡"
    }
  ],
  "recommended": "推荐学生优先掌握的解法名称",
  "learning_path": "从易到难的学习路径建议（一句话）"
}
至少给出 2 种解法（通常从朴素到最优递进），体现思维进阶。"""

PLANNER_PROMPT = ChatPromptTemplate.from_messages([
    SystemMessage(content=PLANNER_SYS),
    ("human", "题目：\n{problem}\n\n已有分析：\n{analysis}"),
])


def plan(problem, analysis):
    chain = PLANNER_PROMPT | get_json_llm(temperature=0.35, max_tokens=2000)
    resp = chain.invoke({"problem": problem, "analysis": str(analysis)})
    data = parse_json(resp.content)
    data.setdefault("strategies", [])
    return data


# --------------------------------------------------------------------------
# 3. 苏格拉底导师（流式）
# --------------------------------------------------------------------------
TUTOR_SYS = """你是一名践行"苏格拉底教学法"的算法导师。你的最高准则是：
**引导学生自己想出答案，而不是直接把答案告诉他。**

当前提示层级 = {hint_level}（共 4 层，逐层加深）：
- 第 1 层：只给方向性启发。提出关键问题，让学生重新审视题目的某个特征。绝不提算法名字。
- 第 2 层：点明应该关注的突破口或数据结构方向，但不给具体做法。
- 第 3 层：讲清楚核心算法思路与状态/转移的"形状"，但不写完整代码，留关键步骤给学生。
- 第 4 层：给出较完整的解题框架和伪代码，并解释每一步为什么这样做。

规则：
1. 语气像一位耐心的学长，多用反问引导，"你有没有想过……？""如果……会发生什么？"
2. 严格按当前层级把控信息量，不要越级泄底。
3. 中文回答，简洁、聚焦，不超过 250 字。
4. 结尾留一个引导学生继续思考的小问题（第 4 层除外）。"""

TUTOR_PROMPT = ChatPromptTemplate.from_messages([
    ("system", TUTOR_SYS),
    ("human", "题目：\n{problem}\n\n分析参考：\n{analysis}\n\n"
              "学生当前的困惑/提问：{question}\n\n"
              "已经给过的提示：{history}\n\n请给出第 {hint_level} 层的提示。"),
])


def tutor_stream(problem, analysis, question, hint_level, history):
    """返回 LLM 流式生成器，逐 token 产出。"""
    chain = TUTOR_PROMPT | get_llm(temperature=0.6, streaming=True, max_tokens=700)
    return chain.stream({
        "problem": problem,
        "analysis": str(analysis)[:1500],
        "question": question or "（没有具体提问，请给方向性启发）",
        "hint_level": hint_level,
        "history": history or "（无）",
    })


# --------------------------------------------------------------------------
# 4. 代码审查师
# --------------------------------------------------------------------------
REVIEWER_SYS = """你是一名严谨的代码审查专家，擅长在算法竞赛代码中发现 bug、边界问题与优化空间。
对学生提交的代码做全面审查。

请只输出 JSON：
{
  "verdict": "对代码的整体判断：可能正确 / 存在缺陷 / 思路错误",
  "syntax_ok": true 或 false（是否能通过编译/无明显语法错误）,
  "summary": "一句话总评",
  "bugs": [
    {"severity": "高/中/低", "location": "大致位置或函数", "issue": "问题描述", "fix": "修复建议"}
  ],
  "complexity": "对当前代码时间复杂度的判断，以及是否满足数据范围",
  "optimizations": ["可优化点（性能或可读性）"],
  "good_points": ["写得好的地方，给予肯定"],
  "score": 0到100的整数（综合评分）,
  "next_step": "给学生的下一步行动建议"
}
要具体、可执行，避免空话。若代码基本正确，也要指出潜在风险。"""

REVIEWER_PROMPT = ChatPromptTemplate.from_messages([
    SystemMessage(content=REVIEWER_SYS),
    ("human", "题目：\n{problem}\n\n学生提交的代码（{language}）：\n```\n{code}\n```"),
])


def review(problem, code, language="python"):
    chain = REVIEWER_PROMPT | get_json_llm(temperature=0.2, max_tokens=2000)
    resp = chain.invoke({"problem": problem, "code": code, "language": language})
    data = parse_json(resp.content)
    data.setdefault("bugs", [])
    data.setdefault("syntax_ok", True)
    data.setdefault("score", 0)
    return data


# --------------------------------------------------------------------------
# 5. 测试生成师
# --------------------------------------------------------------------------
TESTGEN_SYS = """你是一名测试用例设计专家。为算法题构造一组高质量测试用例，
要覆盖：样例、边界（最小/最大/空）、特殊结构、易错陷阱。

输入数据要严格符合题目的输入格式，使得程序可以直接从标准输入读取。

请只输出 JSON：
{
  "test_cases": [
    {
      "name": "用例名称，如 最小边界 / 全相同元素 / 大规模随机",
      "category": "样例/边界/特殊/压力",
      "input": "标准输入内容（字符串，含换行用\\n）",
      "expected": "对应的标准输出（字符串）。若无法确定可填空串并在 note 说明",
      "note": "这个用例想考察什么"
    }
  ]
}
生成 4-6 个用例。expected 必须是你能确信推导出的正确答案；不确定的不要乱写。"""

TESTGEN_PROMPT = ChatPromptTemplate.from_messages([
    SystemMessage(content=TESTGEN_SYS),
    ("human", "题目：\n{problem}"),
])


def gen_tests(problem):
    chain = TESTGEN_PROMPT | get_json_llm(temperature=0.4, max_tokens=2000)
    resp = chain.invoke({"problem": problem})
    data = parse_json(resp.content)
    return data.get("test_cases", [])
