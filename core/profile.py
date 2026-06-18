# -*- coding: utf-8 -*-
"""用户画像：从答题历史刻画水平档位与强弱题型，并产出"因材施教"指令。

档位只用于调整教学策略与挑战强度，不改变对学生的尊重与鼓励。
"""
from sqlalchemy import select

from core.db import session_scope
from core.models import Submission

HARD = ("困难", "竞赛级")


def build_profile(user_id):
    if user_id is None:
        return _empty()
    with session_scope() as s:
        rows = list(s.scalars(select(Submission).where(Submission.user_id == user_id)))
    total = len(rows)
    if total == 0:
        return _empty()

    solved = sum(1 for r in rows if r.passed)
    rate = round(100 * solved / total)
    solved_hard = any(r.passed and (r.difficulty in HARD) for r in rows)

    # 题型通过率
    by_type = {}
    for r in rows:
        t = r.problem_type or "其他"
        by_type.setdefault(t, {"total": 0, "passed": 0})
        by_type[t]["total"] += 1
        by_type[t]["passed"] += 1 if r.passed else 0
    weak = [t for t, d in by_type.items() if d["total"] >= 2 and d["passed"] / d["total"] < 0.5]
    strong = [t for t, d in by_type.items() if d["total"] >= 2 and d["passed"] / d["total"] >= 0.8]

    # 常见错误（非 AC）
    err = {}
    for r in rows:
        k = r.error_kind or "AC"
        if k != "AC":
            err[k] = err.get(k, 0) + 1
    common_errors = [k for k, _ in sorted(err.items(), key=lambda x: -x[1])[:2]]

    # 档位
    if total < 5 or rate < 40:
        tier = "novice"
    elif solved >= 12 and rate >= 75 and solved_hard:
        tier = "expert"
    else:
        tier = "intermediate"

    label = {"novice": "新手", "intermediate": "进阶", "expert": "高手"}[tier]
    summary = "%s档 · 已攻克 %d/%d 题 · 通过率 %d%%" % (label, solved, total, rate)
    if weak:
        summary += " · 薄弱：" + "、".join(weak[:3])

    return {
        "tier": tier, "tier_label": label,
        "total": total, "solved": solved, "solve_rate": rate,
        "weak_types": weak, "strong_types": strong,
        "common_errors": common_errors, "summary": summary,
        "is_empty": False,
    }


def _empty():
    return {"tier": "novice", "tier_label": "新手", "total": 0, "solved": 0,
            "solve_rate": 0, "weak_types": [], "strong_types": [],
            "common_errors": [], "summary": "暂无答题数据，按通用策略辅导",
            "is_empty": True}


_DIRECTIVE = {
    "novice": "【该生水平：新手】多给鼓励与肯定；提示要更早、更具体、更口语化，"
              "先讲直觉再引术语；把大问题拆成小台阶，确保不卡死。",
    "intermediate": "【该生水平：进阶】提示精炼，多用反问引导其自己推进；"
                    "可适度提高挑战，点到为止，留出思考空间。",
    "expert": "【该生水平：高手】语言简洁直接；苏格拉底追问更犀利，"
              "可主动抛出更优复杂度或更难变式的追问，避免赘述基础概念。",
}


def build_directive(user_id):
    """供导师/对话 prompt 注入的因材施教指令；游客或无数据返回空串。"""
    p = build_profile(user_id)
    if p["is_empty"]:
        return ""
    d = _DIRECTIVE[p["tier"]]
    if p["weak_types"]:
        d += "该生在【%s】题型上偏弱，可多加引导、必要时多举一例。" % "、".join(p["weak_types"][:3])
    return d
