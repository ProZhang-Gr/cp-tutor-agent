# -*- coding: utf-8 -*-
"""每日学习报告（Pro）：聚合当日数据 + LLM 叙述性总结 + 导出 PDF。"""
import time
from io import BytesIO

from sqlalchemy import func, select

from core import profile
from core.db import session_scope
from core.llm import get_llm
from core.models import AuditLog, Submission


def _today_stats(user_id):
    since = time.time() - 86400
    with session_scope() as s:
        subs = list(s.scalars(select(Submission).where(
            Submission.user_id == user_id, Submission.ts >= since)))
        calls = s.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.user_id == user_id, AuditLog.ts >= since)) or 0
    by_type = {}
    for x in subs:
        d = by_type.setdefault(x.problem_type or "其他", {"a": 0, "ac": 0})
        d["a"] += 1
        d["ac"] += 1 if x.passed else 0
    errs = {}
    for x in subs:
        k = x.error_kind or "AC"
        if k != "AC":
            errs[k] = errs.get(k, 0) + 1
    return {
        "attempted": len(subs),
        "ac": sum(1 for x in subs if x.passed),
        "llm_calls": int(calls),
        "by_type": by_type,
        "errors": errs,
        "items": [{"title": x.problem_title, "kind": x.error_kind, "score": x.score} for x in subs[:15]],
    }


_SYS = ("你是一名贴心的学习教练。根据学生今日的刷题数据，写一份简短的「每日学习报告」"
        "（150-250字，中文）：先肯定今天的进步与亮点，再客观点出薄弱环节，最后给出明日的"
        "具体学习建议。语气温暖、鼓励，但不空洞。直接输出报告正文，不要标题。")


def build_report(user_id):
    st = _today_stats(user_id)
    prof = profile.build_profile(user_id)
    human = ("今日数据：尝试 %d 题，通过 %d 题，与AI互动 %d 次。"
             "各题型(尝试/通过)：%s。主要错误类型：%s。整体画像：%s。"
             % (st["attempted"], st["ac"], st["llm_calls"], st["by_type"], st["errors"], prof["summary"]))
    try:
        narrative = get_llm(temperature=0.6, max_tokens=600).invoke(
            [("system", _SYS), ("human", human)]).content
    except Exception:
        narrative = "今日已完成 %d 题、通过 %d 题。继续保持，明天再接再厉！" % (st["attempted"], st["ac"])
    return {"date": time.strftime("%Y-%m-%d"), "stats": st, "profile": prof, "narrative": narrative}


def build_pdf(report, username):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))  # reportlab 内置中文字体
    F = "STSong-Light"
    title = ParagraphStyle("t", fontName=F, fontSize=20, spaceAfter=6, textColor="#1F6F66")
    sub = ParagraphStyle("s", fontName=F, fontSize=10, textColor="#6E6657", spaceAfter=14)
    h = ParagraphStyle("h", fontName=F, fontSize=13, spaceBefore=10, spaceAfter=6, textColor="#1F6F66")
    body = ParagraphStyle("b", fontName=F, fontSize=11, leading=19)

    st = report["stats"]
    by = "；".join("%s %d/%d" % (t, d["ac"], d["a"]) for t, d in st["by_type"].items()) or "—"
    story = [
        Paragraph("ARENA 学习日报", title),
        Paragraph("学员：%s    日期：%s" % (username, report["date"]), sub),
        Paragraph("今日概览", h),
        Paragraph("尝试 %d 题 · 通过 %d 题 · AI 互动 %d 次<br/>题型表现：%s"
                  % (st["attempted"], st["ac"], st["llm_calls"], by), body),
        Paragraph("教练点评", h),
        Paragraph(report["narrative"].replace("\n", "<br/>"), body),
        Spacer(1, 18),
        Paragraph("—— 由 ARENA 算法竞赛辅导智能体生成", sub),
    ]
    buf = BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, title="ARENA 学习日报").build(story)
    buf.seek(0)
    return buf.read()
