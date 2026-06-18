# -*- coding: utf-8 -*-
"""学习进度跟踪：按用户作用域记录提交并产出仪表盘统计。

登录用户看自己的数据；游客（user_id 为空）共用一个游客桶。
底层走 core.db，自动适配 SQLite / Postgres。
"""
import time

from core import db


def init_db():
    db.init_schema()


def record(problem_title, problem_type, difficulty, passed,
           tests_passed, tests_total, score, error_kind, user_id=None):
    db.execute(
        "INSERT INTO submissions (user_id, ts, problem_title, problem_type, difficulty, "
        "passed, tests_passed, tests_total, score, error_kind) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (user_id, time.time(), problem_title, problem_type, difficulty,
         1 if passed else 0, tests_passed, tests_total, score, error_kind),
    )


def _rows_for(user_id):
    if user_id is None:
        return db.query("SELECT * FROM submissions WHERE user_id IS NULL ORDER BY ts DESC")
    return db.query("SELECT * FROM submissions WHERE user_id = ? ORDER BY ts DESC", (user_id,))


def stats(user_id=None):
    rows = _rows_for(user_id)
    total = len(rows)
    solved = sum(1 for r in rows if r["passed"])
    avg_score = round(sum(r["score"] for r in rows) / total, 1) if total else 0

    by_type = {}
    for r in rows:
        t = r["problem_type"] or "其他"
        by_type.setdefault(t, {"total": 0, "passed": 0})
        by_type[t]["total"] += 1
        by_type[t]["passed"] += 1 if r["passed"] else 0
    type_mastery = [
        {"type": t, "rate": round(100 * d["passed"] / d["total"]), "count": d["total"]}
        for t, d in sorted(by_type.items(), key=lambda x: -x[1]["total"])
    ]

    by_diff = {}
    for r in rows:
        d = r["difficulty"] or "未知"
        by_diff[d] = by_diff.get(d, 0) + 1

    err = {}
    for r in rows:
        k = r["error_kind"] or "AC"
        err[k] = err.get(k, 0) + 1

    weak = sorted(
        [m for m in type_mastery if m["rate"] < 100],
        key=lambda x: (x["rate"], -x["count"]),
    )[:3]

    return {
        "total": total,
        "solved": solved,
        "solve_rate": round(100 * solved / total) if total else 0,
        "avg_score": avg_score,
        "type_mastery": type_mastery,
        "difficulty_dist": by_diff,
        "error_dist": err,
        "weak_points": weak,
        "recent": rows[:10],
    }
