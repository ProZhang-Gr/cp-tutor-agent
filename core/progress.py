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
           tests_passed, tests_total, score, error_kind, user_id=None, problem_id=None):
    db.execute(
        "INSERT INTO submissions (user_id, ts, problem_id, problem_title, problem_type, difficulty, "
        "passed, tests_passed, tests_total, score, error_kind) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (user_id, time.time(), problem_id, problem_title, problem_type, difficulty,
         1 if passed else 0, tests_passed, tests_total, score, error_kind),
    )


def solved_problem_ids(user_id):
    """该用户已 AC（全部通过）的题目 id 列表（含题库题与自建题）。"""
    if user_id is None:
        rows = db.query("SELECT DISTINCT problem_id FROM submissions "
                        "WHERE user_id IS NULL AND passed=1 AND problem_id IS NOT NULL")
    else:
        rows = db.query("SELECT DISTINCT problem_id FROM submissions "
                        "WHERE user_id=? AND passed=1 AND problem_id IS NOT NULL", (user_id,))
    return [r["problem_id"] for r in rows]


def add_user_problem(user_id, title, ptype, difficulty, description):
    """把用户自建题纳入题单（同用户同标题去重），返回形如 'U3' 的 id。"""
    if user_id is None:
        ex = db.query_one("SELECT id FROM user_problems WHERE user_id IS NULL AND title=?", (title,))
    else:
        ex = db.query_one("SELECT id FROM user_problems WHERE user_id=? AND title=?", (user_id, title))
    if ex:
        return "U%d" % ex["id"]
    db.execute("INSERT INTO user_problems (user_id, title, type, difficulty, description, created_at) "
               "VALUES (?,?,?,?,?,?)", (user_id, title, ptype, difficulty, description, time.time()))
    if user_id is None:
        r = db.query_one("SELECT id FROM user_problems WHERE user_id IS NULL AND title=? ORDER BY id DESC", (title,))
    else:
        r = db.query_one("SELECT id FROM user_problems WHERE user_id=? AND title=? ORDER BY id DESC", (user_id, title))
    return "U%d" % r["id"] if r else None


def list_user_problems(user_id):
    if user_id is None:
        rows = db.query("SELECT id, title, type, difficulty FROM user_problems "
                        "WHERE user_id IS NULL ORDER BY id DESC")
    else:
        rows = db.query("SELECT id, title, type, difficulty FROM user_problems "
                        "WHERE user_id=? ORDER BY id DESC", (user_id,))
    return [{"id": "U%d" % r["id"], "title": r["title"],
             "type": r["type"] or "其他", "difficulty": r["difficulty"] or "未知"} for r in rows]


def get_user_problem(user_id, pid):
    """按 'U3' 取回用户自建题完整信息。"""
    try:
        rid = int(str(pid)[1:])
    except (ValueError, IndexError):
        return None
    if user_id is None:
        r = db.query_one("SELECT * FROM user_problems WHERE id=? AND user_id IS NULL", (rid,))
    else:
        r = db.query_one("SELECT * FROM user_problems WHERE id=? AND user_id=?", (rid, user_id))
    if not r:
        return None
    return {"id": "U%d" % r["id"], "title": r["title"], "type": r["type"],
            "difficulty": r["difficulty"], "description": r["description"]}


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
