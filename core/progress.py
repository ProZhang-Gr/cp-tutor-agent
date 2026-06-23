# -*- coding: utf-8 -*-
"""学习进度跟踪（SQLAlchemy ORM）。

登录用户看自己的数据；游客（user_id 为空）共用一个游客桶。
"""
import time
from datetime import datetime

from sqlalchemy import select

from core.db import create_all, session_scope
from core.models import Submission, UserProblem


def init_db():
    create_all()


def _user_cond(model, user_id):
    return model.user_id == user_id if user_id is not None else model.user_id.is_(None)


def record(problem_title, problem_type, difficulty, passed,
           tests_passed, tests_total, score, error_kind, user_id=None,
           problem_id=None, code=None):
    with session_scope() as s:
        s.add(Submission(
            user_id=user_id, ts=time.time(), problem_id=problem_id,
            problem_title=problem_title, problem_type=problem_type, difficulty=difficulty,
            passed=1 if passed else 0, tests_passed=tests_passed,
            tests_total=tests_total, score=score, error_kind=error_kind,
            code=code,
        ))


def list_submissions(user_id, problem_id, limit=30):
    """某题在当前用户（或游客桶）下的历次提交，按时间倒序，含源代码。"""
    if not problem_id:
        return []
    with session_scope() as s:
        rows = list(s.scalars(
            select(Submission)
            .where(_user_cond(Submission, user_id), Submission.problem_id == problem_id)
            .order_by(Submission.ts.desc())
            .limit(limit)
        ))
        return [{
            "id": r.id, "ts": r.ts,
            "passed": bool(r.passed), "error_kind": r.error_kind or "AC",
            "tests_passed": r.tests_passed, "tests_total": r.tests_total,
            "score": r.score, "code": r.code or "",
        } for r in rows]


def stats(user_id=None):
    with session_scope() as s:
        rows = list(s.scalars(
            select(Submission).where(_user_cond(Submission, user_id))
            .order_by(Submission.ts.desc())
        ))
        total = len(rows)
        solved = sum(1 for r in rows if r.passed)
        avg_score = round(sum(r.score for r in rows) / total, 1) if total else 0

        by_type = {}
        for r in rows:
            t = r.problem_type or "其他"
            d = by_type.setdefault(t, {"total": 0, "passed": 0})
            d["total"] += 1
            d["passed"] += 1 if r.passed else 0
        type_mastery = [
            {"type": t, "rate": round(100 * d["passed"] / d["total"]), "count": d["total"]}
            for t, d in sorted(by_type.items(), key=lambda x: -x[1]["total"])
        ]

        by_diff = {}
        for r in rows:
            k = r.difficulty or "未知"
            by_diff[k] = by_diff.get(k, 0) + 1

        err = {}
        for r in rows:
            k = r.error_kind or "AC"
            err[k] = err.get(k, 0) + 1

        # 每日活跃度（按本地日期计数），供前端画 GitHub 风格刷题日历热力图
        daily = {}
        for r in rows:
            dk = datetime.fromtimestamp(r.ts).strftime("%Y-%m-%d")
            daily[dk] = daily.get(dk, 0) + 1

        weak = sorted([m for m in type_mastery if m["rate"] < 100],
                      key=lambda x: (x["rate"], -x["count"]))[:3]

        recent = [{
            "problem_title": r.problem_title, "problem_type": r.problem_type,
            "error_kind": r.error_kind, "score": r.score, "ts": r.ts,
        } for r in rows[:10]]

    return {
        "total": total, "solved": solved,
        "solve_rate": round(100 * solved / total) if total else 0,
        "avg_score": avg_score, "type_mastery": type_mastery,
        "difficulty_dist": by_diff, "error_dist": err,
        "weak_points": weak, "recent": recent,
        "daily_activity": daily, "active_days": len(daily),
    }


def solved_problem_ids(user_id):
    with session_scope() as s:
        q = (select(Submission.problem_id)
             .where(_user_cond(Submission, user_id),
                    Submission.passed == 1, Submission.problem_id.isnot(None))
             .distinct())
        return [pid for pid in s.scalars(q) if pid]


def add_user_problem(user_id, title, ptype, difficulty, description):
    """纳入题单（同用户同标题去重），返回形如 'U3' 的 id。"""
    with session_scope() as s:
        existing = s.scalar(select(UserProblem).where(
            _user_cond(UserProblem, user_id), UserProblem.title == title))
        if existing:
            return "U%d" % existing.id
        up = UserProblem(user_id=user_id, title=title, type=ptype,
                         difficulty=difficulty, description=description, created_at=time.time())
        s.add(up)
        s.flush()
        return "U%d" % up.id


def list_user_problems(user_id):
    with session_scope() as s:
        rows = list(s.scalars(select(UserProblem)
                    .where(_user_cond(UserProblem, user_id))
                    .order_by(UserProblem.id.desc())))
        return [{"id": "U%d" % r.id, "title": r.title,
                 "type": r.type or "其他", "difficulty": r.difficulty or "未知"} for r in rows]


def get_user_problem(user_id, pid):
    try:
        rid = int(str(pid)[1:])
    except (ValueError, IndexError):
        return None
    with session_scope() as s:
        r = s.scalar(select(UserProblem).where(
            UserProblem.id == rid, _user_cond(UserProblem, user_id)))
        if not r:
            return None
        return {"id": "U%d" % r.id, "title": r.title, "type": r.type,
                "difficulty": r.difficulty, "description": r.description}
