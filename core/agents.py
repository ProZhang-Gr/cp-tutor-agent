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

【第一步：先判断输入是不是一道有效的算法/编程题】
有效题目通常含明确的问题描述，常带输入输出要求、数据范围或样例。
若输入并非算法题——例如闲聊、只是问某个名词概念、无意义或残缺到无法理解的文本——
请将 is_problem 置为 false，并在 message 里用一句友好的话引导用户
（例如：「这看起来不像一道完整的算法题，请粘贴含输入输出/样例的题面，或到右侧『导师对话』直接提问～」）。
此时其余分析字段可填占位值，不必硬凑。
只有当 is_problem 为 true 时，才认真完成下面的分析。

请只输出 JSON，字段如下：
{
  "is_problem": true 或 false,
  "message": "当 is_problem 为 false 时给用户的一句友好提示；为 true 时填空字符串",
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
    ("human", "题目如下：\n{problem}{extra}"),
])

_DEEP_INSTR = ("\n\n【Pro 深度模式】请在 JSON 中额外输出字段 "
               "\"deep_dive\"：一段 300-500 字的「解题推演」——像专家一样一步步推理"
               "如何从题意出发，逐步逼近最优解（含关键观察、为何朴素做法不行、"
               "如何优化到目标复杂度），用于帮学生看到完整思考链路。")


def analyze(problem, deep=False):
    extra = _DEEP_INSTR if deep else ""
    chain = ANALYZER_PROMPT | get_json_llm(temperature=0.2, max_tokens=2400 if deep else 1200)
    resp = chain.invoke({"problem": problem, "extra": extra})
    data = parse_json(resp.content)
    data.setdefault("is_problem", True)
    data.setdefault("message", "")
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
    ("system", "因材施教提示（据此调整教学策略与挑战强度，但对学生始终保持尊重与鼓励）：{directive}"),
    ("human", "题目：\n{problem}\n\n分析参考：\n{analysis}\n\n"
              "学生当前的困惑/提问：{question}\n\n"
              "已经给过的提示：{history}\n\n请给出第 {hint_level} 层的提示。"),
])


