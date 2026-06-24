# -*- coding: utf-8 -*-
"""学习行为埋点（聚合，非键鼠记录）。

只接收并存储「时长 + 计数」这类聚合学习行为：专注时长、击键次数、运行/提交次数。
不接收、不存储任何按键内容或鼠标轨迹——这是有教育价值且尊重隐私的行为分析，
与「全量 keylogger」有本质区别（见 DESIGN.md）。

登录用户按 uid 归属；游客（user_id 为空）共用游客桶。
"""
import time
from datetime import datetime

from sqlalchemy import func, select

from config import settings
from core.db import session_scope
from core.models import StudyLog


def _clamp(v, lo, hi):
    try:
        v = int(v)
    except (TypeError, ValueError):
        return lo
    return max(lo, min(hi, v))


def record(user_id, problem_id, active_seconds, keystrokes, runs, submits):
    """落一条聚合埋点。各字段越界即截断，防止被伪造成天量数据刷榜。"""
    active_seconds = _clamp(active_seconds, 0, settings.TELEMETRY_MAX_SECONDS)
    keystrokes = _clamp(keystrokes, 0, settings.TELEMETRY_MAX_KEYSTROKES)
    runs = _clamp(runs, 0, 10000)
    submits = _clamp(submits, 0, 10000)
    # 一段什么都没发生（全 0）就不落库，避免心跳噪声
    if active_seconds == 0 and keystrokes == 0 and runs == 0 and submits == 0:
        return False
    pid = (str(problem_id).strip()[:40] or None) if problem_id else None
    with session_scope() as s:
        s.add(StudyLog(user_id=user_id, ts=time.time(), problem_id=pid,
                       active_seconds=active_seconds, keystrokes=keystrokes,
                       runs=runs, submits=submits))
    return True


def _cond(user_id):
    return StudyLog.user_id == user_id if user_id is not None else StudyLog.user_id.is_(None)


def summary(user_id):
    """学习行为汇总，供仪表盘「学习投入」卡片展示。"""
    today_key = datetime.now().strftime("%Y-%m-%d")
    with session_scope() as s:
        rows = list(s.scalars(select(StudyLog).where(_cond(user_id))))
    total_seconds = sum(r.active_seconds or 0 for r in rows)
    total_keys = sum(r.keystrokes or 0 for r in rows)
    total_runs = sum(r.runs or 0 for r in rows)
    total_submits = sum(r.submits or 0 for r in rows)
    today_seconds = sum((r.active_seconds or 0) for r in rows
                        if datetime.fromtimestamp(r.ts).strftime("%Y-%m-%d") == today_key)
    # 专注分钟、人均每次提交用时（粗略反映「想清楚再交」还是「乱枪打鸟」）
    avg_per_submit = round(total_seconds / total_submits / 60, 1) if total_submits else 0
    return {
        "total_minutes": round(total_seconds / 60, 1),
        "today_minutes": round(today_seconds / 60, 1),
        "total_keystrokes": total_keys,
        "total_runs": total_runs,
        "total_submits": total_submits,
        "avg_minutes_per_submit": avg_per_submit,
        "sessions": len(rows),
    }
