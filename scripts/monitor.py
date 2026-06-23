# -*- coding: utf-8 -*-
"""只读运维监控：从审计日志看「谁、从哪个 IP、调了多少次 AI」。

不是 HTTP 接口（避免再开一个需要鉴权的高危端点），而是运维在服务器/本地
直接对数据库跑的脚本，安全。线上连同一个 DATABASE_URL 即可看线上数据。

用法：
    python scripts/monitor.py            # 默认看最近 24 小时
    python scripts/monitor.py 72         # 看最近 72 小时
    python scripts/monitor.py 24 50      # 最近 24h，并列出最近 50 条明细
"""
import os
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from config import settings  # noqa: E402
from core.db import session_scope  # noqa: E402
from core.models import AuditLog, User  # noqa: E402


def _fmt(ts):
    return time.strftime("%m-%d %H:%M:%S", time.localtime(ts))


def main():
    hours = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    detail_n = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    since = time.time() - hours * 3600

    with session_scope() as s:
        rows = list(s.scalars(
            select(AuditLog).where(AuditLog.ts >= since).order_by(AuditLog.ts.desc())))
        names = {u.id: u.username for u in s.scalars(select(User))}

    total = len(rows)
    cap = settings.GLOBAL_DAILY_LLM_CAP
    print("=" * 66)
    print("审计监控 · 最近 %d 小时" % hours)
    print("=" * 66)
    print("AI 调用总数：%d%s" % (
        total, ("  /  全站日上限 %d（%.0f%%）" % (cap, 100.0 * total / cap)) if cap else ""))

    by_ip = Counter(r.ip or "?" for r in rows)
    by_user = Counter((names.get(r.user_id, "游客#%s" % r.ip) if r.user_id else "游客") for r in rows)
    by_endpoint = Counter(r.endpoint or "?" for r in rows)
    ip_users = defaultdict(set)   # IP -> 用过的 user_id 集合
    user_ips = defaultdict(set)   # user -> 用过的 IP 集合
    for r in rows:
        ip_users[r.ip or "?"].add(r.user_id)
        if r.user_id:
            user_ips[names.get(r.user_id, r.user_id)].add(r.ip or "?")

    print("\n— 调用最多的 IP（前 10）—")
    for ip, n in by_ip.most_common(10):
        print("  %-22s %5d 次   关联账号 %d 个" % (ip, n, len([u for u in ip_users[ip] if u])))

    print("\n— 调用最多的账号（前 10）—")
    for u, n in by_user.most_common(10):
        print("  %-22s %5d 次" % (str(u), n))

    print("\n— 端点分布 —")
    for ep, n in by_endpoint.most_common():
        print("  %-16s %5d" % (ep, n))

    # 简单异常信号
    print("\n— 可疑信号 —")
    flagged = False
    for ip, n in by_ip.items():
        if n >= max(settings.QUOTA_GUEST, 50):
            print("  ⚠ IP %s 调用 %d 次（≥%d），疑似刷量" % (ip, n, max(settings.QUOTA_GUEST, 50)))
            flagged = True
    for u, ips in user_ips.items():
        if len(ips) >= 4:
            print("  ⚠ 账号 %s 来自 %d 个不同 IP，疑似共享/异常" % (u, len(ips)))
            flagged = True
    if not flagged:
        print("  （无）")

    print("\n— 最近 %d 条明细 —" % detail_n)
    for r in rows[:detail_n]:
        who = names.get(r.user_id, "游客") if r.user_id else "游客"
        print("  %s  %-14s  ip=%-16s  %-10s  %s" % (
            _fmt(r.ts), who, r.ip or "?", r.endpoint or "?", (r.meta or "")[:80]))


if __name__ == "__main__":
    main()