def tutor_stream(problem, analysis, question, hint_level, history, directive=""):
    """返回 LLM 流式生成器，逐 token 产出。directive 为因材施教指令。"""
    chain = TUTOR_PROMPT | get_llm(temperature=0.6, streaming=True, max_tokens=700)
    return chain.stream({
        "problem": problem,
        "analysis": str(analysis)[:1500],
        "question": question or "（没有具体提问，请给方向性启发）",
        "hint_level": hint_level,
        "history": history or "（无）",
        "directive": directive or "（无特定画像，按通用策略）",
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
# 5b. 审阅导师（主动反馈：行内批注 + 可选整段修订）
# --------------------------------------------------------------------------
REVIEW_EDIT_SYS = """你是一名手把手带学生的算法竞赛导师。学生把题目和他写到一半/可能有问题的代码交给你，
你要像老师在纸上批改一样：先逐行看，在出问题或思路不对的【具体行】上画批注，再判断要不要给一份修订版代码。

代码的行号从 1 开始，与学生看到的完全一致。请严格按行号定位。

请只输出 JSON：
{
  "summary": "两三句话的总体点评：思路对不对、主要问题在哪",
  "annotations": [
    {
      "line": 该问题所在的行号(整数, 从1开始),
      "severity": "high" | "med" | "low",   // high=会导致错误答案/崩溃, med=隐患/边界, low=风格/可读性
      "note": "这一行/这块的问题或思路提示，一句话点透，像老师批注（可给方向，别直接写出整段答案）"
    }
  ],
  "has_fix": true 或 false,                 // 是否给出修订版代码
  "proposed_code": "当 has_fix=true：完整可运行的修订版代码（保留学生原有风格，只改该改的）；否则空串",
  "fix_explanation": "当 has_fix=true：用一两句说明你改了什么、为什么"
}

要求：
- annotations 控制在 1~6 条，挑最关键的行，别每行都标。
- 如果代码基本是对的，annotations 可以只放优化/风险点，has_fix 可为 false。
- 如果学生只写了骨架/空函数，proposed_code 可给一个合理的解题框架（带 TODO 注释引导），但不要直接奉送整题最优解的全部细节——保留让他思考的空间。
- proposed_code 必须是完整的、能独立运行的代码（不是片段），语言与学生一致。"""

REVIEW_EDIT_PROMPT = ChatPromptTemplate.from_messages([
    SystemMessage(content=REVIEW_EDIT_SYS),
    ("human", "题目：\n{problem}\n\n学生的代码（{language}，已标注行号供你定位）：\n{numbered_code}"),
])


def _number_lines(code):
    """给代码逐行编号，帮助模型把批注精准对到行。"""
    lines = (code or "").split("\n")
    return "\n".join("%4d | %s" % (i + 1, ln) for i, ln in enumerate(lines))


def review_for_edit(problem, code, language="python"):
    """审阅导师：返回行内批注列表 + 可选的整段修订代码。"""
    chain = REVIEW_EDIT_PROMPT | get_json_llm(temperature=0.2, max_tokens=2600)
    resp = chain.invoke({
        "problem": problem or "（学生未提供题面，请仅就代码本身的正确性/风格审阅）",
        "language": language,
        "numbered_code": _number_lines(code),
    })
    data = parse_json(resp.content)
    # 规整：行号转 int、过滤越界、限制条数
    total = len((code or "").split("\n"))
    cleaned = []
    for a in (data.get("annotations") or []):
        try:
            ln = int(a.get("line", 0))
        except (TypeError, ValueError):
            continue
        if ln < 1 or ln > total:
            continue
        sev = a.get("severity", "med")
        if sev not in ("high", "med", "low"):
            sev = "med"
        note = (a.get("note") or "").strip()
        if note:
            cleaned.append({"line": ln, "severity": sev, "note": note})
    return {
        "summary": (data.get("summary") or "").strip(),
        "annotations": cleaned[:6],
        "has_fix": bool(data.get("has_fix")) and bool((data.get("proposed_code") or "").strip()),
        "proposed_code": (data.get("proposed_code") or "").strip(),
        "fix_explanation": (data.get("fix_explanation") or "").strip(),
    }


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


# --------------------------------------------------------------------------
# 6. 对拍套件生成师（差分测试 / stress test）
#    无官方测试数据时，由它产出「暴力正确解 + 随机数据生成器」，
#    用暴力解当真值，与用户解逐组比对，抓最小反例。
# --------------------------------------------------------------------------
STRESSKIT_SYS = """你是竞赛对拍（stress test）专家。给定一道算法题，请产出一套可自动对拍的工具，
让我们用「朴素暴力解」当真值来校验别人的解法。

严格输出 JSON：
{
  "brute_code": "完整可独立运行的 Python3。从标准输入读题目输入，用最朴素、最显然正确的方法求解（正确性第一，效率无所谓，可指数级），把答案 print 到标准输出。格式必须和题目要求完全一致。",
  "gen_code": "完整可独立运行的 Python3 随机数据生成器。从标准输入读入一个整数作为随机种子，random.seed(种子)，随机造一组【小规模】且严格符合输入格式与约束的合法输入，只把这组输入 print 出来（不要输出答案）。规模一定要小（如 n≤8、数值≤20），这样暴力解快、反例也最小。",
  "samples": [{"input": "题面给出的样例输入（原样）", "output": "对应样例输出"}]
}

要求：
- brute_code 与 gen_code 都必须是无需任何外部库（标准库除外）即可直接 `python x.py` 运行的完整脚本。
- gen_code 生成的输入必须能被 brute_code 正确读取。
- samples 从题面的 Examples / 样例中原样抽取，抽不到就给空数组。
- 不要有任何多余解释，只输出 JSON。"""

STRESSKIT_PROMPT = ChatPromptTemplate.from_messages([
    SystemMessage(content=STRESSKIT_SYS),
    ("human", "题目：\n{problem}"),
])


def gen_stress_kit(problem):
    chain = STRESSKIT_PROMPT | get_json_llm(temperature=0.2, max_tokens=2200)
    resp = chain.invoke({"problem": problem})
    data = parse_json(resp.content)
    return {
        "brute_code": data.get("brute_code", "") or "",
        "gen_code": data.get("gen_code", "") or "",
        "samples": data.get("samples", []) or [],
    }
