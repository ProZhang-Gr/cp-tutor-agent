# -*- coding: utf-8 -*-
"""学习进度跟踪：SQLite 持久化提交记录，并产出仪表盘统计。

记录每次代码提交（题目、题型、难度、判题结果、得分），
据此分析：总体通过率、各题型掌握度（雷达图）、难度分布、薄弱点、近期活跃。
"""
import os
import sqlite3
import time

from config import settings


def _conn():
    os.makedirs(os.path.dirname(settings.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(settings.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            ts           REAL,
            problem_title TEXT,
            problem_type TEXT,
            difficulty   TEXT,
            passed       INTEGER,   -- 1=全部通过
            tests_passed INTEGER,
            tests_total  INTEGER,
            score        INTEGER,
            error_kind   TEXT       -- AC/WA/TLE/RE/CE 主错误类型
        )
    """)
    conn.commit()
    conn.close()


def record(problem_title, problem_type, difficulty, passed,
           tests_passed, tests_total, score, error_kind):
    conn = _conn()
    conn.execute(
        "INSERT INTO submissions (ts, problem_title, problem_type, difficulty, "
        "passed, tests_passed, tests_total, score, error_kind) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (time.time(), problem_title, problem_type, difficulty,
         1 if passed else 0, tests_passed, tests_total, score, error_kind),
    )
    conn.commit()
    conn.close()


def stats():
    """汇总统计，供前端仪表盘渲染。"""
    conn = _conn()
    rows = conn.execute("SELECT * FROM submissions ORDER BY ts DESC").fetchall()
    conn.close()
    rows = [dict(r) for r in rows]

    total = len(rows)
    solved = sum(1 for r in rows if r["passed"])
    avg_score = round(sum(r["score"] for r in rows) / total, 1) if total else 0

    # 按题型聚合（雷达图：每个题型的通过率 0-100）
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

    # 难度分布
    by_diff = {}
    for r in rows:
        d = r["difficulty"] or "未知"
        by_diff[d] = by_diff.get(d, 0) + 1

    # 错误类型分布（薄弱点）
    err = {}
    for r in rows:
        k = r["error_kind"] or "AC"
        err[k] = err.get(k, 0) + 1

    # 薄弱题型：通过率最低且至少做过 1 题
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
