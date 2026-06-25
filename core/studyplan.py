# -*- coding: utf-8 -*-
"""个性化训练计划：据用户画像（薄弱题型 / 档位 / 高频失误）从题库挑题，
生成"今日该刷什么"的训练清单。

设计取舍：核心计划用确定性规则产出（稳、可解释、零 LLM 成本），
仅末尾一句鼓励性导语走 best-effort LLM（失败回退模板），与 report.py 一致。
"""
from core import profile as profile_mod
from core import progress
from core.llm import get_llm
from core.rag import get_bank

# 难度梯度（由易到难），用于按档位匹配合适难度
DIFF_ORDER = ["入门", "简单", "中等", "困难", "竞赛级"]
_DIFF_RANK = {d: i for i, d in enumerate(DIFF_ORDER)}

# 各档位的目标难度区间（取交集内的题优先推荐）
_TIER_DIFFS = {
    "novice": ("入门", "简单"),
    "intermediate": ("简单", "中等"),
    "expert": ("中等", "竞赛级"),
}

# 无答题数据时的新手起步题型梯度（覆盖面广、上手友好）
_DEFAULT_FOCUS = ["枚举", "模拟", "排序", "贪心"]

# 每个计划最多推荐的题目数
PLAN_SIZE = 5


def _diff_in_range(diff, lo, hi):
    r = _DIFF_RANK.get(diff)
    return r is not None and _DIFF_RANK[lo] <= r <= _DIFF_RANK[hi]


def _pick_focus_types(prof, bank, solved):
    """决定今日主攻题型：优先薄弱题型；无则取"练得最少"的题型补全面。"""
    focus = list(prof.get("weak_types") or [])
    if focus:
        return focus[:3]
    # 无明显薄弱项：挑用户做得最少的题型，鼓励拓宽覆盖面
    by_type = {}
    for p in bank.list_all():
        by_type.setdefault(p.get("type") or "其他", 0)
    solved_by_type = {}
    for p in bank.list_all():
        if p["id"] in solved:
            t = p.get("type") or "其他"
            solved_by_type[t] = solved_by_type.get(t, 0) + 1
    # 该题型已攻克数升序：先补最薄弱覆盖面
    ranked = sorted(by_type.keys(), key=lambda t: solved_by_type.get(t, 0))
    picked = [t for t in ranked if solved_by_type.get(t, 0) == 0][:2]
    if not picked:
        picked = ranked[:2]
    # 新手且毫无数据时给一条友好的起步梯度
    if prof.get("is_empty"):
        picked = [t for t in _DEFAULT_FOCUS if t in by_type][:3] or picked
    return picked or ["枚举"]


def _candidates(bank, ptype, solved, lo, hi):
    """某题型下、未做过、且难度落在 [lo, hi] 的候选题，难度升序。"""
    out = []
    for p in bank.list_all():
        if (p.get("type") or "其他") != ptype:
            continue
        if p["id"] in solved:
            continue
        if _diff_in_range(p.get("difficulty"), lo, hi):
            out.append(p)
    out.sort(key=lambda p: (_DIFF_RANK.get(p.get("difficulty"), 99), p.get("difficulty_score", 5)))
    return out


def _fallback_any(bank, ptype, solved):
    """难度区间内没货时，退而取该题型任意未做题（难度升序）。"""
    out = [p for p in bank.list_all()
           if (p.get("type") or "其他") == ptype and p["id"] not in solved]
    out.sort(key=lambda p: (_DIFF_RANK.get(p.get("difficulty"), 99), p.get("difficulty_score", 5)))
    return out


def build_plan(user_id):
    """产出个性化训练计划。游客/无数据也能给一份通用起步计划。"""
    prof = profile_mod.build_profile(user_id)
    bank = get_bank()
    solved = set(progress.solved_problem_ids(user_id))

    tier = prof.get("tier", "novice")
    lo, hi = _TIER_DIFFS.get(tier, ("入门", "简单"))
    focus_types = _pick_focus_types(prof, bank, solved)

    weak = set(prof.get("weak_types") or [])
    items = []
    seen = set()
    # 轮转各主攻题型，每型先取 1 题，再回头补满 PLAN_SIZE，保证覆盖面
    buckets = []
    for t in focus_types:
        cand = _candidates(bank, t, solved, lo, hi) or _fallback_any(bank, t, solved)
        buckets.append((t, cand))
    round_i = 0
    while len(items) < PLAN_SIZE and any(len(c) > round_i for _, c in buckets):
        for t, cand in buckets:
            if len(items) >= PLAN_SIZE:
                break
            if len(cand) <= round_i:
                continue
            p = cand[round_i]
            if p["id"] in seen:
                continue
            seen.add(p["id"])
            reason = ("巩固薄弱题型【%s】" % t) if t in weak else ("拓宽题型覆盖：%s" % t)
            items.append({
                "id": p["id"], "title": p["title"], "type": t,
                "difficulty": p.get("difficulty", ""),
                "difficulty_score": p.get("difficulty_score", 0),
                "reason": reason,
            })
        round_i += 1

    # 复习提示：把高频失误转成一句针对性提醒
    review_tip = _review_tip(prof.get("common_errors") or [])

    focus_label = "、".join(focus_types[:3])
    if prof.get("is_empty"):
        headline = "先从【%s】这几类基础题型起步，建立手感" % focus_label
    elif weak:
        headline = "今日优先攻克薄弱题型：%s" % focus_label
    else:
        headline = "保持节奏，今日拓宽题型覆盖：%s" % focus_label

    plan = {
        "tier": tier, "tier_label": prof.get("tier_label", "新手"),
        "focus_types": focus_types,
        "target_difficulty": "%s ~ %s" % (lo, hi),
        "headline": headline,
        "items": items,
        "review_tip": review_tip,
        "profile_summary": prof.get("summary", ""),
        "narrative": _narrative(prof, focus_types, items, review_tip),
    }
    return plan


_ERROR_HINT = {
    "WA": "重点核对边界与特殊用例（空输入 / 最小最大值 / 相等元素）",
    "TLE": "留意时间复杂度，警惕不必要的嵌套循环，考虑更优数据结构",
    "RE": "排查数组越界、除零、空指针与递归深度",
    "CE": "提交前先在本地编译/运行一遍，别让低级语法错误吃掉提交机会",
    "MLE": "注意空间复杂度，避免开过大数组或冗余拷贝",
}


def _review_tip(common_errors):
    tips = [_ERROR_HINT[e] for e in common_errors if e in _ERROR_HINT]
    if not tips:
        return ""
    kinds = "、".join(e for e in common_errors if e in _ERROR_HINT)
    return "你近期高频失误为 %s：%s。" % (kinds, "；".join(tips[:2]))


_SYS = ("你是一名算法竞赛私教。根据学生画像与今天为他挑好的训练题，写一句简短的训练寄语"
        "（40-70字，中文）：点明今日训练目标与抓手，语气专业、笃定、给力，但不空喊口号。"
        "直接输出寄语正文，不要标题、不要列题号。")


def _narrative(prof, focus_types, items, review_tip):
    human = ("学生画像：%s。今日主攻题型：%s。已为其挑选 %d 道训练题（难度递进）。%s"
             % (prof.get("summary", ""), "、".join(focus_types), len(items), review_tip))
    try:
        return get_llm(temperature=0.6, max_tokens=200).invoke(
            [("system", _SYS), ("human", human)]).content.strip()
    except Exception:
        return "今天就从主攻题型稳扎稳打，按由易到难的顺序逐题攻克，量不在多而在吃透每一道。"
